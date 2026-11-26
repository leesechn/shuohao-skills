// 청음실 엔진: 검색(Apple iTunes + Deezer) · 메타데이터(MusicBrainz) · 오디오 분석(DSP) · 엄격 채점
// 서버 없음. 모든 요청은 방문자 브라우저에서 각 공개 API로 직접 나간다(트래픽이 한 서버에 몰리지 않음).

/* ───────────── 공통 ───────────── */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const memo = new Map();

function lsGet(k) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 용량 초과·차단 시 무시 */ } }

// 짧은 수명 캐시(검색 응답). 미리듣기 URL에 만료 토큰이 있어 길게 두지 않는다.
function cached(key, ttlMs, fn) {
  const hit = memo.get(key);
  if (hit && Date.now() - hit.t < ttlMs) return hit.p;
  const p = fn().catch((e) => { memo.delete(key); throw e; });
  memo.set(key, { t: Date.now(), p });
  return p;
}

/* JSONP: Apple·Deezer는 CORS 대신 callback 파라미터를 공식 지원 → 브라우저 정책과 무관하게 동작 */
let seq = 0;
export function jsonp(url, timeout = 9000) {
  return new Promise((resolve, reject) => {
    const name = `__ctl${Date.now().toString(36)}${++seq}`;
    const s = document.createElement('script');
    let done = false;
    const finish = () => { done = true; clearTimeout(t); s.remove(); window[name] = () => { delete window[name]; }; };
    window[name] = (data) => { if (done) return; finish(); delete window[name]; resolve(data); };
    s.onerror = () => { if (done) return; finish(); reject(new Error('network')); };
    const t = setTimeout(() => { if (done) return; finish(); reject(new Error('timeout')); }, timeout);
    s.src = `${url}${url.includes('?') ? '&' : '?'}callback=${name}`;
    s.referrerPolicy = 'no-referrer';
    document.head.appendChild(s);
  });
}

/* MusicBrainz: 공식 규칙상 IP당 초당 1회 → 1.1초 간격 큐 */
let mbChain = Promise.resolve();
let mbLast = 0;
export function mb(path) {
  const key = 'mb:' + path;
  const stored = lsGet('ctl:c:' + key);
  if (stored && Date.now() - stored.t < 14 * 864e5) return Promise.resolve(stored.v);
  return cached(key, 36e5, () => {
    const task = async () => {
      for (let attempt = 0; attempt < 3; attempt++) {
        const wait = Math.max(0, mbLast + 1100 - Date.now());
        if (wait) await sleep(wait);
        mbLast = Date.now();
        const r = await fetch(`https://musicbrainz.org/ws/2/${path}${path.includes('?') ? '&' : '?'}fmt=json`, { headers: { Accept: 'application/json' } });
        if (r.status === 503 || r.status === 429) { await sleep(1500 * (attempt + 1)); continue; }
        if (!r.ok) throw new Error('mb ' + r.status);
        const v = await r.json();
        lsSet('ctl:c:' + key, { t: Date.now(), v });
        return v;
      }
      throw new Error('mb busy');
    };
    const p = mbChain.then(task);
    mbChain = p.catch(() => {});
    return p;
  });
}

/* ───────────── 문자열 정규화·관련도 ───────────── */
const lite = (s) => (s || '').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
export const dedupeKey = (s) => lite(
  (s || '').normalize('NFKC')
    .replace(/\((?:feat|ft|with|prod)[^)]*\)|\[(?:feat|ft|with|prod)[^\]]*\]/gi, ' ')
    .replace(/\s[-–]\s.*\b(remaster(?:ed)?|version|edit|mix|live)\b.*$/i, ' ')
    .replace(/\((?:[^)]*\b(?:remaster(?:ed)?|version|edit)\b[^)]*)\)/gi, ' ')
);
const primaryArtist = (a) => (a || '').split(/\s*(?:,|&|\/|\bfeat\.?|\bft\.?|\bwith\b|\bx\b)\s*/i)[0];

export function relevance(q, title, artist, idx, n) {
  const nq = lite(q), nt = lite(title), na = lite(artist);
  if (!nq) return 0;
  let s = 0;
  if (nt === nq) s += 100; else if (nt.startsWith(nq)) s += 72; else if (nt.includes(nq)) s += 50;
  if (na === nq) s += 64; else if (na.startsWith(nq)) s += 40;
  if (na && na.length > 1 && nq.includes(na)) {
    const rest = nq.replace(na, '');
    s += rest && (nt === rest ? 120 : nt.startsWith(rest) ? 95 : nt.includes(rest) ? 70 : 0) || 30;
  }
  if (nt.length > 1 && nq !== nt && nq.includes(nt)) s += 38;
  const toks = (q || '').toLowerCase().split(/\s+/).map(lite).filter((t) => t.length > 0);
  const hay = nt + ' ' + na;
  for (const t of toks) if (hay.includes(t)) s += 12;
  s += (1 - idx / Math.max(n, 1)) * 30; // 각 서비스가 매긴 순서(인기·정확도)를 보조 신호로
  return s;
}

/* ───────────── 검색 ───────────── */
const art600 = (u) => (u || '').replace(/\/\d+x\d+bb\./, '/600x600bb.');
const yearOf = (d) => (d ? String(d).slice(0, 4) : '');

function fromAppleSong(r) {
  return {
    kind: 'track', title: r.trackName, artist: r.artistName, album: r.collectionName, year: yearOf(r.releaseDate),
    artwork: art600(r.artworkUrl100), preview: r.previewUrl || '', appleUrl: r.trackViewUrl, appleId: r.trackId,
    appleAlbumId: r.collectionId, appleArtistId: r.artistId, durationMs: r.trackTimeMillis || 0,
    genre: r.primaryGenreName || '', explicit: r.trackExplicitness === 'explicit',
  };
}
function fromDeezerTrack(t) {
  return {
    kind: 'track', title: t.title, artist: t.artist?.name, album: t.album?.title, year: '',
    artwork: t.album?.cover_xl || t.album?.cover_big || '', preview: t.preview || '', previewAlt: t.preview || '', deezerId: t.id, deezerUrl: t.link,
    deezerAlbumId: t.album?.id, deezerArtistId: t.artist?.id, durationMs: (t.duration || 0) * 1000, genre: '', explicit: !!t.explicit_lyrics,
  };
}
function fromAppleAlbum(r) {
  return {
    kind: 'album', title: r.collectionName, artist: r.artistName, year: yearOf(r.releaseDate), artwork: art600(r.artworkUrl100),
    appleUrl: r.collectionViewUrl, appleId: r.collectionId, appleArtistId: r.artistId, trackCount: r.trackCount, genre: r.primaryGenreName || '',
  };
}
function fromDeezerAlbum(a) {
  return {
    kind: 'album', title: a.title, artist: a.artist?.name, year: '', artwork: a.cover_xl || a.cover_big || '', deezerId: a.id,
    deezerUrl: a.link, deezerArtistId: a.artist?.id, trackCount: a.nb_tracks, recordType: a.record_type, genre: '',
  };
}
function fromAppleArtist(r) {
  return { kind: 'artist', title: r.artistName, artist: r.artistName, artwork: '', appleUrl: r.artistLinkUrl, appleId: r.artistId, genre: r.primaryGenreName || '' };
}
function fromDeezerArtist(a) {
  return { kind: 'artist', title: a.name, artist: a.name, artwork: a.picture_xl || a.picture_big || '', deezerId: a.id, deezerUrl: a.link, fans: a.nb_fan, genre: '' };
}

