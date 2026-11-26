import * as E from './engine.js';

/* ───────────── 유틸 ───────────── */
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeUrl = (u) => (typeof u === 'string' && u.startsWith('https://') ? u : '');
const fmtDur = (ms) => (ms ? `${Math.floor(ms / 60000)}:${String(Math.round((ms % 60000) / 1000)).padStart(2, '0')}` : '');
const lsGet = (k, d) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } };
const KIND_KO = { track: '곡', album: '앨범', artist: '아티스트' };
const toastEl = $('#toast');
let toastT;
function toast(msg) { toastEl.textContent = msg; toastEl.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => { toastEl.hidden = true; }, 2600); }

/* ───────────── 상태 ───────────── */
const LIB_KEY = 'ctl:lib:v1';
const S = {
  tab: 'all', q: '', res: null, token: 0,
  lib: lsGet(LIB_KEY, { entries: [], version: 0, prevTop: [] }),
  manual: lsGet('ctl:manual', {}),
  items: new Map(), // key → item(렌더된 항목 조회용)
  pending: new Map(), // key → { steps: [], promise }
  stack: [], sort: 'score', related: null,
};
const saveLib = () => { if (!lsSet(LIB_KEY, S.lib)) toast('브라우저 저장 공간이 부족합니다. 내 취향 화면에서 백업을 내려받아 두세요.'); };
const saveManual = () => lsSet('ctl:manual', S.manual);
const libEntry = (key) => S.lib.entries.find((e) => e.key === key);
function getAnalysis(key) { return libEntry(key)?.an || lsGet('ctl:a:' + key, null); }
function putAnalysis(key, an) {
  const e = libEntry(key);
  if (e) { e.an = an; saveLib(); } else lsSet('ctl:a:' + key, an);
}
function slim(it) {
  const keep = ['kind', 'key', 'title', 'artist', 'album', 'year', 'artwork', 'preview', 'previewAlt', 'appleUrl', 'appleId', 'appleAlbumId', 'appleArtistId', 'deezerId', 'deezerUrl', 'deezerAlbumId', 'deezerArtistId', 'durationMs', 'genre', 'explicit', 'trackCount', 'srcs', 'label'];
  return Object.fromEntries(keep.filter((k) => it[k] != null && it[k] !== '').map((k) => [k, it[k]]));
}
function reg(it) { if (!it.key) it.key = E.itemKey(it); const prev = S.items.get(it.key); S.items.set(it.key, prev ? Object.assign(prev, it) : it); return it.key; }

/* ───────────── 분석 큐(한 번에 하나: MusicBrainz 호출 제한 준수) ───────────── */
let chain = Promise.resolve();
function analyze(item) {
  const key = item.key;
  const have = getAnalysis(key);
  if (have) return Promise.resolve(have);
  if (S.pending.has(key)) return S.pending.get(key).promise;
  const rec = { steps: ['대기 중'], promise: null };
  S.pending.set(key, rec);
  const onStep = (s) => { rec.steps.push(s); if (curKey() === key) renderSheet(); };
  const run = async () => {
    rec.steps = [];
    const fn = item.kind === 'album' ? E.analyzeAlbum : item.kind === 'artist' ? E.analyzeArtist : E.analyzeTrack;
    const an = await fn(item, onStep);
    an.kind = item.kind;
    putAnalysis(key, an);
    const e = libEntry(key); if (e) { e.item = slim({ ...e.item, ...item }); saveLib(); }
    return an;
  };
  rec.promise = chain.then(run).catch((err) => { console.warn(err); return { kind: item.kind, failed: true, errors: ['분석 중 오류가 났습니다. 잠시 뒤 다시 열어 주세요.'] }; })
    .finally(() => { S.pending.delete(key); refreshAfterAnalysis(key); });
  chain = rec.promise.catch(() => {});
  return rec.promise;
}
function refreshAfterAnalysis(key) {
  if (curKey() === key) renderSheet();
  if (!$('#view-taste').hidden) renderTaste();
  updateCount();
}

/* ───────────── 점수 ───────────── */
function scoreOf(kind, an, key) {
  if (!an || an.failed) return null;
  const man = S.manual[key] || {};
  if (kind === 'track') {
    const axes = {}; const src = {};
    for (const a of E.AXES) {
      if (man.axes && man.axes[a.k] != null) { axes[a.k] = man.axes[a.k]; src[a.k] = 'u'; }
      else if (an.auto && an.auto[a.k] != null) { axes[a.k] = an.auto[a.k]; src[a.k] = 'm'; }
      else { axes[a.k] = E.DEFAULT_UNMEASURED; src[a.k] = 'g'; }
    }
    const score = E.musicScore(axes, !!man.inst);
    return { score, axes, src, provisional: Object.values(src).includes('g') };
  }
  const r = E.setScore(kind, an, man.axes || {});
  if (!r) return null;
  return { ...r, provisional: !(man.axes && man.axes.미 != null) && kind === 'album' };
}

/* ───────────── 취향 프로필 ───────────── */
const CORE_ROLES = new Set(['작곡', '작사', '작사·작곡', '편곡', '프로듀서']);
function profile(excludeKey) {
  const P = { n: 0, genres: new Map(), credits: new Map(), vecs: [], pts: [], bpms: [], minor: 0, modes: 0, energy: [], artists: new Map(), acoustic: [], width: [] };
  for (const e of S.lib.entries) {
    if (e.key === excludeKey || !e.an || e.an.failed) continue;
    P.n++;
    const an = e.an;
    (an.genres || []).forEach((g) => P.genres.set(g.name, (P.genres.get(g.name) || 0) + g.weight));
    for (const c of an.credits || []) if (CORE_ROLES.has(c.role)) { const k = c.name; const cur = P.credits.get(k) || { name: c.name, roles: new Set(), n: 0 }; cur.roles.add(c.role); cur.n += c.n || 1; P.credits.set(k, cur); }
    const art = (e.kind === 'artist' ? e.item.title : (e.item.artist || '')).split(/\s*(?:,|&|feat\.?)\s*/i)[0];
    if (art) P.artists.set(art, { n: (P.artists.get(art)?.n || 0) + 1, id: e.item.deezerArtistId || (e.kind === 'artist' ? e.item.deezerId : undefined) });
    const v = an.vec || an.vecMean; if (v) P.vecs.push(v);
    const m = an.mood; if (m) P.pts.push({ x: m.x, y: m.y, key: e.key, title: e.item.title });
    const feats = e.kind === 'track' ? (an.features ? [an.features] : []) : (an.analyzed || []).filter((t) => !t.failed).map((t) => t.features);
    const moods = e.kind === 'track' ? (an.mood ? [an.mood] : []) : (an.analyzed || []).filter((t) => !t.failed).map((t) => t.mood);
    for (const f of feats) { P.bpms.push(f.bpm); P.modes++; if (f.mode === 'minor') P.minor++; P.width.push(f.width); }
    for (const mm of moods) { P.energy.push(mm.energy); P.acoustic.push(mm.acoustic); }
  }
  return P;
}
const mean = (a) => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0);
const q = (a, p) => { if (!a.length) return 0; const s = [...a].sort((x, y) => x - y); return s[Math.floor(p * (s.length - 1))]; };
function topGenres(P, n = 5) { return [...P.genres.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([g]) => g); }

