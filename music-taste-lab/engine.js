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
      for (let attempt = 0; attempt < 4; attempt++) {
        const wait = Math.max(0, mbLast + 1250 - Date.now());
        if (wait) await sleep(wait);
        mbLast = Date.now();
        let r;
        // 제한(503) 응답에는 CORS 헤더가 없어 브라우저가 네트워크 오류로 던짐 → 예외도 재시도
        try { r = await fetch(`https://musicbrainz.org/ws/2/${path}${path.includes('?') ? '&' : '?'}fmt=json`, { headers: { Accept: 'application/json' } }); }
        catch { await sleep(1500 * (attempt + 1)); mbLast = Date.now(); continue; }
        if (r.status === 503 || r.status === 429) { await sleep(1500 * (attempt + 1)); mbLast = Date.now(); continue; }
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
const CJK = /[\u3131-\uD79D\u3040-\u30FF\u4E00-\u9FFF]/;
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
  // 원곡이 아닌 버전(커버·피아노·노래방 등)은 검색어에 그 단어가 없으면 감점
  const variant = /\b(piano|instrumental|inst\.?|karaoke|cover|lullaby|music box|8[- ]?bit|tribute|sped up|slowed|nightcore|mr)\b|커버|피아노|연주곡|오르골|노래방/i;
  if (variant.test(title || '') && !variant.test(q)) s -= 32;
  // 재업로드 패턴: 제목 안에 '가수 - 곡'을 적은 다른 사람의 업로드(예: "뉴진스 (NewJeans) - Hype Boy" / jxng__ssxng)
  if (artist && /\s[-–]\s/.test(title || '') && na && !nq.includes(na) && !na.includes(nq)) s -= 60;
  if (/__|_{1}[a-z0-9]+_/i.test(artist || '')) s -= 25;
  return s;
}
const orderBonus = (idx, n) => (1 - idx / Math.max(n, 1)) * 30; // 각 서비스가 매긴 순서를 보조 신호로

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
    deezerAlbumId: t.album?.id, deezerArtistId: t.artist?.id, durationMs: (t.duration || 0) * 1000, genre: '', explicit: !!t.explicit_lyrics, rank: t.rank || 0,
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
  return { kind: 'artist', title: a.name, artist: a.name, artwork: a.picture_xl || a.picture_big || '', deezerId: a.id, deezerUrl: a.link, genre: '' };
}

export function itemKey(it) {
  return it.kind === 'artist'
    ? `artist|${dedupeKey(it.title)}`
    : `${it.kind}|${dedupeKey(it.title)}|${dedupeKey(primaryArtist(it.artist))}`;
}

// 정식 발매가 아닌 것(노래방·커버·속도 변형·자장가·컴필레이션 업로드 등)은 검색어가 그런 버전을 찾을 때만 보여 준다
const UNOFFICIAL = /\b(karaoke|in the style of|originally performed|made famous|tribute|lullaby|music box|8[- ]?bit|sped up|slowed|nightcore|ringtone|cover version|piano cover|instrumental cover|reverb version)\b|노래방|가라오케|자장가|오르골|\bMR\b|커버|원곡가수|原曲歌手|カラオケ|オルゴール/i;
const UNOFFICIAL_ARTIST = /(karaoke|tribute|lullaby|piano guy|music box|cover band|cover hits|sleep music|baby music|playground4music|歌っちゃ王)|__/i;
export function isUnofficial(it, q = '') {
  if (UNOFFICIAL.test(q)) return false;
  if (UNOFFICIAL.test(it.title || '') || UNOFFICIAL.test(it.album || '')) return true;
  if (it.kind !== 'artist' && UNOFFICIAL_ARTIST.test(it.artist || '')) return true;
  if (it.kind === 'artist' && UNOFFICIAL_ARTIST.test(it.title || '')) return true;
  if (it.kind === 'album' && (/^various artists$/i.test(it.artist || '') || it.recordType === 'compile')) return true;
  return false;
}
function merge(lists, q, alts = []) {
  const map = new Map(), idx = new Map();
  for (const { items, src } of lists) {
    items.forEach((raw, i) => {
      if (!raw || !raw.title || isUnofficial(raw, q)) return;
      const it = { ...raw, srcs: [src] };
      it.key = itemKey(it);
      const who = it.kind === 'artist' ? '' : it.artist;
      const text = Math.max(relevance(q, it.title, who), ...alts.map((a) => relevance(a, it.title, who))) + (it.boost || 0);
      it.text = Math.max(it.text || 0, text);
      const score = text + orderBonus(i, items.length);
      const viaId = it.deezerId && idx.get('dz' + it.deezerId);
      const prev = viaId ? map.get(viaId) : map.get(it.key);
      if (!prev) {
        it.rel = score; map.set(it.key, it);
        if (it.deezerId) idx.set('dz' + it.deezerId, it.key);
        if (it.altTitle) map.set(itemKey({ ...it, title: it.altTitle }), it);
        return;
      }
      // 같은 곡이 두 서비스에 모두 있으면 하나로 합치고 정확도 가산
      for (const [k, v] of Object.entries(it)) if (v && !prev[k]) prev[k] = v;
      if (src === 'apple' && it.artwork) prev.artwork = it.artwork;
      prev.text = Math.max(prev.text || 0, text);
      if (!prev.srcs.includes(src)) { prev.srcs.push(src); prev.rel = Math.max(prev.rel, score) + (prev.text >= 30 ? 18 : 0); }
      else prev.rel = Math.max(prev.rel, score);
    });
  }
  // 같은 곡이 서비스마다 한글/영문 아티스트명으로 갈린 경우(검정치마 ↔ The Black Skirts): 제목·길이가 같으면 병합
  const list = [...new Set(map.values())];
  const out = [];
  for (const it of list) {
    const twin = it.kind === 'track' && out.find((o) => o.kind === 'track' && dedupeKey(o.title) === dedupeKey(it.title)
      && o.durationMs && it.durationMs && Math.abs(o.durationMs - it.durationMs) <= 2500
      && CJK.test(o.artist || '') !== CJK.test(it.artist || ''));
    if (!twin) { out.push(it); continue; }
    for (const [k, v] of Object.entries(it)) if (v && !twin[k]) twin[k] = v;
    if (it.srcs.includes('apple') && it.artwork) twin.artwork = it.artwork;
    if (CJK.test(it.artist || '') && !CJK.test(twin.artist || '')) twin.artist = it.artist;
    twin.srcs = [...new Set([...twin.srcs, ...it.srcs])];
    twin.rel = Math.max(twin.rel, it.rel) + 18;
  }
  return out.sort((a, b) => b.rel - a.rel);
}