export function itemKey(it) {
  return it.kind === 'artist'
    ? `artist|${dedupeKey(it.title)}`
    : `${it.kind}|${dedupeKey(it.title)}|${dedupeKey(primaryArtist(it.artist))}`;
}

function merge(lists, q) {
  const map = new Map();
  for (const { items, src } of lists) {
    items.forEach((raw, i) => {
      if (!raw || !raw.title) return;
      const it = { ...raw, srcs: [src] };
      it.key = itemKey(it);
      const score = relevance(q, it.title, it.kind === 'artist' ? '' : it.artist, i, items.length);
      const prev = map.get(it.key);
      if (!prev) { it.rel = score; map.set(it.key, it); return; }
      // 같은 곡이 두 서비스에 모두 있으면 하나로 합치고 정확도 가산
      for (const [k, v] of Object.entries(it)) if (v && !prev[k]) prev[k] = v;
      if (src === 'apple' && it.artwork) prev.artwork = it.artwork;
      if (!prev.srcs.includes(src)) { prev.srcs.push(src); prev.rel = Math.max(prev.rel, score) + 18; }
      else prev.rel = Math.max(prev.rel, score);
    });
  }
  return [...map.values()].sort((a, b) => b.rel - a.rel);
}

const enc = encodeURIComponent;
const apple = (params) => jsonp(`https://itunes.apple.com/search?${params}`).then((d) => d.results || []);
const deezer = (path) => jsonp(`https://api.deezer.com/${path}${path.includes('?') ? '&' : '?'}output=jsonp`).then((d) => {
  if (d && d.error) throw new Error('deezer ' + (d.error.message || ''));
  return d;
});
const safe = (p) => p.then((v) => ({ ok: true, v }), (e) => ({ ok: false, e }));

// 검색: 곡(Apple KR·Deezer) + 앨범 + 아티스트를 병렬 조회 후 중복 병합·관련도 정렬
// Apple 공개 API는 분당 약 20회 제한 → 전체 탭에서는 Apple 1회만 호출하고, 결과가 적으면 US 스토어 보강
export function search(q, tab = 'all') {
  q = q.trim();
  return cached(`s:${tab}:${q.toLowerCase()}`, 10 * 6e4, async () => {
    const term = enc(q);
    const jobs = {};
    if (tab === 'all' || tab === 'track') {
      jobs.aSong = safe(apple(`term=${term}&media=music&entity=song&limit=${tab === 'track' ? 50 : 25}&country=KR`));
      jobs.dTrack = safe(deezer(`search?q=${term}&limit=${tab === 'track' ? 50 : 25}`).then((d) => d.data || []));
    }
    if (tab === 'all' || tab === 'album') {
      if (tab === 'album') jobs.aAlbum = safe(apple(`term=${term}&media=music&entity=album&limit=25&country=KR`));
      jobs.dAlbum = safe(deezer(`search/album?q=${term}&limit=${tab === 'album' ? 25 : 10}`).then((d) => d.data || []));
    }
    if (tab === 'all' || tab === 'artist') {
      if (tab === 'artist') jobs.aArtist = safe(apple(`term=${term}&media=music&entity=musicArtist&limit=10&country=KR`));
      jobs.dArtist = safe(deezer(`search/artist?q=${term}&limit=${tab === 'artist' ? 20 : 6}`).then((d) => d.data || []));
    }
    const keys = Object.keys(jobs);
    const res = Object.fromEntries((await Promise.all(keys.map((k) => jobs[k]))).map((v, i) => [keys[i], v]));
    const val = (k) => (res[k] && res[k].ok ? res[k].v : []);
    if (res.aSong && res.aSong.ok && val('aSong').length < 5) {
      const us = await safe(apple(`term=${term}&media=music&entity=song&limit=25&country=US`));
      if (us.ok) res.aSong.v = val('aSong').concat(us.v);
    }
    const failed = keys.filter((k) => res[k] && !res[k].ok).map((k) => (k[0] === 'a' ? 'Apple Music' : 'Deezer'));
    const tracks = merge([
      { src: 'apple', items: val('aSong').filter((r) => r.kind === 'song' || r.wrapperType === 'track').map(fromAppleSong) },
      { src: 'deezer', items: val('dTrack').map(fromDeezerTrack) },
    ], q);
    // 곡 결과에서 앨범·아티스트도 보강(Apple 호출을 늘리지 않기 위해)
    const albumFromSongs = val('aSong').map((r) => ({ kind: 'album', title: r.collectionName, artist: r.collectionArtistName || r.artistName, year: yearOf(r.releaseDate), artwork: art600(r.artworkUrl100), appleUrl: r.collectionViewUrl, appleId: r.collectionId, genre: r.primaryGenreName }));
    const albums = merge([
      { src: 'apple', items: val('aAlbum').map(fromAppleAlbum).concat(tab === 'all' ? albumFromSongs : []) },
      { src: 'deezer', items: val('dAlbum').map(fromDeezerAlbum) },
    ], q);
    const artists = merge([
      { src: 'apple', items: val('aArtist').map(fromAppleArtist) },
      { src: 'deezer', items: val('dArtist').map(fromDeezerArtist) },
    ], q);
    const top = [tracks[0], artists[0], albums[0]].filter(Boolean).sort((a, b) => (b.rel + (b.kind === 'artist' ? 6 : 0)) - (a.rel + (a.kind === 'artist' ? 6 : 0)))[0] || null;
    if (!tracks.length && !albums.length && !artists.length && failed.length === keys.length) throw new Error('all-failed');
    return { tracks, albums, artists, top, failed: [...new Set(failed)] };
  });
}

// 자동완성: 입력 중에는 Deezer만(호출 제한이 넉넉) 사용
export function suggest(q) {
  q = q.trim();
  return cached(`sg:${q.toLowerCase()}`, 10 * 6e4, async () => {
    const d = await deezer(`search?q=${enc(q)}&limit=8`);
    return merge([{ src: 'deezer', items: (d.data || []).map(fromDeezerTrack) }], q).slice(0, 6);
  });
}