function fitOf(an, P) {
  if (!an || an.failed || P.vecs.length < 3) return null;
  const v = an.vec || an.vecMean;
  const dims = P.vecs[0].length;
  let sim = null;
  if (v) {
    let z = 0;
    for (let k = 0; k < dims; k++) {
      const col = P.vecs.map((x) => x[k]); const m = mean(col);
      const sd = Math.max(0.12, Math.sqrt(mean(col.map((x) => (x - m) ** 2))));
      z += ((v[k] - m) / sd) ** 2;
    }
    sim = Math.exp(-0.5 * (z / dims));
  }
  let gen = null;
  if ((an.genres || []).length && P.genres.size) {
    let dot = 0, a2 = 0, b2 = 0;
    for (const g of an.genres) { dot += g.weight * (P.genres.get(g.name) || 0); a2 += g.weight ** 2; }
    for (const w of P.genres.values()) b2 += w * w;
    gen = dot / Math.sqrt(a2 * b2 + 1e-9);
    gen = Math.min(1, gen * 1.6);
  }
  const names = new Set([...P.credits.keys()]);
  const cr = (an.credits || []).filter((c) => CORE_ROLES.has(c.role));
  const cred = cr.length ? Math.min(1, cr.filter((c) => names.has(c.name)).length / 2) : null;
  const parts = [[sim, 0.5], [gen, 0.38], [cred, 0.12]].filter(([x]) => x != null);
  if (!parts.length) return null;
  const tw = parts.reduce((s, [, w]) => s + w, 0);
  return Math.round((100 * parts.reduce((s, [x, w]) => s + x * w, 0)) / tw);
}

/* ───────────── 플레이어 ───────────── */
const audio = $('#audio');
let playingKey = null;
function play(it) {
  const src = it.preview || it.previewAlt;
  if (!src) { toast('이 곡은 미리듣기가 없습니다.'); return; }
  if (playingKey === it.key && !audio.paused) { audio.pause(); return; }
  audio.src = src; playingKey = it.key;
  audio.play().catch(() => toast('미리듣기를 재생하지 못했습니다.'));
  $('#playerBar').hidden = false;
  $('#pArt').src = safeUrl(it.artwork) || '';
  $('#pTitle').textContent = it.title; $('#pArtist').textContent = it.artist || '';
}
audio.addEventListener('play', syncPlay); audio.addEventListener('pause', syncPlay); audio.addEventListener('ended', syncPlay);
audio.addEventListener('timeupdate', () => { $('#pProg').style.width = `${(audio.currentTime / (audio.duration || 30)) * 100}%`; });
function syncPlay() {
  $('#pToggle').textContent = audio.paused ? '▶' : '❚❚';
  $('#pToggle').setAttribute('aria-label', audio.paused ? '재생' : '일시정지');
  document.querySelectorAll('.play').forEach((b) => { const on = b.dataset.key === playingKey && !audio.paused; b.classList.toggle('on', on); b.textContent = on ? '❚❚' : '▶'; });
}
$('#pToggle').addEventListener('click', () => (audio.paused ? audio.play() : audio.pause()));

/* ───────────── 라이브러리 ───────────── */
function toggleLib(key) {
  const it = S.items.get(key);
  const i = S.lib.entries.findIndex((e) => e.key === key);
  if (i >= 0) {
    const [gone] = S.lib.entries.splice(i, 1);
    if (gone.an) lsSet('ctl:a:' + key, gone.an);
    saveLib(); toast(`‘${gone.item.title}’을(를) 뺐습니다.`);
  } else {
    if (!it) return;
    S.lib.prevTop = topGenres(profile());
    S.lib.version = (S.lib.version || 0) + 1;
    const an = lsGet('ctl:a:' + key, null);
    S.lib.entries.unshift({ key, kind: it.kind, item: slim(it), an, addedAt: Date.now() });
    try { localStorage.removeItem('ctl:a:' + key); } catch { /* 무시 */ }
    saveLib();
    if (!an) analyze(it);
    toast(`‘${it.title}’을(를) 취향에 담았습니다${an ? '' : ' · 분석 중'}`);
  }
  updateCount(); syncAddButtons();
  if (!$('#view-taste').hidden) renderTaste();
  if (curKey()) renderSheet();
}
function updateCount() { $('#libCount').textContent = S.lib.entries.length; }
function syncAddButtons() {
  document.querySelectorAll('[data-act="add"]').forEach((b) => {
    const on = !!libEntry(b.dataset.key);
    b.classList.toggle('on', on);
    if (b.classList.contains('add')) { b.textContent = on ? '✓' : '+'; b.setAttribute('aria-label', on ? '취향에서 빼기' : '취향에 담기'); }
    else b.textContent = on ? '✓ 담김' : '+ 취향에 담기';
  });
}