const enc = encodeURIComponent;
const apple = (params) => jsonp(`https://itunes.apple.com/search?${params}`).then((d) => d.results || []);
const deezer = (path) => jsonp(`https://api.deezer.com/${path}${path.includes('?') ? '&' : '?'}output=jsonp`).then((d) => {
  if (d && d.error) throw new Error('deezer ' + (d.error.message || ''));
  return d;
});
const safe = (p) => p.then((v) => ({ ok: true, v }), (e) => ({ ok: false, e }));

// 한글로 적은 외래어 곡명(디토 ↔ Ditto)을 맞추기 위한 간이 로마자 변환·발음 키
const H_I = ['g','kk','n','d','tt','r','m','b','pp','s','ss','','j','jj','ch','k','t','p','h'];
const H_M = ['a','ae','ya','yae','eo','e','yeo','ye','o','wa','wae','oe','yo','u','wo','we','wi','yu','eu','ui','i'];
const H_F = ['','g','kk','gs','n','nj','nh','d','l','lg','lm','lb','ls','lt','lp','lh','m','b','bs','s','ss','ng','j','ch','k','t','p','h'];
function romanize(s) {
  let o = '';
  for (const ch of s || '') {
    const c = ch.charCodeAt(0) - 0xAC00;
    if (c >= 0 && c < 11172) o += H_I[Math.floor(c / 588)] + H_M[Math.floor((c % 588) / 28)] + H_F[c % 28];
    else o += ch;
  }
  return o;
}
function phon(s) {
  return romanize((s || '').normalize('NFKC').toLowerCase()).replace(/[^a-z]/g, '')
    .replace(/eo/g, 'o').replace(/eu/g, 'u').replace(/ae/g, 'e').replace(/ph/g, 'p').replace(/th/g, 't').replace(/ck/g, 'k')
    .replace(/f/g, 'p').replace(/v/g, 'b').replace(/[cq]/g, 'k').replace(/x/g, 'ks').replace(/z/g, 'j').replace(/y/g, 'i').replace(/l/g, 'r')
    .replace(/(.)\1+/g, '$1');
}
function lev(a, b) {
  const d = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) { let p = d[0]; d[0] = i; for (let j = 1; j <= b.length; j++) { const t = d[j]; d[j] = Math.min(d[j] + 1, d[j - 1] + 1, p + (a[i - 1] === b[j - 1] ? 0 : 1)); p = t; } }
  return d[b.length];
}
export function phonSim(a, b) { const x = phon(a), y = phon(b); if (!x || !y) return 0; return 1 - lev(x, y) / Math.max(x.length, y.length); }

// 검색 v2
// - Apple: 한국 스토어 검색이 (최소한 해외 IP에서) 0건을 돌려줘 KR·US를 동시에 조회, 일본어가 있으면 JP도 추가
// - Deezer: 곡·앨범·아티스트
// - 한글·일본어 검색어: MusicBrainz로 가수 이름을 연결(뉴진스→NewJeans)하고, 원어 곡명→ISRC→Deezer 정확한 음원으로 보정(refine)
const JP = /[぀-ヿ一-鿿]/;
const appleSongs = (term, country, limit) => apple(`term=${enc(term)}&media=music&entity=song&limit=${limit}&country=${country}`).catch(() => []);
function fromAppleSongs(list) { return list.filter((r) => r.kind === 'song' || r.wrapperType === 'track').map(fromAppleSong); }
function albumsFromSongs(list) {
  return list.map((r) => ({ kind: 'album', title: r.collectionName, artist: r.collectionArtistName || r.artistName, year: yearOf(r.releaseDate), artwork: art600(r.artworkUrl100), appleUrl: r.collectionViewUrl, appleId: r.collectionId, genre: r.primaryGenreName }));
}
function pickTop(tracks, albums, artists) {
  return [tracks[0], artists[0], albums[0]].filter(Boolean).sort((a, b) => (b.rel + (b.kind === 'artist' ? 6 : 0)) - (a.rel + (a.kind === 'artist' ? 6 : 0)))[0] || null;
}