/* ───────────── 상세 조회(앨범 수록곡·아티스트 대표곡) ───────────── */
export async function albumTracks(al) {
  if (al.deezerId) {
    const d = await deezer(`album/${al.deezerId}`);
    al.year = al.year || yearOf(d.release_date);
    al.genres = (d.genres?.data || []).map((g) => g.name);
    al.label = d.label;
    return (d.tracks?.data || []).map((t) => ({ ...fromDeezerTrack({ ...t, album: { title: d.title, cover_xl: d.cover_xl, id: d.id } }), year: al.year }));
  }
  if (al.appleId) {
    const d = await jsonp(`https://itunes.apple.com/lookup?id=${al.appleId}&entity=song&country=KR`);
    return (d.results || []).filter((r) => r.wrapperType === 'track').map(fromAppleSong);
  }
  // Apple 결과에만 있는 앨범 → Deezer에서 찾아 연결
  const s = await deezer(`search/album?q=${enc(`${al.artist} ${al.title}`)}&limit=5`);
  const best = (s.data || []).find((a) => dedupeKey(a.title) === dedupeKey(al.title)) || (s.data || [])[0];
  if (!best) return [];
  al.deezerId = best.id;
  return albumTracks(al);
}

export async function artistTopTracks(ar) {
  let id = ar.deezerId;
  if (!id) {
    const s = await deezer(`search/artist?q=${enc(ar.title)}&limit=5`);
    const best = (s.data || []).find((a) => lite(a.name) === lite(ar.title)) || (s.data || [])[0];
    if (!best) return [];
    id = ar.deezerId = best.id;
    ar.artwork = ar.artwork || best.picture_xl;
  }
  const d = await deezer(`artist/${id}/top?limit=10`);
  return (d.data || []).map(fromDeezerTrack);
}

/* ───────────── 메타데이터: Deezer 상세 + MusicBrainz 크레딧·장르 ───────────── */
async function deezerDetail(tr) {
  let id = tr.deezerId;
  if (!id) {
    const s = await deezer(`search?q=${enc(`artist:"${tr.artist}" track:"${tr.title}"`)}&limit=5`).catch(() => null);
    const list = (s && s.data) || [];
    const best = list.find((t) => dedupeKey(t.title) === dedupeKey(tr.title)) || list[0];
    if (!best) return null;
    id = tr.deezerId = best.id;
    tr.deezerUrl = tr.deezerUrl || best.link;
    tr.preview = tr.preview || best.preview;
  }
  const t = await deezer(`track/${id}`);
  let genres = [];
  if (t.album?.id) {
    const a = await deezer(`album/${t.album.id}`).catch(() => null);
    genres = (a?.genres?.data || []).map((g) => g.name);
    if (a?.release_date) tr.year = tr.year || yearOf(a.release_date);
    tr.label = a?.label || tr.label;
  }
  return { isrc: t.isrc, bpm: t.bpm || 0, gain: t.gain, contributors: (t.contributors || []).map((c) => ({ name: c.name, role: c.role })), genres, release: t.release_date };
}