/* ───────────── 검색 화면 ───────────── */
const resultsEl = $('#results');
const input = $('#q');
const EXAMPLES = [['NewJeans', 'Ditto'], ['아이유', '밤편지'], ['Radiohead', 'Weird Fishes'], ['검정치마', 'Everything'], ['Frank Ocean', 'Pink + White'], ['宇多田ヒカル', 'First Love'], ['Daft Punk', 'Digital Love'], ['혁오', 'TOMBOY']];
function renderIntro() {
  const recent = S.lib.entries.slice(0, 6);
  resultsEl.innerHTML = `
    <div class="intro">
      <div style="display:grid;gap:12px">
        <h1>좋아하는 음악을 담으면, 왜 좋아하는지 보여 드립니다.</h1>
        <p>곡·앨범·아티스트를 몇 개든 담을 수 있습니다. 담은 음악마다 세부장르와 작곡가, 곡의 느낌을 분석하고 8개 항목으로 엄격하게 채점한 뒤, 전체를 묶어 내 취향을 정리합니다.</p>
      </div>
      <div class="steps">
        <div class="step"><span class="n">STEP 1</span><b>검색</b><span>Apple Music과 Deezer 카탈로그를 한 번에 찾습니다.</span></div>
        <div class="step"><span class="n">STEP 2</span><b>담기</b><span>＋ 버튼으로 담으면 바로 분석이 시작됩니다.</span></div>
        <div class="step"><span class="n">STEP 3</span><b>내 취향 보기</b><span>세 개 이상 담으면 취향 공식과 지도가 나옵니다.</span></div>
      </div>
      <div style="display:grid;gap:10px">
        <span class="mut" style="font-size:13px">예시로 검색해 보기</span>
        <div class="chips">${EXAMPLES.map(([a, t]) => `<button class="chip" data-act="q" data-q="${esc(a + ' ' + t)}">${esc(t)}<small>${esc(a)}</small></button>`).join('')}</div>
      </div>
      ${recent.length ? `<div><div class="sec-h"><h2>최근 담은 음악</h2><a class="more" href="#taste">내 취향 보기</a></div><div class="shelf">${recent.map((e) => { reg(e.item); return card(e.item); }).join('')}</div></div>` : ''}
    </div>`;
}
function srcDots(it) { return `<span class="srcs" title="${esc((it.srcs || []).map((s) => (s === 'apple' ? 'Apple Music' : 'Deezer')).join(' · '))}">${(it.srcs || []).map((s) => `<i class="${s}"></i>`).join('')}</span>`; }
function addBtn(key) { const on = !!libEntry(key); return `<button class="add${on ? ' on' : ''}" data-act="add" data-key="${esc(key)}" aria-label="${on ? '취향에서 빼기' : '취향에 담기'}">${on ? '✓' : '+'}</button>`; }
function trow(it) {
  const key = reg(it);
  const img = safeUrl(it.artwork);
  return `<div class="trow" data-act="open" data-key="${esc(key)}">
    <div class="cover">${img ? `<img src="${esc(img)}" alt="" loading="lazy">` : ''}<button class="play" data-act="play" data-key="${esc(key)}" aria-label="미리듣기" ${it.preview || it.previewAlt ? '' : 'disabled'}>▶</button></div>
    <div class="tmeta"><b>${it.explicit ? '<span class="e">E</span>' : ''}${esc(it.title)}</b><span>${esc(it.artist)}${it.album ? ' · ' + esc(it.album) : ''}</span></div>
    <span class="dur">${srcDots(it)} ${fmtDur(it.durationMs)}</span>
    ${addBtn(key)}
  </div>`;
}
function card(it) {
  const key = reg(it);
  const img = safeUrl(it.artwork);
  const sub = it.kind === 'artist' ? '아티스트' : `${it.year ? it.year + ' · ' : ''}${esc(it.artist || '')}`;
  return `<button class="card ${it.kind}" data-act="open" data-key="${esc(key)}">${img ? `<img src="${esc(img)}" alt="" loading="lazy">` : `<span class="ph">${esc((it.title || '?').slice(0, 1))}</span>`}<b>${esc(it.title)}</b><span>${sub}</span></button>`;
}
function topCard(it) {
  const key = reg(it);
  const img = safeUrl(it.artwork);
  const on = !!libEntry(key);
  return `<div class="top-card ${it.kind}" data-act="open" data-key="${esc(key)}">
    ${img ? `<img src="${esc(img)}" alt="">` : `<span class="ph" style="width:104px;height:104px;border-radius:${it.kind === 'artist' ? '50%' : '8px'}">${esc(it.title.slice(0, 1))}</span>`}
    <div style="display:grid;gap:6px;min-width:0"><h3>${esc(it.title)}</h3>
      <div class="meta"><span class="pill">${KIND_KO[it.kind]}</span>${it.kind !== 'artist' ? `<span>${esc(it.artist)}</span>` : ''}${it.year ? `<span>· ${esc(it.year)}</span>` : ''}</div></div>
    <div class="row-actions">
      ${it.kind === 'track' && (it.preview || it.previewAlt) ? `<button class="btn" data-act="play" data-key="${esc(key)}">▶ 미리듣기</button>` : ''}
      <button class="btn ${on ? '' : 'primary'}" data-act="add" data-key="${esc(key)}">${on ? '✓ 담김' : '+ 취향에 담기'}</button>
      <button class="btn ghost" data-act="open" data-key="${esc(key)}">분석 보기</button>
    </div></div>`;
}
function renderResults() {
  const r = S.res;
  if (!r) return;
  const fail = r.failed.length ? `<div class="notice">${esc(r.failed.join(', '))} 응답이 늦거나 막혀 다른 서비스 결과만 표시합니다. 잠시 뒤 다시 검색하면 채워집니다.</div>` : '';
  const none = `<div class="state">‘${esc(S.q)}’에 맞는 결과가 없습니다. 철자를 확인하거나 아티스트 이름을 함께 넣어 보세요.</div>`;
  let html = '';
  if (S.tab === 'all') {
    if (!r.tracks.length && !r.albums.length && !r.artists.length) { resultsEl.innerHTML = fail + none; return; }
    html += `<div class="top-grid">
      ${r.top ? `<div><div class="sec-h"><h2>최상위 결과</h2></div>${topCard(r.top)}</div>` : ''}
      <div style="min-width:0"><div class="sec-h"><h2>곡</h2>${r.tracks.length > 5 ? '<button class="more" data-act="tab" data-tab="track">모두 보기</button>' : ''}</div><div class="list">${r.tracks.slice(0, 5).map(trow).join('') || '<div class="state">곡 결과 없음</div>'}</div></div>
    </div>`;
    if (r.artists.length) html += `<div><div class="sec-h"><h2>아티스트</h2><button class="more" data-act="tab" data-tab="artist">모두 보기</button></div><div class="shelf">${r.artists.slice(0, 8).map(card).join('')}</div></div>`;
    if (r.albums.length) html += `<div><div class="sec-h"><h2>앨범</h2><button class="more" data-act="tab" data-tab="album">모두 보기</button></div><div class="shelf">${r.albums.slice(0, 10).map(card).join('')}</div></div>`;
  } else if (S.tab === 'track') {
    html = r.tracks.length ? `<div class="list">${r.tracks.map(trow).join('')}</div>` : none;
  } else {
    const list = S.tab === 'album' ? r.albums : r.artists;
    html = list.length ? `<div class="grid-cards">${list.map(card).join('')}</div>` : none;
  }
  resultsEl.innerHTML = fail + html;
  syncPlay();
}
let debT;
async function doSearch(now = false) {
  const qv = input.value.trim();
  $('#clearQ').hidden = !input.value;
  clearTimeout(debT);
  if (qv.length < 1) { S.q = ''; S.res = null; renderIntro(); return; }
  const go = async () => {
    const tok = ++S.token; S.q = qv;
    if (!S.res) resultsEl.innerHTML = `<div class="skel">${'<i></i>'.repeat(6)}</div>`;
    try {
      const res = await E.search(qv, S.tab);
      if (tok !== S.token) return;
      S.res = res; renderResults();
      try { history.replaceState(null, '', `?q=${encodeURIComponent(qv)}${S.tab !== 'all' ? '&t=' + S.tab : ''}${location.hash}`); } catch { /* 무시 */ }
    } catch (e) {
      if (tok !== S.token) return;
      resultsEl.innerHTML = '<div class="state">검색 서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 검색해 주세요.<br><button class="btn small" style="margin-top:12px" data-act="retry">다시 검색</button></div>';
    }
  };
  if (now) go(); else debT = setTimeout(go, 450);
}
input.addEventListener('input', () => doSearch(false));
$('#searchForm').addEventListener('submit', (e) => { e.preventDefault(); input.blur(); doSearch(true); });
$('#clearQ').addEventListener('click', () => { input.value = ''; S.res = null; doSearch(true); input.focus(); });
function setTab(t) {
  S.tab = t;
  document.querySelectorAll('#tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === t)));
  S.res = null; if (input.value.trim()) doSearch(true);
  window.scrollTo({ top: 0 });
}
$('#tabs').addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) setTab(b.dataset.tab); });

/* ───────────── 분석 시트 ───────────── */
const sheet = $('#sheet'), sheetBody = $('#sheetBody');
const curKey = () => (S.stack.length && !sheet.hidden ? S.stack[S.stack.length - 1] : null);
function openSheet(key) {
  const it = S.items.get(key); if (!it) return;
  if (curKey() !== key) S.stack.push(key);
  sheet.hidden = false; $('#sheetBack').hidden = false; document.body.style.overflow = 'hidden';
  renderSheet(); sheetBody.scrollTop = 0;
  if (!getAnalysis(key)) analyze(it);
}
function closeSheet() { sheet.hidden = true; $('#sheetBack').hidden = true; S.stack = []; document.body.style.overflow = ''; }
$('#sheetClose').addEventListener('click', closeSheet);
$('#sheetBack').addEventListener('click', closeSheet);
$('#sheetPrev').addEventListener('click', () => { S.stack.pop(); renderSheet(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !sheet.hidden) closeSheet(); });