export function search(q, tab = 'all') {
  q = q.trim();
  return cached(`s2:${tab}:${q.toLowerCase()}`, 10 * 6e4, async () => {
    const term = enc(q);
    const wantT = tab === 'all' || tab === 'track', wantA = tab === 'all' || tab === 'album', wantR = tab === 'all' || tab === 'artist';
    const lim = tab === 'all' ? 25 : 50;
    const J = {};
    if (wantT) {
      J.aKR = safe(appleSongs(q, 'KR', lim)); J.aUS = safe(appleSongs(q, 'US', lim));
      if (JP.test(q) && !/[ㄱ-힝]/.test(q)) J.aJP = safe(appleSongs(q, 'JP', 20));
      J.dT = safe(deezer(`search?q=${term}&limit=${lim}`).then((d) => d.data || []));
    }
    if (wantA) {
      if (tab === 'album') { J.aAlK = safe(apple(`term=${term}&media=music&entity=album&limit=25&country=KR`)); J.aAlU = safe(apple(`term=${term}&media=music&entity=album&limit=25&country=US`)); }
      J.dA = safe(deezer(`search/album?q=${term}&limit=${tab === 'album' ? 30 : 12}`).then((d) => d.data || []));
    }
    if (wantR) {
      if (tab === 'artist') { J.aArK = safe(apple(`term=${term}&media=music&entity=musicArtist&limit=10&country=KR`)); J.aArU = safe(apple(`term=${term}&media=music&entity=musicArtist&limit=10&country=US`)); }
      J.dR = safe(deezer(`search/artist?q=${term}&limit=${tab === 'artist' ? 20 : 8}`).then((d) => d.data || []));
    }
    const keys = Object.keys(J);
    const R = Object.fromEntries((await Promise.all(keys.map((k) => J[k]))).map((v, i) => [keys[i], v]));
    const val = (k) => (R[k] && R[k].ok ? R[k].v : []);
    const failed = [...new Set(keys.filter((k) => R[k] && !R[k].ok).map((k) => (k[0] === 'a' ? 'Apple Music' : 'Deezer')))];
    const appleRaw = [...val('aKR'), ...val('aJP'), ...val('aUS')];
    const res = {
      q, tab, failed,
      raw: { apple: appleRaw, dT: val('dT'), dA: val('dA'), dR: val('dR'), aAl: [...val('aAlK'), ...val('aAlU')], aAr: [...val('aArK'), ...val('aArU')] },
    };
    build(res, [], []);
    if (!res.tracks.length && !res.albums.length && !res.artists.length && failed.length && keys.every((k) => !R[k].ok)) throw new Error('all-failed');
    return res;
  });
}

// 결과 목록 조립(보정 단계에서 추가 소스·별칭 검색어와 함께 다시 호출)
function build(res, extraTracks, alts, extraArtists = []) {
  const { raw, q, tab } = res;
  res.tracks = merge([
    { src: 'mb', items: extraTracks },
    { src: 'apple', items: fromAppleSongs(raw.apple) },
    { src: 'deezer', items: raw.dT.map(fromDeezerTrack) },
  ], q, alts);
  res.albums = merge([
    { src: 'apple', items: raw.aAl.map(fromAppleAlbum).concat(tab === 'all' ? albumsFromSongs(raw.apple) : []) },
    { src: 'deezer', items: raw.dA.map(fromDeezerAlbum) },
  ], q, alts);
  res.artists = merge([
    { src: 'deezer', items: extraArtists },
    { src: 'apple', items: raw.aAr.map(fromAppleArtist) },
    { src: 'deezer', items: raw.dR.map(fromDeezerArtist) },
  ], q, alts);
  res.top = pickTop(res.tracks, res.albums, res.artists);
  return res;
}