const luc = (s) => (s || '').replace(/([+\-!(){}[\]^"~*?:\\/]|&&|\|\|)/g, '\\$1');

async function mbRecordingId(tr, isrc) {
  if (isrc) {
    const d = await mb(`isrc/${enc(isrc)}?inc=artist-credits`).catch(() => null);
    const recs = d?.recordings || [];
    if (recs.length) return recs[0].id;
  }
  const q = `recording:"${luc(tr.title)}" AND artist:"${luc(primaryArtist(tr.artist))}"`;
  const d = await mb(`recording?query=${enc(q)}&limit=8`);
  const recs = (d.recordings || []).filter((r) => (r.score ?? 100) >= 80);
  const exact = recs.find((r) => dedupeKey(r.title) === dedupeKey(tr.title));
  return (exact || recs[0])?.id || null;
}

const ROLE_KO = {
  composer: '작곡', lyricist: '작사', writer: '작사·작곡', arranger: '편곡', librettist: '작사', producer: '프로듀서',
  mix: '믹스', engineer: '엔지니어', 'recording engineer': '레코딩', mastering: '마스터링', programming: '프로그래밍',
  vocal: '보컬', instrument: '연주', 'performing orchestra': '오케스트라', conductor: '지휘', orchestrator: '오케스트레이션',
};

export async function musicBrainz(tr, isrc) {
  const id = await mbRecordingId(tr, isrc);
  if (!id) return { credits: [], tags: [], mbUrl: '' };
  const rec = await mb(`recording/${id}?inc=artist-credits+genres+tags+work-rels+work-level-rels+artist-rels+releases`);
  const credits = [];
  const push = (role, name, attrs) => {
    if (!name) return;
    const ko = ROLE_KO[role] || role;
    const label = role === 'instrument' && attrs?.length ? `연주(${attrs.join(', ')})` : ko;
    if (!credits.some((c) => c.name === name && c.role === label)) credits.push({ role: label, name, raw: role });
  };
  for (const r of rec.relations || []) {
    if (r['target-type'] === 'artist' && r.artist) push(r.type, r.artist.name, r.attributes);
    if (r['target-type'] === 'work' && r.work) {
      for (const w of r.work.relations || []) if (w['target-type'] === 'artist' && w.artist) push(w.type, w.artist.name, w.attributes);
    }
  }
  const tagW = new Map();
  const add = (list, w) => (list || []).forEach((g) => tagW.set(g.name.toLowerCase(), (tagW.get(g.name.toLowerCase()) || 0) + w * Math.max(1, g.count || 1)));
  add(rec.genres, 3); add(rec.tags, 1.2);
  const artistId = rec['artist-credit']?.[0]?.artist?.id;
  if (artistId) {
    const a = await mb(`artist/${artistId}?inc=genres+tags`).catch(() => null);
    if (a) { add(a.genres, 1); add(a.tags, 0.4); }
  }
  return { credits, tags: [...tagW.entries()].map(([name, w]) => ({ name, w })), mbUrl: `https://musicbrainz.org/recording/${id}`, firstRelease: rec['first-release-date'] };
}

/* ───────────── 장르 정리 ───────────── */
export const GENRE_KO = {
  pop: '팝', 'k-pop': '케이팝', 'dance-pop': '댄스팝', 'synth-pop': '신스팝', synthpop: '신스팝', electropop: '일렉트로팝', 'indie pop': '인디 팝',
  'dream pop': '드림팝', 'bedroom pop': '베드룸 팝', 'art pop': '아트 팝', 'teen pop': '틴 팝', 'r&b': 'R&B', 'contemporary r&b': '컨템퍼러리 R&B',
  'alternative r&b': '얼터너티브 R&B', 'neo soul': '네오 소울', soul: '소울', 'hip hop': '힙합', 'hip-hop': '힙합', rap: '랩', trap: '트랩',
  'boom bap': '붐뱁', 'k-hip hop': '국내 힙합', rock: '록', 'alternative rock': '얼터너티브 록', 'indie rock': '인디 록', shoegaze: '슈게이즈',
  'post-rock': '포스트록', 'art rock': '아트록', 'progressive rock': '프로그레시브 록', 'punk rock': '펑크록', punk: '펑크록', 'pop punk': '팝펑크',
  metal: '메탈', 'heavy metal': '헤비메탈', grunge: '그런지', 'britpop': '브릿팝', folk: '포크', 'indie folk': '인디 포크', 'singer-songwriter': '싱어송라이터',
  ballad: '발라드', 'k-ballad': '가요 발라드', jazz: '재즈', 'jazz pop': '재즈 팝', 'bossa nova': '보사노바', house: '하우스', 'deep house': '딥하우스',
  'uk garage': 'UK 개러지', '2-step': '투스텝', 'jersey club': '저지 클럽', techno: '테크노', ambient: '앰비언트', edm: 'EDM', electronic: '일렉트로닉',
  'drum and bass': '드럼앤베이스', dubstep: '덥스텝', 'future bass': '퓨처 베이스', disco: '디스코', 'nu-disco': '뉴디스코', funk: '펑크(Funk)',
  'city pop': '시티팝', 'j-pop': '제이팝', 'j-rock': '제이록', classical: '클래식', 'lo-fi': '로파이', hyperpop: '하이퍼팝', 'film score': '영화음악',
  soundtrack: 'OST', trot: '트로트', 'reggaeton': '레게톤', 'latin pop': '라틴 팝', afrobeats: '아프로비츠', country: '컨트리', blues: '블루스',
  gospel: '가스펠', 'new wave': '뉴웨이브', 'post-punk': '포스트펑크', 'trip hop': '트립합', 'dance': '댄스', 'alternative': '얼터너티브',
  'indie': '인디', 'electro': '일렉트로', 'k-indie': '국내 인디', 'mandopop': '만다린 팝', 'cantopop': '광둥 팝', 'vocal jazz': '보컬 재즈',
  'piano': '피아노', 'acoustic': '어쿠스틱', 'garage rock': '개러지 록', 'emo': '이모', 'experimental': '익스페리멘털', 'idm': 'IDM',
};
const NOT_GENRE = /^(seen live|favorites?|favourite|korean|south korean|japanese|american|british|english|female vocalists?|male vocalists?|\d{4}s?|vocal|seoul|usa|uk|beautiful|love|awesome|my|cover|instrumental version)$/i;
const ELECTRONIC = /(garage|2-step|jersey|house|edm|synth|trap|r&b|electro|techno|future|hyperpop|dance|disco|dubstep|drum and bass|idm|club|hip ?hop|rap|ambient|trip hop)/i;
const ACOUSTIC = /(folk|acoustic|ballad|singer-songwriter|rock|indie|alternative|jazz|classical|bossa|piano|country|blues|shoegaze|grunge|punk|post-rock|orchestral|soundtrack|chamber)/i;

export function rankGenres({ tags = [], deezer = [], apple = '' }) {
  const w = new Map();
  for (const t of tags) if (!NOT_GENRE.test(t.name)) w.set(t.name, (w.get(t.name) || 0) + t.w);
  const top = Math.max(1, ...w.values());
  for (const g of deezer) { const k = g.toLowerCase(); if (!NOT_GENRE.test(k)) w.set(k, (w.get(k) || 0) + top * 0.25); }
  if (apple) { const k = apple.toLowerCase(); w.set(k, (w.get(k) || 0) + top * 0.2); }
  return [...w.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([name, weight]) => ({ name, ko: GENRE_KO[name] || '', weight: +(weight / top).toFixed(2) }));
}
export function genreClass(genres) {
  const s = genres.slice(0, 3).map((g) => g.name).join(' ');
  if (/hip ?hop|rap|trap/i.test(s)) return 'hiphop';
  if (/(classical|orchestral|soundtrack|film score|ambient|jazz|folk|acoustic|singer-songwriter|bossa)/i.test(s)) return 'acoustic';
  if (/(house|techno|edm|electro|garage|dubstep|drum and bass|dance|disco|hyperpop|club)/i.test(s)) return 'electronic';
  if (/(rock|metal|punk|grunge|shoegaze)/i.test(s)) return 'rock';
  return 'other';
}
function genreAxis(genres) { // -1 어쿠스틱·밴드 ↔ +1 전자·R&B (taxonomy 규칙)
  let e = 0, a = 0;
  for (const g of genres) { if (ELECTRONIC.test(g.name)) e += g.weight; if (ACOUSTIC.test(g.name)) a += g.weight; }
  return e + a ? (e - a) / (e + a) : null;
}

/* ───────────── 오디오 분석(30초 미리듣기, 브라우저 내 DSP) ───────────── */
function fft(re, im) { // 제자리 radix-2
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len, wr = Math.cos(ang), wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const a = i + k, b = a + len / 2;
        const tr = re[b] * cr - im[b] * ci, ti = re[b] * ci + im[b] * cr;
        re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        const ncr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = ncr;
      }
    }
  }
}
const KK_MAJ = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
const KK_MIN = [6.33, 2.68, 3.52, 5.38, 2.6, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17];
export const PC = ['C', 'C♯', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B♭', 'B'];
const CAM_MAJ = [8, 3, 10, 5, 12, 7, 2, 9, 4, 11, 6, 1];
const CAM_MIN = [5, 12, 7, 2, 9, 4, 11, 6, 1, 8, 3, 10];
function pearson(x, y) {
  const n = x.length; let mx = 0, my = 0;
  for (let i = 0; i < n; i++) { mx += x[i]; my += y[i]; }
  mx /= n; my /= n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const a = x[i] - mx, b = y[i] - my; sxy += a * b; sxx += a * a; syy += b * b; }
  return sxy / Math.sqrt(sxx * syy + 1e-12);
}
const pct = (arr, p) => { const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.max(0, Math.floor(p * (s.length - 1))))]; };