function links(it) {
  const qy = encodeURIComponent(`${it.kind === 'artist' ? '' : (it.artist || '') + ' '}${it.title}`.trim());
  const L = [
    ['Apple Music', safeUrl(it.appleUrl) || `https://music.apple.com/kr/search?term=${qy}`],
    ['Spotify', `https://open.spotify.com/search/${qy}`],
    ['YouTube Music', `https://music.youtube.com/search?q=${qy}`],
    ['멜론', `https://www.melon.com/search/total/index.htm?q=${qy}`],
    ['Deezer', safeUrl(it.deezerUrl) || `https://www.deezer.com/search/${qy}`],
  ];
  return `<div class="links">${L.map(([n, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(n)} ↗</a>`).join('')}</div>`;
}
function head(it) {
  const img = safeUrl(it.artwork);
  const key = it.key; const on = !!libEntry(key);
  const sub = it.kind === 'track' ? [it.artist, it.album, it.year].filter(Boolean).join(' · ') : it.kind === 'album' ? [it.artist, it.year, it.trackCount ? `${it.trackCount}곡` : ''].filter(Boolean).join(' · ') : '아티스트';
  return `<div class="d-head ${it.kind}">${img ? `<img src="${esc(img)}" alt="">` : `<span class="ph">${esc(it.title.slice(0, 1))}</span>`}
    <div style="display:grid;gap:6px;min-width:0"><span class="pill" style="justify-self:start">${KIND_KO[it.kind]}</span><h2>${esc(it.title)}</h2><span class="sub">${esc(sub)}</span></div></div>
    <div class="d-actions">
      <button class="btn ${on ? '' : 'primary'}" data-act="add" data-key="${esc(key)}">${on ? '✓ 담김' : '+ 취향에 담기'}</button>
      ${it.kind === 'track' && (it.preview || it.previewAlt) ? `<button class="btn" data-act="play" data-key="${esc(key)}">▶ 미리듣기</button>` : ''}
    </div>${links(it)}`;
}
function progressBlock(key) {
  const rec = S.pending.get(key);
  const steps = rec ? rec.steps : [];
  return `<div class="block"><h3>분석 중</h3><div class="progress">${steps.map((s, i) => `<div class="${i < steps.length - 1 ? 'done' : 'now'}">${esc(s)}</div>`).join('') || '<div class="now">준비 중</div>'}</div>
    <p class="mut" style="margin:0;font-size:13px">미리듣기 30초를 내려받아 브라우저에서 직접 신호를 분석합니다. 크레딧 조회는 MusicBrainz 이용 규칙(초당 1회)에 맞춰 천천히 진행됩니다.</p></div>`;
}
function vu(score) { const n = 20, on = Math.round((score / 100) * n); return `<div class="vu" aria-hidden="true">${Array.from({ length: n }, (_, i) => `<i class="${i < on ? 'on' : ''}${i >= 17 && i < on ? ' hot' : ''}"></i>`).join('')}</div>`; }
function scoreHead(sc, label) {
  const g = E.grade(sc.score);
  return `<div class="score"><div><div class="score-num">${sc.score.toFixed(1)}<small>/100</small></div>${vu(sc.score)}</div>
    <div style="min-width:0"><div class="score-grade"><b>${g.g}</b><span>${g.t}</span></div><p>${label}</p></div></div>`;
}
function trackScoreBlock(key, an) {
  const sc = scoreOf('track', an, key);
  const man = S.manual[key] || {};
  const label = sc.provisional
    ? '잠정 점수입니다. 오디오로 잴 수 있는 작곡(화성)·편곡 두 항목만 측정했고, 나머지는 보수적 기본값 2.5점입니다. 직접 들어 보고 막대를 옮기면 확정됩니다.'
    : '모든 항목을 직접 채점한 확정 점수입니다.';
  const badge = { m: ['m', '측정'], g: ['g', '기본값'], u: ['u', '직접'] };
  return `<div class="block" id="scoreBlock"><h3>엄격 채점 · 8개 항목</h3>${scoreHead(sc, label)}
    <div class="axes">${E.AXES.map((a) => {
      const v = sc.axes[a.k]; const [bc, bt] = badge[sc.src[a.k]];
      const off = man.inst && a.k === '가';
      return `<div class="axis"${off ? ' style="opacity:.35"' : ''}><span class="nm">${esc(a.name)}<small>가중치 ${a.w}</small></span>
        <input type="range" min="0" max="5" step="0.5" value="${v}" data-act="axis" data-key="${esc(key)}" data-axis="${a.k}" aria-label="${esc(a.name)} 점수" ${off ? 'disabled' : ''}>
        <span class="v">${(+v).toFixed(1)}</span><span class="badge ${bc}">${bt}</span>
        <span class="axis-hint">${esc(a.hint)} — ${esc(E.ANCHORS[Math.round(v)])}</span></div>`;
    }).join('')}</div>
    <div class="score-tools"><label><input type="checkbox" data-act="inst" data-key="${esc(key)}" ${man.inst ? 'checked' : ''}> 연주곡(가사 항목 제외)</label>
      ${man.axes && Object.keys(man.axes).length ? `<button class="btn small ghost" data-act="resetAxes" data-key="${esc(key)}">직접 채점 지우기</button>` : ''}</div>
    <p class="mut" style="margin:0;font-size:12px">기준: 5 장르의 교본 · 4 장르 상위 10% · 3 탄탄함 · 2 평범 · 1 약점이 눈에 띔 · 0 곡을 해침. 자동 측정은 근거 없이 4점을 넘지 않고(작곡은 멜로디를 들을 수 없어 3.5점까지), 인기·차트·수상은 점수에 넣지 않습니다.</p>
    ${fitBlock(key, an, sc.score)}</div>`;
}
function fitBlock(key, an, score) {
  const P = profile(key);
  const fit = fitOf(an, P);
  if (fit == null) return `<p class="mut" style="margin:0;font-size:13px">취향 적합도는 다른 음악을 세 개 이상 담고 분석이 끝나면 계산됩니다. (현재 ${P.n}개)</p>`;
  const fin = +(score * 0.6 + fit * 0.4).toFixed(1);
  const eureka = score >= 85 && fit < 50;
  return `<div class="fit"><div class="kv"><span>내 취향 적합도</span><b>${fit}</b><em>담은 음악 ${P.n}개와의 소리·장르·창작자 겹침</em></div>
    <div class="kv"><span>취향 반영 점수</span><b>${fin}</b><em>음악성 × 0.6 + 취향 × 0.4${eureka ? ' · ✦ 취향 밖이지만 완성도가 매우 높음' : ''}</em></div></div>`;
}
function genreBlock(an) {
  if (!an.genres?.length) return `<div class="block"><h3>세부장르</h3><p class="mut" style="margin:0">장르 정보가 등록되어 있지 않습니다.</p></div>`;
  return `<div class="block"><h3>세부장르</h3><div class="genres">${an.genres.map((g, i) => `<div class="genre${i === 0 ? ' lead' : ''}"><b>${esc(g.ko || g.name)}</b><span>${esc(g.ko ? g.name : '')}${g.ko ? ' · ' : ''}비중 ${Math.round(g.weight * 100)}</span></div>`).join('')}</div>
    <p class="mut" style="margin:0;font-size:12px">MusicBrainz 장르·태그(곡 > 아티스트 순 가중), Deezer 앨범 장르, Apple 대표 장르를 합쳐 비중을 매겼습니다.</p></div>`;
}
const ROLE_ORDER = ['작사·작곡', '작곡', '작사', '편곡', '프로듀서', '믹스', '엔지니어', '레코딩', '마스터링', '프로그래밍', '보컬'];
function creditBlock(an, isSet) {
  const cr = an.credits || [];
  const src = an.mbUrl ? `<a href="${esc(safeUrl(an.mbUrl))}" target="_blank" rel="noopener noreferrer">MusicBrainz 원본 ↗</a>` : 'MusicBrainz';
  if (!cr.length) return `<div class="block"><h3>작곡 · 작사 · 프로듀서</h3><p class="mut" style="margin:0">공개 데이터베이스(MusicBrainz)에 이 ${isSet ? '앨범' : '곡'}의 크레딧이 아직 등록되어 있지 않습니다. 앨범 속지나 멜론 곡 정보에서 확인할 수 있습니다.</p><p class="foot" style="margin:0">출처: ${src}</p></div>`;
  const groups = new Map();
  for (const c of cr) { if (!groups.has(c.role)) groups.set(c.role, []); groups.get(c.role).push(c.n > 1 ? `${c.name} (${c.n}곡)` : c.name); }
  const roles = [...groups.keys()].sort((a, b) => (ROLE_ORDER.indexOf(a) + 1 || 99) - (ROLE_ORDER.indexOf(b) + 1 || 99));
  return `<div class="block"><h3>작곡 · 작사 · 프로듀서</h3><div class="credits">${roles.map((r) => `<div class="credit"><span>${esc(r)}</span><b>${esc(groups.get(r).join(', '))}</b></div>`).join('')}</div><p class="foot" style="margin:0">출처: ${src} (사용자 참여형 데이터베이스라 누락이 있을 수 있음)</p></div>`;
}
function metric(label, val, note, meter) { return `<div class="metric"><span>${esc(label)}</span><b>${val}</b>${meter != null ? `<div class="meter"><i style="width:${Math.round(E.clamp(meter) * 100)}%"></i></div>` : ''}<em>${esc(note)}</em></div>`; }
function moodBlock(an) {
  const f = an.features, m = an.mood;
  if (!f) return `<div class="block"><h3>곡의 느낌</h3><p class="mut" style="margin:0">미리듣기 오디오를 분석하지 못해 느낌을 측정하지 못했습니다. ${an.bpmRef ? `Deezer 기준 템포는 ${an.bpmRef} BPM입니다.` : ''}</p></div>`;
  const drNote = f.dr > 12 ? '강약 대비가 큼' : f.dr < 6 ? '세기 변화가 적고 꽉 찬 편' : '보통 범위';
  const bpmNote = an.bpmRef && Math.abs(an.bpmRef - f.bpm) > 4 ? `Deezer 표기 ${an.bpmRef} BPM. 박자 단위 차이로 반·두 배가 될 수 있음` : '30초 구간의 타격음 주기로 추정';
  return `<div class="block"><h3>곡의 느낌</h3>
    <div class="mood-words">${esc(m.words.join(' · '))}</div>
    <div class="mood-tex">${m.texture.map((t) => `<span>${esc(t)}</span>`).join('')}</div>
    <div class="metrics">
      ${metric('템포', `${Math.round(f.bpm)} <small class="mut">BPM</small>`, bpmNote)}
      ${metric('조성', `${esc(f.keyName)} <small class="mut">${esc(f.camelot)}</small>`, `조성 확신도 ${f.keyR.toFixed(2)} (1에 가까울수록 뚜렷)`)}
      ${metric('에너지', `${Math.round(m.energy * 100)}`, `평균 음량 ${f.rmsDb} dBFS`, m.energy)}
      ${metric('밝기', `${Math.round(E.clamp((f.centroid - 900) / 2600) * 100)}`, `소리 무게중심 ${f.centroid.toLocaleString()} Hz`, (f.centroid - 900) / 2600)}
      ${metric('다이내믹 레인지', `${f.dr} <small class="mut">dB</small>`, drNote, f.dr / 16)}
      ${metric('공간감(스테레오 폭)', `${Math.round(E.clamp(f.width / 0.6) * 100)}`, f.width < 0.03 ? '거의 모노' : f.width > 0.35 ? '넓게 퍼짐' : '보통', f.width / 0.6)}
      ${metric('화성 움직임', `${Math.round(E.clamp(f.harmonicChange / 0.4) * 100)}`, '1초 단위 음높이 분포가 바뀌는 정도', f.harmonicChange / 0.4)}
      ${metric('어쿠스틱 질감', `${Math.round(m.acoustic * 100)}`, '잡음성·고역·비트 규칙성으로 추정', m.acoustic)}
    </div>
    <div class="quad-wrap"><canvas class="quad" data-quad="single"></canvas></div>
    <p class="mut" style="margin:0;font-size:12px">취향 지도 위치: <b style="color:var(--fg)">${esc(m.quad)}</b> (가로: 밴드·어쿠스틱 ↔ 전자·R&B, 세로: 아련 ↔ 밝음)</p></div>`;
}
function setBlock(it, an) {
  const key = it.key;
  const sc = scoreOf(it.kind, an, key);
  const man = (S.manual[key] || {}).axes || {};
  const ok = (an.analyzed || []).filter((t) => !t.failed);
  let html = '';
  if (sc) {
    const label = it.kind === 'album'
      ? `상위 3곡 평균 ${sc.top3} × 50% + 통일성 ${(+sc.tong).toFixed(1)}점 × 30% + 미적 일체감 ${(+sc.mi).toFixed(1)}점 × 20%. 분석한 수록곡 ${sc.n}곡 기준.`
      : `대표곡 평균 ${sc.mean} × 55% + 상위 3곡 ${sc.top3} × 30% + 일관성 ${(+sc.tong).toFixed(1)}점 × 15%${sc.penalty ? ` − 대표곡 한 곡 의존 감점 ${sc.penalty}` : ''}. ${sc.n}곡 기준.`;
    const axes = it.kind === 'album' ? [['통', '통일성', '앨범 흐름의 일관성(측정)', an.auto?.통], ['미', '미적 일체감', '사운드·커버·콘셉트의 일치(직접 평가)', undefined]] : [['통', '일관성', '대표곡들의 소리 일관성(측정)', an.auto?.통]];
    html += `<div class="block" id="scoreBlock"><h3>엄격 채점</h3>${scoreHead(sc, label)}
      <div class="axes">${axes.map(([k, name, hint, auto]) => {
        const v = man[k] ?? auto ?? E.DEFAULT_UNMEASURED; const src = man[k] != null ? ['u', '직접'] : auto != null ? ['m', '측정'] : ['g', '기본값'];
        return `<div class="axis"><span class="nm">${name}</span><input type="range" min="0" max="5" step="0.5" value="${v}" data-act="axis" data-key="${esc(key)}" data-axis="${k}" aria-label="${name} 점수"><span class="v">${(+v).toFixed(1)}</span><span class="badge ${src[0]}">${src[1]}</span><span class="axis-hint">${esc(hint)} — ${esc(E.ANCHORS[Math.round(v)])}</span></div>`;
      }).join('')}</div>${Object.keys(man).length ? `<div class="score-tools"><button class="btn small ghost" data-act="resetAxes" data-key="${esc(key)}">직접 채점 지우기</button></div>` : ''}
      ${fitBlock(key, an, sc.score)}</div>`;
  } else html += `<div class="block"><h3>엄격 채점</h3><p class="mut" style="margin:0">미리듣기가 있는 곡이 없어 점수를 매기지 못했습니다.</p></div>`;
  html += genreBlock(an);
  if (it.kind === 'album') html += creditBlock(an, true);
  if (an.mood) {
    const words = moodOf2(an.mood);
    html += `<div class="block"><h3>전체 느낌</h3><div class="mood-words">${esc(words)}</div>
      <div class="metrics">${metric('평균 템포', `${Math.round(mean(ok.map((t) => t.features.bpm)))} <small class="mut">BPM</small>`, `범위 ${Math.round(Math.min(...ok.map((t) => t.features.bpm)))}–${Math.round(Math.max(...ok.map((t) => t.features.bpm)))}`)}
      ${metric('단조 비율', `${Math.round((ok.filter((t) => t.features.mode === 'minor').length / ok.length) * 100)}%`, '분석한 곡 중 단조로 판정된 비율')}
      ${metric(it.kind === 'album' ? '통일성' : '일관성', an.cohesion == null ? '–' : `${Math.round(an.cohesion * 100)}`, '곡들의 템포·에너지·밝기·공간감이 얼마나 비슷한가', an.cohesion ?? 0)}
      ${metric('평균 에너지', `${Math.round(mean(ok.map((t) => t.mood.energy)) * 100)}`, '분석한 곡 평균', mean(ok.map((t) => t.mood.energy)))}</div>
      <div class="quad-wrap"><canvas class="quad" data-quad="set"></canvas></div></div>`;
  }
  const rows = an.tracks.map((t, i) => {
    const a = (an.analyzed || []).find((x) => x.title === t.title && x.deezerId === t.deezerId);
    const tItem = { kind: 'track', title: t.title, artist: t.artist, album: t.album || (it.kind === 'album' ? it.title : ''), artwork: t.artwork || it.artwork, preview: t.preview, previewAlt: t.preview, deezerId: t.deezerId, appleId: t.appleId, durationMs: t.durationMs, year: it.kind === 'album' ? it.year : '', srcs: [t.deezerId ? 'deezer' : 'apple'] };
    const k = reg(tItem);
    const s = a && !a.failed ? a.score : null;
    return `<div class="trow" data-act="open" data-key="${esc(k)}"><span class="idx num">${i + 1}</span>
      <div class="tmeta"><b>${esc(t.title)}</b><span>${esc(t.artist || '')}${a && !a.failed ? ' · ' + esc(a.mood.words[0]) + ' · ' + Math.round(a.features.bpm) + ' BPM' : ''}</span></div>
      <span class="minibar">${s != null ? `<i style="--w:${s}%"></i>${s.toFixed(0)}` : '<span class="dim" style="font-size:12px">미분석</span>'}</span>${addBtn(k)}</div>`;
  }).join('');
  html += `<div class="block"><h3>${it.kind === 'album' ? '수록곡' : '대표곡'} <span class="dim" style="text-transform:none;letter-spacing:0">· 막대는 측정 기반 잠정 점수, 누르면 곡 단위 상세 분석</span></h3><div class="list tracks">${rows}</div></div>`;
  return html;
}
function moodOf2(m) {
  const a = m.arousal, v = m.valence;
  if (a > 0.62) return v > 0.55 ? '신나고 밝은 쪽' : '강렬하고 어두운 쪽';
  if (a < 0.4) return v > 0.55 ? '잔잔하고 포근한 쪽' : '차분하고 아련한 쪽';
  return v > 0.55 ? '산뜻한 중간 템포' : v < 0.4 ? '가라앉은 중간 템포' : '담백한 중간 지대';
}
function renderSheet() {
  const key = curKey(); if (!key) return;
  const it = S.items.get(key) || libEntry(key)?.item;
  if (!it) return;
  $('#sheetPrev').hidden = S.stack.length < 2;
  $('#sheetTitle').textContent = `${KIND_KO[it.kind]} 분석`;
  const an = getAnalysis(key);
  let html = head(it);
  if (!an) html += progressBlock(key);
  else if (an.failed) html += `<div class="block"><p class="mut" style="margin:0">${esc(an.errors[0])}</p><button class="btn small" data-act="reanalyze" data-key="${esc(key)}">다시 분석</button></div>`;
  else if (it.kind === 'track') {
    html += trackScoreBlock(key, an) + genreBlock(an) + creditBlock(an, false) + moodBlock(an);
  } else html += setBlock(it, an);
  if (an && !an.failed) {
    html += `<p class="foot">${an.errors?.length ? esc(an.errors.join(' · ')) + '<br>' : ''}분석 한계: 음원 전체가 아닌 30초 미리듣기로 측정했습니다. 템포·조성·느낌은 신호 처리 추정치이고, 멜로디의 매력·가사·혁신성은 기계가 판정할 수 없어 직접 채점 항목으로 남겨 두었습니다. 검색·메타데이터: Apple iTunes Search API, Deezer API, MusicBrainz(CC0).
      <br><button class="btn small ghost" style="margin-top:8px" data-act="reanalyze" data-key="${esc(key)}">다시 분석</button></p>`;
  }
  sheetBody.innerHTML = html;
  syncPlay();
  requestAnimationFrame(() => drawSheetQuad(key, an));
}
function drawSheetQuad(key, an) {
  const cv = sheetBody.querySelector('canvas.quad'); if (!cv || !an) return;
  const P = profile(key);
  const pts = P.pts.map((p) => ({ ...p, faint: true }));
  if (an.mood) pts.push({ x: an.mood.x, y: an.mood.y, focus: true, title: S.items.get(key)?.title });
  if (cv.dataset.quad === 'set') for (const t of an.analyzed || []) if (!t.failed) pts.push({ x: t.mood.x, y: t.mood.y, small: true });
  drawQuad(cv, pts);
}

/* 취향 지도 */
function drawQuad(cv, pts) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight; if (!w || !h) return;
  cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  const c = cv.getContext('2d'); c.scale(dpr, dpr);
  const css = getComputedStyle(document.documentElement);
  const col = (n) => css.getPropertyValue(n).trim();
  const pad = 30, X = (x) => pad + ((x + 1) / 2) * (w - 2 * pad), Y = (y) => pad + ((1 - y) / 2) * (h - 2 * pad);
  c.clearRect(0, 0, w, h);
  c.strokeStyle = col('--line'); c.lineWidth = 1; c.setLineDash([3, 4]);
  c.beginPath(); c.moveTo(X(0), pad - 8); c.lineTo(X(0), h - pad + 8); c.moveTo(pad - 8, Y(0)); c.lineTo(w - pad + 8, Y(0)); c.stroke(); c.setLineDash([]);
  c.font = `500 11px ${col('--f-body')}`; c.fillStyle = col('--mut'); c.textAlign = 'center';
  c.fillText('밝음 · 설렘', X(0), 16); c.fillText('아련 · 처연', X(0), h - 8);
  c.save(); c.translate(12, Y(0)); c.rotate(-Math.PI / 2); c.fillText('밴드 · 어쿠스틱', 0, 0); c.restore();
  c.save(); c.translate(w - 10, Y(0)); c.rotate(Math.PI / 2); c.fillText('전자 · 댄스 · R&B', 0, 0); c.restore();
  c.fillStyle = col('--dim'); c.font = `600 12px ${col('--f-body')}`;
  c.textAlign = 'left'; c.fillText('청춘 기타팝', pad + 4, pad + 14); c.fillText('서정의 발라드', pad + 4, h - pad - 6);
  c.textAlign = 'right'; c.fillText('화사한 댄스', w - pad - 4, pad + 14); c.fillText('밤의 R&B', w - pad - 4, h - pad - 6);
  const acc = col('--acc'), hot = col('--hot');
  for (const p of pts.filter((p) => !p.focus)) {
    c.globalAlpha = p.faint ? 0.35 : 0.85; c.fillStyle = acc;
    c.beginPath(); c.arc(X(p.x), Y(p.y), p.small ? 3.5 : 5, 0, Math.PI * 2); c.fill();
  }
  c.globalAlpha = 1;
  for (const p of pts.filter((p) => p.focus)) {
    c.strokeStyle = hot; c.lineWidth = 2; c.fillStyle = hot;
    c.beginPath(); c.arc(X(p.x), Y(p.y), 7, 0, Math.PI * 2); c.stroke();
    c.beginPath(); c.arc(X(p.x), Y(p.y), 3, 0, Math.PI * 2); c.fill();
    if (p.title) { c.fillStyle = col('--fg'); c.font = `600 12px ${col('--f-body')}`; c.textAlign = X(p.x) > w / 2 ? 'right' : 'left'; c.fillText(p.title.slice(0, 22), X(p.x) + (X(p.x) > w / 2 ? -12 : 12), Y(p.y) + 4); }
  }
}

/* ───────────── 내 취향 화면 ───────────── */
const tasteEl = $('#taste');
function summary(P) {
  const tg = topGenres(P, 3).map((g) => E.GENRE_KO[g] || g);
  const ax = mean(P.pts.map((p) => p.x)), ay = mean(P.pts.map((p) => p.y));
  const quad = ay >= 0 ? (ax < 0 ? '청춘 기타팝' : '화사한 댄스') : (ax < 0 ? '서정의 발라드' : '밤의 R&B');
  const en = mean(P.energy);
  const enW = en > 0.62 ? '에너지가 높은' : en < 0.4 ? '에너지가 낮고 차분한' : '에너지가 중간인';
  const minorPct = P.modes ? Math.round((P.minor / P.modes) * 100) : null;
  const creators = [...P.credits.values()].filter((c) => c.n >= 2).sort((a, b) => b.n - a.n).slice(0, 3).map((c) => c.name);
  const h = `${quad} 쪽에 기운, ${enW} 취향`;
  const parts = [];
  if (tg.length) parts.push(`중심 장르는 ${tg.join(', ')}입니다.`);
  if (P.bpms.length) parts.push(`템포는 주로 ${Math.round(q(P.bpms, 0.25))}–${Math.round(q(P.bpms, 0.75))} BPM 사이에 모여 있습니다.`);
  if (minorPct != null) parts.push(minorPct >= 55 ? `단조 곡이 ${minorPct}%로 많아 아련하거나 어두운 화성에 끌리는 편입니다.` : minorPct <= 40 ? `장조 곡이 ${100 - minorPct}%로 많아 밝은 화성에 끌리는 편입니다.` : `장조와 단조가 고르게 섞여 있습니다.`);
  if (creators.length) parts.push(`${creators.join(', ')}의 이름이 여러 곡의 크레딧에 반복해서 나옵니다.`);
  const now = topGenres(P, 5), prev = S.lib.prevTop || [];
  const added = now.filter((g) => !prev.includes(g)).map((g) => E.GENRE_KO[g] || g);
  const dropped = prev.filter((g) => !now.includes(g)).map((g) => E.GENRE_KO[g] || g);
  const change = prev.length && (added.length || dropped.length) ? `직전 버전 대비 ${added.length ? `새로 들어온 장르: ${added.join(', ')}` : ''}${added.length && dropped.length ? ' · ' : ''}${dropped.length ? `밀려난 장르: ${dropped.join(', ')}` : ''}` : '';
  return { h, p: parts.join(' '), change };
}
function renderTaste() {
  updateCount();
  const entries = S.lib.entries;
  if (!entries.length) {
    tasteEl.innerHTML = `<div class="intro"><div style="display:grid;gap:12px"><h1>아직 담은 음악이 없습니다.</h1><p>검색에서 좋아하는 곡·앨범·아티스트 옆의 ＋ 버튼을 누르면 여기에 쌓이고, 세 개부터 취향 분석이 시작됩니다. 개수 제한은 없습니다.</p></div>
      <div class="chips">${EXAMPLES.slice(0, 6).map(([a, t]) => `<button class="chip" data-act="q" data-q="${esc(a + ' ' + t)}">${esc(t)}<small>${esc(a)}</small></button>`).join('')}</div>
      <div><label class="btn small ghost" style="cursor:pointer">백업 파일 불러오기<input type="file" accept="application/json" data-act="import" hidden></label></div></div>`;
    return;
  }
  const P = profile();
  const pend = entries.filter((e) => !e.an).length;
  const ready = P.n >= 3;
  const sm = ready ? summary(P) : null;
  const totalG = [...P.genres.values()].reduce((a, b) => a + b, 0) || 1;
  const gBars = [...P.genres.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  const gMax = gBars[0]?.[1] || 1;
  const creators = [...P.credits.values()].sort((a, b) => b.n - a.n).slice(0, 8);
  const scored = entries.map((e) => {
    const sc = e.an && !e.an.failed ? scoreOf(e.kind, e.an, e.key) : null;
    return { e, sc, fit: e.an ? fitOf(e.an, profile(e.key)) : null };
  });
  const sorted = [...scored].sort((a, b) => S.sort === 'recent' ? b.e.addedAt - a.e.addedAt : S.sort === 'fit' ? (b.fit ?? -1) - (a.fit ?? -1) : (b.sc?.score ?? -1) - (a.sc?.score ?? -1));
  tasteEl.innerHTML = `
    <div class="t-head"><span class="ver">취향 공식 v${S.lib.version || 1} · 담은 음악 ${entries.length}개 · 분석 완료 ${P.n}개</span>
      <h1>${ready ? esc(sm.h) : `세 개 이상 분석되면 취향 공식이 나옵니다 (${P.n}/3)`}</h1>
      ${ready ? `<p>${esc(sm.p)}</p>${sm.change ? `<p class="dim" style="font-size:13px">${esc(sm.change)}</p>` : ''}` : '<p>검색 화면에서 좋아하는 음악을 더 담아 주세요. 담는 즉시 분석이 시작됩니다.</p>'}
      ${pend ? `<span class="queue">분석 대기 ${pend}개 · 하나씩 차례로 진행합니다</span>` : ''}</div>
    <div class="t-grid">
      <section class="panel"><h2>세부장르 분포</h2>${gBars.length ? `<div class="bars">${gBars.map(([g, w]) => `<div class="bar"><span class="lbl">${esc(E.GENRE_KO[g] || g)}${E.GENRE_KO[g] ? `<small>${esc(g)}</small>` : ''}</span><span class="trk"><i style="width:${(w / gMax) * 100}%"></i></span><span class="val">${Math.round((w / totalG) * 100)}%</span></div>`).join('')}</div>` : '<p class="mut" style="margin:0">장르 정보가 쌓이면 여기에 표시됩니다.</p>'}</section>
      <section class="panel"><h2>반복해서 만나는 창작자</h2>${creators.length ? `<div class="bars">${creators.map((c) => `<div class="bar"><span class="lbl">${esc(c.name)}<small>${esc([...c.roles].join('·'))}</small></span><span class="trk"><i style="width:${(c.n / creators[0].n) * 100}%"></i></span><span class="val">${c.n}곡</span></div>`).join('')}</div>
        <div class="chips">${creators.slice(0, 4).map((c) => `<button class="chip" data-act="q" data-q="${esc(c.name)}">${esc(c.name)} 검색</button>`).join('')}</div>` : '<p class="mut" style="margin:0">작곡·작사·프로듀서 크레딧이 등록된 음악이 아직 없습니다(MusicBrainz 기준).</p>'}</section>
      <section class="panel"><h2>소리의 성향</h2>${P.bpms.length ? `<div class="stats">
        <div class="kv"><span>템포 중앙값</span><b>${Math.round(q(P.bpms, 0.5))}</b><em>${Math.round(q(P.bpms, 0.25))}–${Math.round(q(P.bpms, 0.75))} BPM</em></div>
        <div class="kv"><span>단조 비율</span><b>${P.modes ? Math.round((P.minor / P.modes) * 100) : 0}%</b><em>${P.modes}곡 기준</em></div>
        <div class="kv"><span>평균 에너지</span><b>${Math.round(mean(P.energy) * 100)}</b><em>0 잔잔 · 100 강렬</em></div>
        <div class="kv"><span>어쿠스틱 질감</span><b>${Math.round(mean(P.acoustic) * 100)}</b><em>높을수록 생악기 느낌</em></div>
        <div class="kv"><span>공간감</span><b>${Math.round(E.clamp(mean(P.width) / 0.6) * 100)}</b><em>스테레오 폭 평균</em></div>
        <div class="kv"><span>분석한 곡</span><b>${P.bpms.length}</b><em>앨범·아티스트 수록곡 포함</em></div></div>` : '<p class="mut" style="margin:0">분석이 끝나면 표시됩니다.</p>'}</section>
      <section class="panel"><h2>취향 지도</h2><canvas class="quad" id="tasteQuad"></canvas><p class="mut" style="margin:0;font-size:12px">점 하나가 담은 음악 하나입니다. 가로는 악기 구성, 세로는 정서입니다.</p></section>
      <section class="panel wide"><h2>비슷한 아티스트 더 찾기</h2><div class="chips" id="related"><span class="mut" style="font-size:13px">불러오는 중</span></div></section>
      <section class="panel wide"><div class="lib-tools"><h2>담은 음악</h2><div class="seg" role="group" aria-label="정렬">
          <button data-act="sort" data-sort="score" aria-pressed="${S.sort === 'score'}">점수순</button><button data-act="sort" data-sort="fit" aria-pressed="${S.sort === 'fit'}">취향 적합순</button><button data-act="sort" data-sort="recent" aria-pressed="${S.sort === 'recent'}">최근 담은 순</button></div></div>
        <div class="list">${sorted.map(({ e, sc, fit }) => {
          reg(e.item); const img = safeUrl(e.item.artwork);
          const g = sc ? E.grade(sc.score) : null;
          return `<div class="lrow" data-act="open" data-key="${esc(e.key)}"><div class="cover" style="${e.kind === 'artist' ? 'border-radius:50%' : ''}">${img ? `<img src="${esc(img)}" alt="" loading="lazy">` : ''}</div>
            <div class="tmeta"><b>${esc(e.item.title)}</b><span>${KIND_KO[e.kind]}${e.kind !== 'artist' ? ' · ' + esc(e.item.artist || '') : ''}${e.an?.genres?.[0] ? ' · ' + esc(e.an.genres[0].ko || e.an.genres[0].name) : ''}${fit != null ? ' · 취향 ' + fit : ''}</span></div>
            <span class="lscore">${sc ? `<b>${sc.score.toFixed(1)}</b><span>${g.g} · ${sc.provisional ? '잠정' : '확정'}</span>` : e.an ? '<span>점수 없음</span>' : '<span class="queue" style="justify-content:flex-end">분석 중</span>'}</span>
            <button class="add on" data-act="add" data-key="${esc(e.key)}" aria-label="취향에서 빼기">✓</button></div>`;
        }).join('')}</div></section>
      <section class="panel wide"><h2>백업</h2><p class="mut" style="margin:0;font-size:13px">담은 음악과 직접 매긴 점수는 이 브라우저에만 저장됩니다. 다른 기기로 옮기거나 지워질 때를 대비해 파일로 내려받아 두세요.</p>
        <div class="d-actions"><button class="btn small" data-act="export">백업 파일 내려받기</button><label class="btn small ghost" style="cursor:pointer">백업 파일 불러오기<input type="file" accept="application/json" data-act="import" hidden></label>
        <button class="btn small ghost danger" data-act="clearAsk">전부 지우기</button><span id="clearConfirm" hidden><button class="btn small" data-act="clearYes">정말 지우기</button></span></div></section>
    </div>`;
  requestAnimationFrame(() => { const cv = $('#tasteQuad'); if (cv) drawQuad(cv, P.pts.map((p) => ({ ...p }))); });
  loadRelated(P);
}
async function loadRelated(P) {
  const el = $('#related'); if (!el) return;
  const tops = [...P.artists.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 3);
  if (!tops.length) { el.innerHTML = '<span class="mut" style="font-size:13px">분석이 끝나면 담은 아티스트와 비슷한 아티스트를 보여 드립니다.</span>'; return; }
  const sig = tops.map(([n]) => n).join('|');
  if (!S.related || S.related.sig !== sig) {
    const have = new Set(S.lib.entries.map((e) => (e.kind === 'artist' ? e.item.title : (e.item.artist || '')).toLowerCase()));
    const lists = await Promise.all(tops.map(([name, v]) => E.relatedArtists(name, v.id).catch(() => [])));
    const seen = new Set(); const out = [];
    for (let i = 0; i < 12; i++) for (const l of lists) { const a = l[i]; if (a && !seen.has(a.title) && !have.has(a.title.toLowerCase())) { seen.add(a.title); out.push(a); } }
    S.related = { sig, list: out.slice(0, 16) };
  }
  const box = $('#related'); if (!box) return;
  box.innerHTML = S.related.list.length ? S.related.list.map((a) => { const k = reg(a); return `<button class="chip" data-act="open" data-key="${esc(k)}">${esc(a.title)}</button>`; }).join('') : '<span class="mut" style="font-size:13px">추천을 불러오지 못했습니다.</span>';
}

/* 백업 */
function exportLib() {
  const blob = new Blob([JSON.stringify({ app: 'cheongeumsil', v: 1, lib: S.lib, manual: S.manual }, null, 1)], { type: 'application/json' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `청음실-취향-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