// 한글·일본어 검색어 보정: 결과를 먼저 보여 준 뒤 호출해 다시 정렬한 결과를 돌려준다
export function needsRefine(q) { return CJK.test(q); }
export function refine(res) {
  return cached(`rf:${res.tab}:${res.q.toLowerCase()}`, 10 * 6e4, async () => {
    const q = res.q, nq = lite(q);
    const out = { ...res };
    let artist = null, alias = '';
    const A = await mb(`artist?query=${enc(luc(q))}&limit=6`).catch(() => null);
    for (const c of A?.artists || []) {
      if ((c.score ?? 0) < 70) continue;
      const names = [c.name, c['sort-name'], ...(c.aliases || []).map((x) => x.name)].filter(Boolean);
      const hit = names.filter((n) => lite(n).length >= 2 && nq.includes(lite(n))).sort((x, y) => lite(y).length - lite(x).length)[0];
      if (hit) { artist = c; alias = hit; break; }
    }
    const rest = artist ? q.toLowerCase().split(alias.toLowerCase()).join(' ').replace(/\s+/g, ' ').trim() : q;
    const extraT = [], extraR = [], alts = [];
    if (artist) {
      alts.push(`${artist.name} ${rest}`.trim());
      // 영문 별칭(잔나비 → JANNABI)도 대조해 서비스마다 다른 표기를 같은 가수로 인식
      for (const al of (artist.aliases || []).map((x) => x.name).filter((n) => /^[\x20-\x7E]+$/.test(n)).slice(0, 3)) alts.push(`${al} ${rest}`.trim());
    }
    // 원어 곡명 → ISRC → Deezer 음원
    const rq = artist ? (rest ? `recording:(${luc(rest)}) AND arid:${artist.id}` : '') : `recording:(${luc(q)}) OR (recording:(${luc(q)}) AND artist:(${luc(q)}))`;
    if (rq) {
      const R = await mb(`recording?query=${enc(rq)}&limit=8`).catch(() => null);
      const want = lite(artist ? rest : q);
      const okTitle = (r) => (r.score ?? 0) >= 85 && (want.includes(lite(r.title)) || lite(r.title).includes(want));
      const all = (R?.recordings || []).filter(okTitle);
      const recs = all.filter((r) => r.isrcs?.length).slice(0, 3);
      // ISRC가 없는 곡: 앨범 바코드 → Deezer 앨범(UPC) → 같은 트랙 번호로 연결
      if (!recs.length && all.length) {
        const r = all[0]; const rel = (r.releases || []).find((x) => x.media?.[0]) || (r.releases || [])[0];
        const pos = rel?.media?.[0]?.['track-offset'];
        if (rel && pos != null) {
          const L = await mb(`release/${rel.id}`).catch(() => null);
          if (L?.barcode) {
            const al = await deezer(`album/upc:${enc(L.barcode)}`).catch(() => null);
            const t = al?.tracks?.data?.[pos];
            if (t) {
              const it = fromDeezerTrack({ ...t, album: { id: al.id, title: al.title, cover_xl: al.cover_xl } });
              it.altTitle = it.title; it.title = r.title; it.boost = 90; it.year = yearOf(al.release_date);
              extraT.push(it); alts.push(`${artist?.name || ''} ${r.title}`.trim());
            }
          }
        }
      }
      const got = await Promise.all(recs.map((r) => deezer(`track/isrc:${enc(r.isrcs[0])}`).then((t) => ({ r, t })).catch(() => null)));
      for (const g of got) {
        if (!g || !g.t?.id) continue;
        const it = fromDeezerTrack(g.t);
        it.altTitle = it.title; it.title = g.r.title; // 원어 곡명으로 표시
        it.boost = 90; it.isrc = g.r.isrcs[0];
        extraT.push(it);
        alts.push(`${g.r['artist-credit']?.[0]?.name || ''} ${g.r.title}`.trim());
      }
    }
    // 가수가 잡히면 그 가수의 Deezer 인기곡·프로필도 후보에 넣는다(예: '뉴진스 디토' → NewJeans 인기곡 중 Ditto)
    if (artist) {
      const S = await deezer(`search/artist?q=${enc(artist.name)}&limit=5`).catch(() => null);
      const da = (S?.data || []).find((x) => lite(x.name) === lite(artist.name)) || null;
      if (da) {
        const ar = fromDeezerArtist(da); ar.boost = rest ? 20 : 120; extraR.push(ar);
        const top = await deezer(`artist/${da.id}/top?limit=20`).catch(() => null);
        const list = top?.data || [];
        const sims = list.map((t) => (rest ? phonSim(rest, t.title_short || t.title) : 0));
        const best = Math.max(0, ...sims);
        list.forEach((t, i) => {
          const it = fromDeezerTrack(t);
          it.boost = rest ? (sims[i] === best && best >= 0.5 ? 110 : -40) : 60 - i * 2;
          extraT.push(it);
        });
      }
    }
    build(out, extraT, alts, extraR);
    // 제목에 그 가수 이름을 붙인 다른 사람의 업로드(커버·리믹스·로파이 버전)는 크게 감점
    if (artist) {
      const an = lite(artist.name), al = lite(alias);
      for (const t of out.tracks) {
        const ta = lite(primaryArtist(t.artist));
        if (ta !== an && ta !== al && (lite(t.title).includes(al) || lite(t.title).includes(an))) t.rel -= 120;
      }
      out.tracks.sort((a, b) => b.rel - a.rel);
      out.top = rest && out.tracks[0] ? out.tracks[0] : pickTop(out.tracks, out.albums, out.artists); // 곡명까지 입력하면 곡을 최상위로
    }
    return out;
  });
}

// 붙여넣기·샘플용: "가수 - 곡" 한 줄을 가장 그럴듯한 곡 하나로
export async function resolveTrack(line) {
  const m = line.replace(/^\s*\d+[.)]\s*/, '').split(/\s+[-–—]\s+|\s*[-–—]\s+|\s+[-–—]\s*/);
  const q = m.length >= 2 ? `${m[0]} ${m.slice(1).join(' ')}` : line;
  let r = await search(q, 'track');
  if (needsRefine(q)) r = await refine(r).catch(() => r);
  return r.tracks[0] || null;
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
  'piano': '피아노', 'korean ballad': '가요 발라드', '2nd gen k-pop': '2세대 케이팝', '3rd gen k-pop': '3세대 케이팝', '4th gen k-pop': '4세대 케이팝', 'korean indie': '국내 인디', 'korean rock': '국내 록', 'korean hip hop': '국내 힙합', 'korean r&b': '국내 R&B', 'kayokyoku': '가요곡', 'anime': '애니송', 'shibuya-kei': '시부야케이', 'art rock': '아트록', 'baroque pop': '바로크 팝', 'chamber pop': '체임버 팝', 'neo-psychedelia': '네오 사이키델리아', 'psychedelic rock': '사이키델릭 록', 'electronica': '일렉트로니카', 'pop rock': '팝 록', 'soft rock': '소프트 록', 'city pop': '시티팝', 'acoustic': '어쿠스틱', 'garage rock': '개러지 록', 'emo': '이모', 'experimental': '익스페리멘털', 'idm': 'IDM',
};
const NOT_GENRE = /^(girl group|boy band|idol|k-idol|female vocalist|male vocalist|asian music|asian|international|world|seen live|favorites?|favourite|korean|south korean|japanese|american|british|english|female vocalists?|male vocalists?|\d{4}s?|vocal|seoul|usa|uk|beautiful|love|awesome|my|cover|instrumental version)$/i;
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