export function computeFeatures(L, R, sr) {
  const N = 2048, H = 512, n = L.length;
  const skip = Math.floor(sr * 0.5); // 미리듣기 앞뒤 페이드 구간 제외
  const start = Math.min(skip, Math.floor(n / 4)), end = Math.max(start + N * 8, n - skip);
  let mid = 0, side = 0, peak = 0, sum = 0, cnt = 0;
  const mono = new Float32Array(end - start);
  for (let i = start; i < end; i++) {
    const m = (L[i] + R[i]) / 2, s = (L[i] - R[i]) / 2;
    mono[i - start] = m; mid += m * m; side += s * s; sum += m * m; cnt++;
    const a = Math.abs(m); if (a > peak) peak = a;
  }
  const rms = Math.sqrt(sum / cnt);
  if (rms < 1e-4) throw new Error('silent');
  const win = new Float32Array(N).map((_, i) => 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (N - 1)));
  const bins = N / 2, df = sr / N;
  const pcOf = new Int8Array(bins).fill(-1);
  for (let k = 1; k < bins; k++) { const f = k * df; if (f >= 55 && f <= 4200) pcOf[k] = ((Math.round(12 * Math.log2(f / 440)) + 69) % 12 + 12) % 12; }
  const frames = Math.floor((mono.length - N) / H);
  const re = new Float64Array(N), im = new Float64Array(N);
  let prevLog = new Float32Array(bins);
  const flux = new Float32Array(frames), cent = new Float32Array(frames), frms = new Float32Array(frames), flat = new Float32Array(frames);
  const chromaF = []; const chromaSum = new Float64Array(12);
  let eLow = 0, eMid = 0, eHigh = 0;
  const kLow = Math.round(250 / df), kHigh = Math.round(4000 / df), k100 = Math.round(100 / df), k8k = Math.round(8000 / df);
  for (let f = 0; f < frames; f++) {
    const o = f * H; let tsum = 0;
    for (let i = 0; i < N; i++) { const v = mono[o + i]; tsum += v * v; re[i] = v * win[i]; im[i] = 0; }
    frms[f] = 10 * Math.log10(tsum / N + 1e-12);
    fft(re, im);
    let num = 0, den = 0, fl = 0, lsum = 0, asum = 0, nb = 0;
    const ch = new Float32Array(12); const cur = new Float32Array(bins);
    for (let k = 1; k < bins; k++) {
      const mag = Math.hypot(re[k], im[k]); const p = mag * mag;
      num += k * df * mag; den += mag;
      const lg = Math.log1p(mag * 10); cur[k] = lg; const d = lg - prevLog[k]; if (d > 0) fl += d;
      if (pcOf[k] >= 0) ch[pcOf[k]] += mag;
      if (k < kLow) eLow += p; else if (k < kHigh) eMid += p; else eHigh += p;
      if (k >= k100 && k <= k8k) { lsum += Math.log(mag + 1e-9); asum += mag; nb++; }
    }
    prevLog = cur; flux[f] = fl; cent[f] = den > 0 ? num / den : 0;
    flat[f] = nb ? Math.exp(lsum / nb) / (asum / nb + 1e-12) : 0;
    chromaF.push(ch); for (let c = 0; c < 12; c++) chromaSum[c] += ch[c];
  }
  const fps = sr / H;
  // 템포: 온셋 포락선 자기상관 + 120BPM 중심 로그 정규 사전분포
  const onset = new Float32Array(frames); const w = Math.round(fps * 0.4);
  for (let f = 0; f < frames; f++) {
    let s = 0, c = 0; for (let j = Math.max(0, f - w); j < Math.min(frames, f + w); j++) { s += flux[j]; c++; }
    onset[f] = Math.max(0, flux[f] - s / c);
  }
  const acf = (lag) => { let s = 0; for (let t = 0; t + lag < frames; t++) s += onset[t] * onset[t + lag]; return s / (frames - lag); };
  const a0 = acf(0) || 1e-9;
  const minLag = Math.floor((60 * fps) / 200), maxLag = Math.ceil((60 * fps) / 55);
  const vals = []; let best = minLag, bestS = -1;
  for (let l = minLag; l <= maxLag; l++) {
    const v = acf(l); vals[l] = v;
    const bpm = (60 * fps) / l; const prior = Math.exp(-0.5 * (Math.log2(bpm / 120) / 0.9) ** 2);
    if (v * prior > bestS) { bestS = v * prior; best = l; }
  }
  let lag = best;
  if (vals[best - 1] != null && vals[best + 1] != null) {
    const y0 = vals[best - 1], y1 = vals[best], y2 = vals[best + 1]; const d = y0 - 2 * y1 + y2;
    if (d < 0) lag = best + (0.5 * (y0 - y2)) / d;
  }
  const bpm = (60 * fps) / lag;
  const pulse = clamp(vals[best] / a0);
  let peaks = 0; const thr = pct(onset, 0.9);
  for (let f = 1; f < frames - 1; f++) if (onset[f] > thr && onset[f] >= onset[f - 1] && onset[f] > onset[f + 1]) peaks++;
  const onsetRate = peaks / (frames / fps);
  // 조성: Krumhansl–Kessler 프로필 상관
  const chroma = [...chromaSum];
  let bMaj = -2, bMajK = 0, bMin = -2, bMinK = 0;
  for (let k = 0; k < 12; k++) {
    const rot = chroma.map((_, i) => chroma[(i + k) % 12]);
    const rm = pearson(rot, KK_MAJ), rn = pearson(rot, KK_MIN);
    if (rm > bMaj) { bMaj = rm; bMajK = k; } if (rn > bMin) { bMin = rn; bMinK = k; }
  }
  const isMajor = bMaj >= bMin; const tonic = isMajor ? bMajK : bMinK;
  // 1초 단위 화성 변화율·음색 변화
  const seg = Math.max(1, Math.round(fps)); const segCh = [], segCent = [];
  for (let s = 0; s + seg <= frames; s += seg) {
    const c = new Float64Array(12); let ce = 0;
    for (let f = s; f < s + seg; f++) { for (let j = 0; j < 12; j++) c[j] += chromaF[f][j]; ce += cent[f]; }
    const nrm = Math.hypot(...c) || 1; segCh.push([...c].map((v) => v / nrm)); segCent.push(ce / seg);
  }
  let hc = 0; for (let i = 1; i < segCh.length; i++) { let dot = 0; for (let j = 0; j < 12; j++) dot += segCh[i][j] * segCh[i - 1][j]; hc += 1 - dot; }
  hc = segCh.length > 1 ? hc / (segCh.length - 1) : 0;
  const cm = segCent.reduce((a, b) => a + b, 0) / (segCent.length || 1);
  const cv = Math.sqrt(segCent.reduce((a, b) => a + (b - cm) ** 2, 0) / (segCent.length || 1)) / (cm || 1);
  const loud = [...frms].filter((v) => v > -60);
  const eTot = eLow + eMid + eHigh || 1;
  return {
    bpm: +bpm.toFixed(1), pulse: +pulse.toFixed(3), onsetRate: +onsetRate.toFixed(2),
    key: tonic, mode: isMajor ? 'major' : 'minor', keyName: `${PC[tonic]} ${isMajor ? '장조' : '단조'}`,
    camelot: `${(isMajor ? CAM_MAJ : CAM_MIN)[tonic]}${isMajor ? 'B' : 'A'}`, keyR: +Math.max(bMaj, bMin).toFixed(3), modeMargin: +(bMaj - bMin).toFixed(3),
    rmsDb: +(20 * Math.log10(rms)).toFixed(1), crestDb: +(20 * Math.log10(peak / rms)).toFixed(1),
    dr: +(loud.length ? pct(loud, 0.95) - pct(loud, 0.1) : 0).toFixed(1),
    width: +(side / (mid + 1e-12)).toFixed(3), centroid: Math.round(cent.reduce((a, b) => a + b, 0) / frames),
    flatness: +(flat.reduce((a, b) => a + b, 0) / frames).toFixed(3), harmonicChange: +hc.toFixed(3), timbreVar: +cv.toFixed(3),
    low: +(eLow / eTot).toFixed(3), midE: +(eMid / eTot).toFixed(3), high: +(eHigh / eTot).toFixed(4), seconds: +(mono.length / sr).toFixed(1),
  };
}