async function importLib(file) {
  try {
    const d = JSON.parse(await file.text());
    if (d.app !== 'cheongeumsil' || !Array.isArray(d.lib?.entries)) throw new Error('형식');
    const have = new Set(S.lib.entries.map((e) => e.key));
    let n = 0;
    for (const e of d.lib.entries) if (e && e.key && e.item && !have.has(e.key)) { S.lib.entries.push(e); n++; }
    Object.assign(S.manual, d.manual || {});
    S.lib.version = Math.max(S.lib.version || 0, d.lib.version || 0) + (n ? 1 : 0);
    saveLib(); saveManual(); toast(`${n}개를 불러왔습니다.`); renderTaste();
  } catch { toast('청음실 백업 파일이 아니거나 손상되었습니다.'); }
}

/* ───────────── 이벤트 위임 ───────────── */
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]'); if (!el) return;
  const act = el.dataset.act, key = el.dataset.key;
  if (['play', 'add', 'q', 'tab', 'sort', 'export', 'reanalyze', 'resetAxes', 'clearAsk', 'clearYes', 'retry'].includes(act)) e.stopPropagation();
  if (act === 'open') openSheet(key);
  else if (act === 'play') { const it = S.items.get(key); if (it) play(it); }
  else if (act === 'add') toggleLib(key);
  else if (act === 'q') { location.hash = '#search'; input.value = el.dataset.q; closeSheet(); doSearch(true); }
  else if (act === 'tab') setTab(el.dataset.tab);
  else if (act === 'retry') doSearch(true);
  else if (act === 'sort') { S.sort = el.dataset.sort; renderTaste(); }
  else if (act === 'export') exportLib();
  else if (act === 'clearAsk') $('#clearConfirm').hidden = false;
  else if (act === 'clearYes') { S.lib = { entries: [], version: 0, prevTop: [] }; S.manual = {}; saveLib(); saveManual(); renderTaste(); toast('모두 지웠습니다.'); }
  else if (act === 'reanalyze') {
    const ent = libEntry(key); if (ent) { ent.an = null; saveLib(); }
    try { localStorage.removeItem('ctl:a:' + key); } catch { /* 무시 */ }
    const it = S.items.get(key) || ent?.item; if (it) { reg(it); analyze(it); renderSheet(); }
  } else if (act === 'resetAxes') { delete S.manual[key]; saveManual(); renderSheet(); }
});
document.addEventListener('input', (e) => {
  const el = e.target;
  if (el.dataset.act === 'axis') {
    const row = el.closest('.axis'); row.querySelector('.v').textContent = (+el.value).toFixed(1);
    const b = row.querySelector('.badge'); b.className = 'badge u'; b.textContent = '직접';
  }
});
document.addEventListener('change', (e) => {
  const el = e.target; const key = el.dataset.key;
  if (el.dataset.act === 'axis') {
    const m = S.manual[key] || (S.manual[key] = {}); (m.axes || (m.axes = {}))[el.dataset.axis] = +el.value;
    saveManual(); const top = sheetBody.scrollTop; renderSheet(); sheetBody.scrollTop = top;
  } else if (el.dataset.act === 'inst') {
    const m = S.manual[key] || (S.manual[key] = {}); m.inst = el.checked; saveManual(); const top = sheetBody.scrollTop; renderSheet(); sheetBody.scrollTop = top;
  } else if (el.dataset.act === 'import' && el.files?.[0]) importLib(el.files[0]);
});