// 템포 두 배·절반 오류 보정: Deezer BPM이 있으면 그 옥타브로, 없으면 타격이 드문 빠른 값은 절반으로
export function fixTempo(f, ref) {
  if (!f) return f;
  const c = [f.bpm, f.bpm / 2, f.bpm * 2];
  let bpm = f.bpm;
  if (ref > 0) {
    bpm = c.reduce((a, b) => (Math.abs(Math.log2(b / ref)) < Math.abs(Math.log2(a / ref)) ? b : a));
    if (Math.abs(Math.log2(bpm / ref)) > 0.11) bpm = ref; // 배수 관계가 아니면(셋잇단 등) Deezer 값을 채택
  }
  else if (f.bpm > 135 && f.onsetRate < 3) bpm = f.bpm / 2;
  if (bpm !== f.bpm) { f.bpmRaw = f.bpm; f.bpm = +bpm.toFixed(1); }
  return f;
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
  // 미리듣기는 음량이 평준화돼 있어(발라드·EDM 모두 약 -14 dBFS) 음량 대신 박동·타악기·잡음 성분으로 에너지를 잰다
  // 실측 보정: 발라드 박동 0.12~0.16, 댄스 0.67~0.91 / 고역 비중 발라드 ~0.01, 댄스 0.04~0.09
  const pulseN = clamp((f.pulse - 0.1) / 0.6), perc = clamp((f.high - 0.008) / 0.06), flatN = clamp((f.flatness - 0.18) / 0.3);
  const tempo = clamp((f.bpm - 65) / 105);
  // 두 경로 중 강한 쪽 위주: 박동(댄스·팝) / 잡음·고역 타악기(메탈·록은 박이 기타에 묻혀 박동 값이 낮음)
  const aBeat = 0.6 * pulseN + 0.4 * tempo, aNoise = 0.55 * perc + 0.45 * flatN;
  const arousal = clamp(0.65 * Math.max(aBeat, aNoise) + 0.35 * Math.min(aBeat, aNoise));
  const energy = arousal;
  const major = 1 / (1 + Math.exp(-f.modeMargin * 9));
  const bright = clamp((f.centroid - 900) / 2600);
  const valence = clamp(0.4 * major + 0.4 * bright + 0.2 * tempo);
  const acousticAudio = clamp(0.55 * (1 - clamp((f.flatness - 0.08) / 0.3)) + 0.25 * (1 - clamp(f.pulse / 0.6)) + 0.2 * (1 - clamp(f.high / 0.12)));
  const gx = genreAxis(genres);
  const x = clamp(gx == null ? 1 - 2 * acousticAudio : 0.65 * gx + 0.35 * (1 - 2 * acousticAudio), -1, 1);
  const y = clamp(((valence - 0.45) / 0.35) * 0.7 + (arousal - 0.4) * 1.2, -1, 1); // 정서축: 밝기·조성 + 에너지(잔잔할수록 서정 쪽)
  const words = [];
  if (arousal > 0.62) words.push(...(valence > 0.45 ? (bright > 0.55 ? ['신나는', '청량한'] : ['신나는', '당당한']) : ['강렬한', '긴장감 있는']));
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
    try { out.features = fixTempo(await analyzeAudio(u), dz?.bpm || 0); break; } catch (e) { /* 다음 소스 */ }
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
      const f = fixTempo(await analyzeAudio(t.preview), 0);
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

/* ───────────── 아티스트 상세: 인기곡 TOP 30 + 정식 발매작 ─────────────
   국내 인디 가수는 Deezer에 한글 이름 빈 페이지와 영문 이름 실제 페이지가 따로 있는 경우가 많아(잔나비/JANNABI, 검정치마/The Black Skirts)
   MusicBrainz 별칭으로 같은 사람의 페이지를 모두 찾아 합치고, 그래도 부족하면 Apple 곡 목록으로 채운다 */
async function mbArtistInfo(name) {
  const A = await mb(`artist?query=${enc(luc(name))}&limit=6`);
  const c = (A.artists || []).find((x) => (x.score ?? 0) >= 80 && [x.name, x['sort-name'], ...(x.aliases || []).map((y) => y.name)].some((n) => n && lite(n) === lite(name)));
  if (!c) return null;
  const names = [...new Set([c.name, ...(c.aliases || []).map((y) => y.name)].filter((n) => n && n.length < 40))];
  return { id: c.id, names, country: c.country || c.area?.name || '', begin: c['life-span']?.begin || '', type: c.type || '', disamb: c.disambiguation || '' };
}
export async function artistDetail(ar) {
  const info = await mbArtistInfo(ar.title).catch(() => null);
  const names = [...new Set([ar.title, ...(info?.names || [])])];
  const want = new Set(names.map(lite));
  const latin = names.filter((n) => /^[\x20-\x7E]+$/.test(n));
  const probe = [...new Set([ar.title, ...latin, ...names])].slice(0, 4);
  const dzIds = new Set(ar.deezerId ? [ar.deezerId] : []);
  const found = await Promise.all(probe.map((n) => deezer(`search/artist?q=${enc(n)}&limit=6`).catch(() => null)));
  for (const f of found) for (const a of f?.data || []) if (want.has(lite(a.name))) { dzIds.add(a.id); if (!ar.artwork && a.picture_xl) ar.artwork = a.picture_xl; }
  const ids = [...dzIds].slice(0, 4);
  const [tops, albs] = await Promise.all([
    Promise.all(ids.map((id) => deezer(`artist/${id}/top?limit=30`).then((d) => d.data || []).catch(() => []))),
    Promise.all(ids.map((id) => deezer(`artist/${id}/albums?limit=100`).then((d) => d.data || []).catch(() => []))),
  ]);
  // Apple 아티스트 ID(검색어별 영문 이름으로 찾기)
  let appleId = ar.appleId;
  if (!appleId) {
    for (const n of [...latin, ar.title].slice(0, 3)) {
      const r = await apple(`term=${enc(n)}&media=music&entity=musicArtist&limit=5&country=US`).catch(() => []);
      const hit = r.find((x) => want.has(lite(x.artistName))); if (hit) { appleId = hit.artistId; break; }
    }
  }
  const lookup = (entity, country) => (appleId ? jsonp(`https://itunes.apple.com/lookup?id=${appleId}&entity=${entity}&limit=200&country=${country}`).then((d) => (d.results || []).slice(1)).catch(() => []) : Promise.resolve([]));
  let aAlb = await lookup('album', 'KR'); if (!aAlb.length) aAlb = await lookup('album', 'US');
  // 인기곡: Deezer 순위(rank)로 정렬, 30곡이 안 되면 Apple 곡으로 보충
  const tmap = new Map();
  for (const t of tops.flat().sort((x, y) => (y.rank || 0) - (x.rank || 0))) {
    const it = fromDeezerTrack(t); if (isUnofficial(it)) continue;
    const k = dedupeKey(it.title); if (!tmap.has(k)) tmap.set(k, it);
  }
  if (tmap.size < 15) {
    let aSongs = await lookup('song', 'KR'); if (!aSongs.length) aSongs = await lookup('song', 'US');
    for (const r of aSongs.filter((x) => x.wrapperType === 'track')) {
      const it = fromAppleSong(r); if (isUnofficial(it)) continue;
      const k = dedupeKey(it.title); if (!tmap.has(k)) tmap.set(k, it);
      if (tmap.size >= 30) break;
    }
  }
  const tracks = [...tmap.values()].slice(0, 30);
  // 발매작: 컴필레이션·다른 가수 앨범 제외
  const amap = new Map();
  for (const a of albs.flat()) {
    if (a.record_type === 'compile') continue;
    const it = { kind: 'album', title: a.title, artist: info?.names?.[0] && ar.title, year: yearOf(a.release_date), date: a.release_date || '', artwork: a.cover_xl || a.cover_big || '', deezerId: a.id, deezerUrl: a.link, recordType: a.record_type, srcs: ['deezer'] };
    it.artist = ar.title;
    if (isUnofficial(it)) continue;
    it.key = itemKey(it); const k = dedupeKey(a.title); if (!amap.has(k)) amap.set(k, it);
  }
  for (const r of aAlb.filter((x) => x.wrapperType === 'collection')) {
    if (/various artists/i.test(r.artistName || '')) continue;
    const t = r.collectionName.replace(/ - (Single|EP)$/i, ''); const k = dedupeKey(t);
    const single = / - Single$/i.test(r.collectionName) || r.trackCount <= 3;
    if (amap.has(k)) { const p = amap.get(k); p.appleId = p.appleId || r.collectionId; p.appleUrl = r.collectionViewUrl; continue; }
    const it = { kind: 'album', title: t, artist: r.artistName, year: yearOf(r.releaseDate), date: (r.releaseDate || '').slice(0, 10), artwork: art600(r.artworkUrl100), appleId: r.collectionId, appleUrl: r.collectionViewUrl, trackCount: r.trackCount, recordType: single ? 'single' : / - EP$/i.test(r.collectionName) ? 'ep' : 'album', srcs: ['apple'] };
    if (isUnofficial(it)) continue;
    it.key = itemKey(it); amap.set(k, it);
  }
  const albums = [...amap.values()].sort((x, y) => String(y.date || y.year).localeCompare(String(x.date || x.year)));
  return { tracks, albums, info: info ? { country: info.country, begin: info.begin, type: info.type, names: names.filter((n) => n !== ar.title).slice(0, 4) } : null };
}

/* ───────────── 평단 정보: 위키백과 평점 표(Music ratings)·평단 반응·개요 ─────────────
   점수에는 넣지 않고 근거로만 보여 준다(루브릭 규칙: 수상·평론은 근거로만) */
const WIKI_H = { 'Api-User-Agent': 'Cheongeumsil/1.0 (https://cheongeumsil.higgsfield.app)' }; // 위키미디어 권장 앱 식별 헤더
const wiki = (lang, params) => fetch(`https://${lang}.wikipedia.org/w/api.php?${params}&format=json&formatversion=2&origin=*`, { headers: WIKI_H }).then((r) => { if (!r.ok) throw new Error('wiki ' + r.status); return r.json(); });
function stripWiki(t) {
  let s = (t || '').replace(/<ref[^>]*\/>/g, '').replace(/<ref[\s\S]*?<\/ref>/g, '').replace(/<!--[\s\S]*?-->/g, '');
  for (let i = 0; i < 6; i++) s = s.replace(/\{\{[^{}]*\}\}/g, '');
  return s.replace(/\[\[(?:[^|\]]*\|)?([^\]]*)\]\]/g, '$1').replace(/\[https?:\/\/\S+\s([^\]]+)\]/g, '$1').replace(/'{2,}/g, '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}