export async function analyzeAudio(url) {
  const r = await fetch(url, { mode: 'cors', credentials: 'omit', referrerPolicy: 'no-referrer' });
  if (!r.ok) throw new Error('preview ' + r.status);
  const buf = await r.arrayBuffer();
  const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const ctx = new Ctx(2, 44100, 44100);
  const ab = await ctx.decodeAudioData(buf);
  const L = ab.getChannelData(0), R = ab.numberOfChannels > 1 ? ab.getChannelData(1) : L;
  await sleep(0);
  return computeFeatures(L, R, ab.sampleRate);
}

/* ───────────── 느낌(무드) ───────────── */
export function moodOf(f, genres) {
  const energy = clamp((f.rmsDb + 30) / 20);
  const tempo = clamp((f.bpm - 65) / 105);
  const arousal = clamp(0.5 * energy + 0.25 * tempo + 0.25 * clamp(f.onsetRate / 5));
  const major = 1 / (1 + Math.exp(-f.modeMargin * 9));
  const bright = clamp((f.centroid - 900) / 2600);
  const valence = clamp(0.5 * major + 0.3 * bright + 0.2 * tempo);
  const acousticAudio = clamp(0.55 * (1 - clamp((f.flatness - 0.08) / 0.3)) + 0.25 * (1 - clamp(f.pulse / 0.6)) + 0.2 * (1 - clamp(f.high / 0.12)));
  const gx = genreAxis(genres);
  const x = clamp(gx == null ? 1 - 2 * acousticAudio : 0.65 * gx + 0.35 * (1 - 2 * acousticAudio), -1, 1);
  const y = clamp(2 * valence - 1, -1, 1);
  const words = [];
  if (arousal > 0.62) words.push(...(valence > 0.55 ? (bright > 0.55 ? ['신나는', '청량한'] : ['신나는', '당당한']) : ['강렬한', '긴장감 있는']));
  else if (arousal < 0.4) words.push(...(valence > 0.55 ? ['포근한', '여유로운'] : (f.width > 0.25 ? ['몽환적인', '아련한'] : ['쓸쓸한', '아련한'])));
  else words.push(valence > 0.55 ? '산뜻한' : valence < 0.4 ? '차분하게 가라앉은' : '담백한');
  const tex = [];
  if (f.pulse > 0.45) tex.push('비트가 또렷함');
  if (f.width > 0.3) tex.push('공간감이 넓음');
  if (f.width < 0.03) tex.push('거의 모노에 가까운 좁은 무대');
  if (f.crestDb < 8.5) tex.push('라우드하게 꽉 눌러 담은 믹스');
  if (f.dr > 12) tex.push('강약 대비가 살아 있음');
  if (acousticAudio > 0.6) tex.push('어쿠스틱한 질감');
  if (f.harmonicChange > 0.28) tex.push('코드 움직임이 잦음');
  if (f.harmonicChange < 0.08) tex.push('한 화성에 오래 머무름');
  if (f.centroid < 1300) tex.push('어둡고 따뜻한 톤');
  if (f.centroid > 3300) tex.push('밝고 날카로운 톤');
  const quad = y >= 0 ? (x < 0 ? '청춘 기타팝' : '화사한 댄스') : (x < 0 ? '서정의 발라드' : '밤의 R&B');
  return { arousal: +arousal.toFixed(3), valence: +valence.toFixed(3), energy: +energy.toFixed(3), acoustic: +acousticAudio.toFixed(3), x: +x.toFixed(3), y: +y.toFixed(3), words, texture: tex, quad };
}

/* ───────────── 엄격 채점(music-taste-curator 루브릭 v2) ─────────────
   8축 고정 가중치: 작22·편22·연12·가8·혁10·통8·유10·미8.
   - 측정 가능한 축(작곡의 화성 측면, 편곡·사운드)만 오디오로 계산.
   - 근거 상한 규칙: 출처 검증 없는 자동 판단은 어떤 축도 4점을 넘지 못함(작곡은 멜로디를 못 들으니 3.5 상한).
   - 측정 불가 축은 보수적 기본값 2.5(평범과 탄탄 사이) → 사용자가 직접 채점하면 대체. */
export const AXES = [
  { k: '작', name: '작곡', w: 22, hint: '멜로디 각인성 · 화성 진행의 의외성과 필연성 · 구조 설계' },
  { k: '편', name: '편곡·사운드', w: 22, hint: '악기·레이어 배치 · 프로덕션 선택 · 믹스의 공간 설계' },
  { k: '연', name: '연주·보컬', w: 12, hint: '해석력 · 음색 활용 · 프레이징' },
  { k: '가', name: '가사·서사', w: 8, hint: '문장의 힘 · 은유 · 사운드와의 정서 일치' },
  { k: '혁', name: '혁신', w: 10, hint: '발매 시점 기준으로 실제로 새로웠는가' },
  { k: '통', name: '통일성', w: 8, hint: '도입-전개-마무리의 일관성(앨범: 흐름)' },
  { k: '유', name: '유레카', w: 10, hint: '처음 듣고 각인되는 결정적 순간을 섹션으로 짚을 수 있나' },
  { k: '미', name: '미적 일체감', w: 8, hint: '사운드·커버·MV·콘셉트가 같은 문법을 공유하나' },
];
export const ANCHORS = ['해당 요소가 곡을 해침', '약점이 눈에 띔', '평범·관습적', '탄탄함, 특출나진 않음', '장르 상위 10%', '장르의 교본·정점'];
const band = (v, lo, hi, soft) => (v >= lo && v <= hi ? 1 : clamp(1 - (v < lo ? lo - v : v - hi) / soft));

export function autoAxes(f, gclass) {
  const dr = { electronic: [4.5, 10], hiphop: [4.5, 10], rock: [5.5, 11], acoustic: [7, 18], other: [5.5, 13] }[gclass] || [5.5, 13];
  const crestMin = gclass === 'electronic' || gclass === 'hiphop' ? 7 : 8.5;
  const parts = {
    dynamics: band(f.dr, dr[0], dr[1], 3),
    crest: clamp((f.crestDb - (crestMin - 3)) / 3),
    balance: Math.min(band(f.low, 0.12, 0.82, 0.12), band(f.high, 0.004, 0.2, 0.05)),
    width: f.width < 0.02 ? 0.45 : band(f.width, 0.03, 0.65, 0.4),
    variation: band(f.timbreVar, 0.06, 0.45, 0.12),
    harmony: band(f.harmonicChange, 0.1, 0.3, 0.12),
    tonal: gclass === 'electronic' || gclass === 'hiphop' ? band(f.keyR, 0.35, 1, 0.3) : band(f.keyR, 0.5, 1, 0.35),
  };
  const 편 = 0.8 + 3.2 * (0.28 * parts.dynamics + 0.17 * parts.crest + 0.2 * parts.balance + 0.15 * parts.width + 0.2 * parts.variation);
  const 작 = 1.0 + 2.5 * (0.55 * parts.harmony + 0.45 * parts.tonal);
  return { axes: { 작: +Math.min(3.5, 작).toFixed(2), 편: +Math.min(4, 편).toFixed(2) }, parts };
}