/* ───────────── 라우팅 ───────────── */
function route() {
  const v = location.hash === '#taste' ? 'taste' : 'search';
  $('#view-search').hidden = v !== 'search'; $('#view-taste').hidden = v !== 'taste';
  document.querySelectorAll('[data-nav]').forEach((a) => { if (a.dataset.nav === v) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  if (v === 'taste') renderTaste();
  window.scrollTo(0, 0);
  requestAnimationFrame(() => window.scrollTo(0, 0));
}
window.addEventListener('hashchange', route);
window.addEventListener('resize', () => { const cv = $('#tasteQuad'); if (cv && !$('#view-taste').hidden) drawQuad(cv, profile().pts); });

/* 깨진 커버 이미지는 숨겨 빈 칸으로 */
document.addEventListener('error', (e) => { const t = e.target; if (t && t.tagName === 'IMG') t.style.visibility = 'hidden'; }, true);

/* 시작 */
updateCount();
const params = new URLSearchParams(location.search);
if (params.get('t') && ['track', 'album', 'artist'].includes(params.get('t'))) { S.tab = params.get('t'); document.querySelectorAll('#tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === S.tab))); }
if (params.get('q')) { input.value = params.get('q'); doSearch(true); } else renderIntro();
route();
// 새로고침 등으로 끊긴 분석 재개
for (const e of S.lib.entries) if (!e.an) { reg(e.item); analyze(e.item); }