function parseRatings(wt) {
  const m = wt.match(/\{\{\s*(?:Music|Album) ratings([\s\S]*?)\n\}\}/i); if (!m) return [];
  const body = m[1]; const out = [];
  const get = (k) => { const r = body.match(new RegExp(`\\|\\s*${k}\\s*=\\s*([^\\n|]*(?:\\{\\{[^}]*\\}\\}[^\\n|]*)?)`, 'i')); return r ? r[1] : ''; };
  const norm = (raw) => {
    const r = raw.match(/\{\{\s*rating\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)/i); if (r) return { text: `${r[1]}/${r[2]}`, n: (100 * +r[1]) / +r[2] };
    const f = raw.replace(/<ref[\s\S]*/i, '').match(/([\d.]+)\s*\/\s*(\d+)/); if (f) return { text: `${f[1]}/${f[2]}`, n: (100 * +f[1]) / +f[2] };
    const g = stripWiki(raw).match(/^(A\+|A−|A-|A|B\+|B−|B-|B|C\+|C−|C-|C|D\+|D|E|F)\b/); if (g) { const G = { 'A+': 100, A: 95, 'A−': 90, 'A-': 90, 'B+': 85, B: 80, 'B−': 75, 'B-': 75, 'C+': 70, C: 65, 'C−': 60, 'C-': 60, 'D+': 55, D: 50, E: 40, F: 30 }; return { text: g[1], n: G[g[1]] }; }
    return null;
  };
  for (const [lab, k] of [['Metacritic', 'MC'], ['AnyDecentMusic?', 'ADM'], ['AOTY', 'AOTY']]) { const v = norm(get(k)); if (v) out.push({ source: lab, ...v, aggregate: true }); }
  for (let i = 1; i <= 30; i++) { const name = stripWiki(get(`rev${i}`)); if (!name) continue; const v = norm(get(`rev${i}score`)); if (v) out.push({ source: name, ...v }); }
  return out;
}
function receptionPara(wt) {
  const sec = wt.split(/\n==+\s*(Critical reception|Reception|Critical response)\s*==+\n/i)[2];
  if (!sec) return '';
  const body = sec.split(/\n==/)[0].replace(/\{\{\s*(?:Music|Album) ratings[\s\S]*?\n\}\}/i, '');
  const para = body.split(/\n\s*\n/).map(stripWiki).find((p) => p.length > 80);
  return para ? para.slice(0, 700) + (para.length > 700 ? '…' : '') : '';
}
export function criticInfo(it) {
  const title = (it.altTitle || it.title || '').replace(/\s*[([].*?[)\]]\s*/g, ' ').trim();
  const artist = primaryArtist(it.artist || '');
  const kindWord = it.kind === 'album' ? 'album' : 'song';
  return cached(`cr:${it.kind}:${lite(title)}:${lite(artist)}`, 36e5, async () => {
    const saved = lsGet('ctl:cr:' + lite(title + artist + kindWord)); if (saved && Date.now() - saved.t < 7 * 864e5) return saved.v;
    const pick = (list) => (list || []).find((r) => { const pt = lite(r.title), sn = lite((r.snippet || '').replace(/<[^>]+>/g, '')); return pt.startsWith(lite(title)) && (sn.includes(lite(artist)) || pt.includes(lite(artist)) || sn.includes(kindWord)); });
    let lang = 'en', hit = null;
    const en = await wiki('en', `action=query&list=search&srsearch=${enc(`${title} ${artist} ${kindWord}`)}&srlimit=6`).catch(() => null);
    hit = pick(en?.query?.search);
    if (!hit) { const ko = await wiki('ko', `action=query&list=search&srsearch=${enc(`${title} ${artist}`)}&srlimit=6`).catch(() => null); hit = pick(ko?.query?.search); if (hit) lang = 'ko'; }
    let v = { found: false };
    if (hit) {
      const P = await wiki(lang, `action=parse&page=${enc(hit.title)}&prop=wikitext|langlinks&redirects=1`).catch(() => null);
      const wt = P?.parse?.wikitext || '';
      const koTitle = lang === 'ko' ? hit.title : (P?.parse?.langlinks || []).find((l) => l.lang === 'ko')?.title;
      const sum = async (l, t) => { try { const r = await fetch(`https://${l}.wikipedia.org/api/rest_v1/page/summary/${enc(t.replace(/ /g, '_'))}`, { headers: WIKI_H }); return r.ok ? (await r.json()).extract || '' : ''; } catch { return ''; } };
      const ratings = parseRatings(wt);
      const crit = ratings.filter((r) => !r.aggregate);
      v = {
        found: true, title: hit.title, url: `https://${lang}.wikipedia.org/wiki/${enc(hit.title.replace(/ /g, '_'))}`,
        koUrl: koTitle ? `https://ko.wikipedia.org/wiki/${enc(koTitle.replace(/ /g, '_'))}` : '',
        summaryKo: koTitle ? await sum('ko', koTitle) : '', summaryEn: lang === 'en' ? await sum('en', hit.title) : '',
        ratings, avg: crit.length ? Math.round(crit.reduce((a, r) => a + r.n, 0) / crit.length) : null,
        reception: lang === 'en' ? receptionPara(wt) : '',
      };
    }
    lsSet('ctl:cr:' + lite(title + artist + kindWord), { t: Date.now(), v });
    return v;
  });
}

/* ───────────── 측정·공개 데이터 기반 평론문 ───────────── */
const josa = (w, a, b) => { const c = (w || '').charCodeAt((w || '').length - 1) - 0xAC00; return c >= 0 && c < 11172 && c % 28 ? a : b; };
export function reviewText(it, an, cr) {
  const out = [];
  const g = (an.genres || []).slice(0, 2).map((x) => x.ko || x.name);
  const who = it.kind === 'album' ? `${it.artist}의 ${it.recordType === 'single' ? '싱글' : it.recordType === 'ep' ? 'EP' : '앨범'}` : `${it.artist}의 곡`;
  out.push(`${it.title}${josa(it.title, '은', '는')} ${it.year ? it.year + '년에 발매된 ' : ''}${who}입니다.${g.length ? ` 공개 데이터베이스의 장르 태그로는 ${g.join('·')} 계열로 분류됩니다.` : ''}`);
  const f = an.features, m = an.mood;
  if (it.kind === 'track' && f) {
    const sound = [`템포는 약 ${Math.round(f.bpm)} BPM, 조성은 ${f.keyName}${Math.abs(f.modeMargin) < 0.1 ? '(장·단조 판정 불확실)' : ''}`];
    if (m) sound.push(`에너지 ${Math.round(m.energy * 100)}/100으로 ${m.words.join('·')} 쪽`);
    out.push(`사운드: ${sound.join(', ')}입니다.${m?.texture?.length ? ` 측정에서 드러난 질감은 ${m.texture.slice(0, 3).join(', ')}입니다.` : ''}`);
    const P = an.parts || {}; const good = [], weak = [];
    if (P.dynamics != null) (P.dynamics >= 0.8 ? good : P.dynamics < 0.5 ? weak : []).push(P.dynamics >= 0.8 ? `다이내믹 레인지 ${f.dr}dB로 장르 기준 범위 안` : `다이내믹 레인지 ${f.dr}dB로 장르 기준에서 벗어남`);
    if (P.width != null) (P.width >= 0.8 ? good : P.width < 0.5 ? weak : []).push(P.width >= 0.8 ? '스테레오 공간 배치가 안정적' : '스테레오 폭이 좁거나 과함');
    if (P.variation != null) (P.variation >= 0.8 ? good : P.variation < 0.5 ? weak : []).push(P.variation >= 0.8 ? '구간별 음색 변화가 적절' : '음색 변화가 단조롭거나 산만함');
    if (P.harmony != null) (P.harmony >= 0.8 ? good : P.harmony < 0.5 ? weak : []).push(P.harmony >= 0.8 ? '화성 움직임이 정체되지도 산만하지도 않음' : f.harmonicChange < 0.1 ? '화성 변화가 적어 반복적' : '화성 변화가 많아 산만할 수 있음');
    if (good.length) out.push(`측정상 강점: ${good.join(', ')}.`);
    if (weak.length) out.push(`측정상 약점: ${weak.join(', ')}.`);
  }
  if (it.kind !== 'track') {
    const ok = (an.analyzed || []).filter((t) => !t.failed);
    if (ok.length) {
      const best = [...ok].sort((a, b) => b.score - a.score)[0], worst = [...ok].sort((a, b) => a.score - b.score)[0];
      out.push(`분석한 ${ok.length}곡의 평균 템포는 ${Math.round(ok.reduce((s, t) => s + t.features.bpm, 0) / ok.length)} BPM이고, ${an.cohesion != null ? `곡 간 소리 일관성은 ${Math.round(an.cohesion * 100)}/100으로 ${an.cohesion >= 0.7 ? '하나의 색이 뚜렷합니다' : an.cohesion >= 0.45 ? '적당히 다양합니다' : '곡마다 방향이 크게 다릅니다'}.` : ''}`);
      if (ok.length > 1) out.push(`측정 점수가 가장 높은 곡은 ‘${best.title}’(${best.score.toFixed(1)}), 가장 낮은 곡은 ‘${worst.title}’(${worst.score.toFixed(1)})입니다.`);
    }
  }
  if (cr?.found && cr.ratings?.length) {
    const crit = cr.ratings.filter((r) => !r.aggregate); const agg = cr.ratings.filter((r) => r.aggregate);
    out.push(`평단: ${[...agg, ...crit].slice(0, 6).map((r) => `${r.source} ${r.text}`).join(', ')}${cr.avg != null ? ` (매체 ${crit.length}곳 환산 평균 ${cr.avg}/100)` : ''}. 평단 점수는 근거로만 표시하고 음악성 점수에는 넣지 않습니다.`);
  } else if (cr?.found) out.push('위키백과에 해설 문서는 있으나 매체 평점 표는 없습니다.');
  else if (cr) out.push('확인 가능한 공개 평단 자료(위키백과 평점 표)를 찾지 못해, 위 내용은 측정값과 메타데이터만으로 작성했습니다.');
  return out;
}