export const DEFAULT_UNMEASURED = 2.5;
export function musicScore(axes, inst = false) {
  let s = 0, tot = 0;
  for (const a of AXES) {
    if (inst && a.k === '가') continue;
    const v = axes[a.k] ?? DEFAULT_UNMEASURED;
    s += (v / 5) * a.w; tot += a.w;
  }
  return +((s * 100) / tot).toFixed(1);
}
export function grade(score) {
  if (score >= 90) return { g: 'S', t: '교본급' };
  if (score >= 80) return { g: 'A', t: '뚜렷하게 뛰어남' };
  if (score >= 70) return { g: 'B', t: '탄탄함 이상' };
  if (score >= 60) return { g: 'C', t: '탄탄함' };
  if (score >= 50) return { g: 'D', t: '평범' };
  return { g: 'F', t: '약점이 큼' };
}

/* 특징 벡터·유사도(통일성·취향 적합도 공용) */
export function vec(f, m) {
  return [clamp((f.bpm - 60) / 120), m.energy, m.valence, m.acoustic, clamp(f.width / 0.6), clamp(f.dr / 16), clamp(f.harmonicChange / 0.4), (m.x + 1) / 2];
}
export function cohesion(vectors) { // 0~1, 앨범·아티스트 일관성
  if (vectors.length < 2) return null;
  let d = 0, c = 0;
  for (let i = 0; i < vectors.length; i++) for (let j = i + 1; j < vectors.length; j++) {
    d += Math.sqrt(vectors[i].reduce((s, v, k) => s + (v - vectors[j][k]) ** 2, 0) / vectors[i].length); c++;
  }
  return clamp(1 - (d / c) / 0.45);
}

/* ───────────── 곡 분석 파이프라인 ───────────── */
export async function analyzeTrack(tr, onStep = () => {}) {
  const out = { at: Date.now(), errors: [] };
  onStep('Deezer에서 곡 정보·BPM 확인');
  const dz = await deezerDetail(tr).catch((e) => { out.errors.push('Deezer 상세 조회 실패'); return null; });
  out.deezer = dz;
  onStep('30초 미리듣기 신호 분석');
  const urls = [tr.preview, tr.previewAlt].filter(Boolean);
  for (const u of urls) {
    try { out.features = await analyzeAudio(u); break; } catch (e) { /* 다음 소스 */ }
  }
  if (!out.features && tr.appleId && !tr.preview) { /* 안전장치 */ }
  if (!out.features) out.errors.push('미리듣기 오디오를 분석하지 못함(미리듣기 없음 또는 브라우저 차단)');
  onStep('MusicBrainz에서 작곡·작사·프로듀서 크레딧 조회');
  const mbr = await musicBrainz(tr, dz?.isrc).catch(() => { out.errors.push('MusicBrainz 조회 실패'); return { credits: [], tags: [], mbUrl: '' }; });
  out.credits = mbr.credits; out.mbUrl = mbr.mbUrl;
  if (!tr.year && mbr.firstRelease) tr.year = yearOf(mbr.firstRelease);
  out.genres = rankGenres({ tags: mbr.tags, deezer: dz?.genres || [], apple: tr.genre });
  out.gclass = genreClass(out.genres);
  if (out.features) {
    out.mood = moodOf(out.features, out.genres);
    const a = autoAxes(out.features, out.gclass);
    out.auto = a.axes; out.parts = a.parts;
    out.vec = vec(out.features, out.mood);
  } else {
    out.auto = {};
  }
  out.bpmRef = dz?.bpm || 0;
  return out;
}

/* ───────────── 앨범·아티스트 파이프라인 ───────────── */
const KEEP_ROLES = new Set(['작곡', '작사', '작사·작곡', '편곡', '프로듀서']);

async function mbAlbum(al) {
  const q = `releasegroup:"${luc(al.title)}" AND artist:"${luc(primaryArtist(al.artist))}"`;
  const s = await mb(`release-group?query=${enc(q)}&limit=5`);
  const rg = (s['release-groups'] || []).find((r) => dedupeKey(r.title) === dedupeKey(al.title)) || (s['release-groups'] || [])[0];
  if (!rg) return { tags: [], credits: [], mbUrl: '' };
  const g = await mb(`release-group/${rg.id}?inc=genres+tags+releases+artist-credits`);
  const tagW = new Map();
  const add = (list, w) => (list || []).forEach((t) => tagW.set(t.name.toLowerCase(), (tagW.get(t.name.toLowerCase()) || 0) + w * Math.max(1, t.count || 1)));
  add(g.genres, 3); add(g.tags, 1.2);
  const artistId = g['artist-credit']?.[0]?.artist?.id;
  if (artistId) { const a = await mb(`artist/${artistId}?inc=genres+tags`).catch(() => null); if (a) { add(a.genres, 1); add(a.tags, 0.4); } }
  const credits = new Map();
  const relId = (g.releases || []).find((r) => r.status === 'Official')?.id || (g.releases || [])[0]?.id;
  if (relId) {
    const rel = await mb(`release/${relId}?inc=recordings+recording-level-rels+work-rels+work-level-rels+artist-rels`).catch(() => null);
    const bump = (role, name) => { const ko = ROLE_KO[role] || role; if (!KEEP_ROLES.has(ko) || !name) return; const k = ko + '|' + name; credits.set(k, (credits.get(k) || 0) + 1); };
    for (const r of rel?.relations || []) if (r.artist) bump(r.type, r.artist.name);
    for (const m of rel?.media || []) for (const t of m.tracks || []) {
      for (const r of t.recording?.relations || []) {
        if (r.artist) bump(r.type, r.artist.name);
        if (r.work) for (const w of r.work.relations || []) if (w.artist) bump(w.type, w.artist.name);
      }
    }
  }
  return {
    tags: [...tagW.entries()].map(([name, w]) => ({ name, w })),
    credits: [...credits.entries()].map(([k, n]) => ({ role: k.split('|')[0], name: k.split('|')[1], n })).sort((a, b) => b.n - a.n),
    mbUrl: `https://musicbrainz.org/release-group/${rg.id}`, firstRelease: rg['first-release-date'],
  };
}

async function mbArtistTags(name) {
  const s = await mb(`artist?query=${enc(`artist:"${luc(name)}"`)}&limit=5`);
  const a = (s.artists || []).find((x) => lite(x.name) === lite(name) || (x.aliases || []).some((al) => lite(al.name) === lite(name))) || (s.artists || [])[0];
  if (!a) return { tags: [], mbUrl: '' };
  const d = await mb(`artist/${a.id}?inc=genres+tags`);
  const tags = [...(d.genres || []).map((g) => ({ name: g.name.toLowerCase(), w: 3 * Math.max(1, g.count || 1) })), ...(d.tags || []).map((g) => ({ name: g.name.toLowerCase(), w: Math.max(1, g.count || 1) }))];
  return { tags, mbUrl: `https://musicbrainz.org/artist/${a.id}`, country: d.country, begin: d['life-span']?.begin };
}

async function analyzeSet(tracks, genres, gclass, max, onStep) {
  const usable = tracks.filter((t) => t.preview).slice(0, max);
  const out = [];
  for (let i = 0; i < usable.length; i++) {
    const t = usable[i];
    onStep(`수록곡 신호 분석 ${i + 1}/${usable.length}`);
    try {
      const f = await analyzeAudio(t.preview);
      const m = moodOf(f, genres);
      const auto = autoAxes(f, gclass).axes;
      out.push({ title: t.title, artist: t.artist, preview: t.preview, artwork: t.artwork, deezerId: t.deezerId, appleId: t.appleId, durationMs: t.durationMs, features: f, mood: m, auto, score: musicScore(auto), vec: vec(f, m) });
    } catch { out.push({ title: t.title, artist: t.artist, preview: t.preview, artwork: t.artwork, deezerId: t.deezerId, failed: true }); }
  }
  return out;
}
const meanVec = (vs) => (vs.length ? vs[0].map((_, k) => vs.reduce((s, v) => s + v[k], 0) / vs.length) : null);
const avg = (a) => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0);

export async function analyzeAlbum(al, onStep = () => {}) {
  onStep('수록곡 불러오기');
  const tracks = await albumTracks(al);
  onStep('MusicBrainz에서 앨범 장르·크레딧 조회');
  const m = await mbAlbum(al).catch(() => ({ tags: [], credits: [], mbUrl: '' }));
  if (!al.year && m.firstRelease) al.year = yearOf(m.firstRelease);
  const genres = rankGenres({ tags: m.tags, deezer: al.genres || [], apple: al.genre });
  const gclass = genreClass(genres);
  const set = await analyzeSet(tracks, genres, gclass, 10, onStep);
  const ok = set.filter((t) => !t.failed);
  const vecs = ok.map((t) => t.vec);
  const coh = cohesion(vecs);
  return {
    kind: 'album', at: Date.now(), tracks: tracks.map((t) => ({ title: t.title, artist: t.artist, preview: t.preview, artwork: t.artwork, deezerId: t.deezerId, appleId: t.appleId, durationMs: t.durationMs, album: al.title })),
    analyzed: set, genres, gclass, credits: m.credits, mbUrl: m.mbUrl, cohesion: coh, label: al.label,
    auto: { 통: coh == null ? undefined : +Math.min(4, 1 + 3 * coh).toFixed(2) }, vecMean: meanVec(vecs),
    mood: ok.length ? { x: avg(ok.map((t) => t.mood.x)), y: avg(ok.map((t) => t.mood.y)), arousal: avg(ok.map((t) => t.mood.arousal)), valence: avg(ok.map((t) => t.mood.valence)) } : null,
    errors: ok.length ? [] : ['수록곡 미리듣기를 분석하지 못함'],
  };
}

export async function analyzeArtist(ar, onStep = () => {}) {
  onStep('대표곡 불러오기(Deezer)');
  const tracks = await artistTopTracks(ar);
  onStep('MusicBrainz에서 아티스트 장르 조회');
  const m = await mbArtistTags(ar.title).catch(() => ({ tags: [], mbUrl: '' }));
  const genres = rankGenres({ tags: m.tags, apple: ar.genre });
  const gclass = genreClass(genres);
  const set = await analyzeSet(tracks, genres, gclass, 6, onStep);
  const ok = set.filter((t) => !t.failed);
  const vecs = ok.map((t) => t.vec);
  const coh = cohesion(vecs);
  return {
    kind: 'artist', at: Date.now(), tracks: tracks.map((t) => ({ title: t.title, artist: t.artist, album: t.album, preview: t.preview, artwork: t.artwork, deezerId: t.deezerId, durationMs: t.durationMs })),
    analyzed: set, genres, gclass, mbUrl: m.mbUrl, country: m.country, begin: m.begin, cohesion: coh,
    auto: { 통: coh == null ? undefined : +Math.min(4, 1 + 3 * coh).toFixed(2) }, vecMean: meanVec(vecs),
    mood: ok.length ? { x: avg(ok.map((t) => t.mood.x)), y: avg(ok.map((t) => t.mood.y)), arousal: avg(ok.map((t) => t.mood.arousal)), valence: avg(ok.map((t) => t.mood.valence)) } : null,
    errors: ok.length ? [] : ['대표곡 미리듣기를 분석하지 못함'],
  };
}

/* 앨범: 상위 3곡 평균 50% + 통일성 30% + 미적 일체감 20% (루브릭 '앨범' 규칙)
   아티스트: 대표곡 평균 55% + 상위 3곡 30% + 일관성 15%, 대표작 1곡 의존이면 감점 */
export function setScore(kind, an, manual = {}) {
  const scores = (an.analyzed || []).filter((t) => !t.failed).map((t) => t.score).sort((a, b) => b - a);
  if (!scores.length) return null;
  const top3 = avg(scores.slice(0, 3));
  const tong = manual.통 ?? an.auto?.통 ?? DEFAULT_UNMEASURED;
  if (kind === 'album') {
    const mi = manual.미 ?? DEFAULT_UNMEASURED;
    return { score: +(0.5 * top3 + 0.3 * (tong / 5) * 100 + 0.2 * (mi / 5) * 100).toFixed(1), top3: +top3.toFixed(1), tong, mi, n: scores.length };
  }
  const mean = avg(scores);
  const penalty = Math.max(0, scores[0] - mean - 10) * 0.5;
  return { score: +(0.55 * mean + 0.3 * top3 + 0.15 * (tong / 5) * 100 - penalty).toFixed(1), top3: +top3.toFixed(1), mean: +mean.toFixed(1), tong, penalty: +penalty.toFixed(1), n: scores.length };
}

export async function relatedArtists(name, id) {
  if (!id) {
    const s = await deezer(`search/artist?q=${enc(name)}&limit=3`).catch(() => null);
    const best = (s?.data || []).find((a) => lite(a.name) === lite(name)) || (s?.data || [])[0];
    if (!best) return [];
    id = best.id;
  }
  const d = await deezer(`artist/${id}/related?limit=12`).catch(() => null);
  return (d?.data || []).map(fromDeezerArtist);
}
