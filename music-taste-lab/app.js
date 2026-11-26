import * as E from './engine.js';

/* ═══════════════ 유틸 ═══════════════ */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeUrl = (u) => (typeof u === 'string' && u.startsWith('https://') ? u : '');
const lsGet = (k, d) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } };
const mean = (a) => (a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0);
const sd = (a) => { const m = mean(a); return Math.sqrt(mean(a.map((v) => (v - m) ** 2))); };
const qtl = (a, p) => { if (!a.length) return 0; const s = [...a].sort((x, y) => x - y); return s[Math.floor(p * (s.length - 1))]; };
const C = E.clamp;
const KIND = { track: '곡', album: '앨범', artist: '아티스트' };
const PH = (label) => 'data:image/svg+xml;utf8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="#222834"/><text x="60" y="74" text-anchor="middle" fill="#6C7687" font-family="sans-serif" font-size="44" font-weight="700">${esc((String(label || '?').trim()[0] || '?').toUpperCase())}</text></svg>`);
const art = (it) => safeUrl(it.artwork) || PH(it.title);
let toastT;
function toast(m) { const t = $('#toast'); t.textContent = m; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 3000); }
function links(artist, title) {
  const q = encodeURIComponent(`${artist || ''} ${title || ''}`.trim());
  return [['SP', 'Spotify', `https://open.spotify.com/search/${q}`], ['AM', 'Apple Music', `https://music.apple.com/kr/search?term=${q}`], ['YT', 'YouTube Music', `https://music.youtube.com/search?q=${q}`], ['멜론', '멜론', `https://www.melon.com/search/total/index.htm?q=${q}`]];
}
const chipsHtml = (a, t, full = false) => `<span class="ext-links">${links(a, t).map(([s, n, u]) => `<a class="ext-chip" href="${esc(u)}" target="_blank" rel="noopener noreferrer" title="${esc(n)}에서 열기">${esc(full ? n : s)}</a>`).join('')}</span>`;

/* ═══════════════ 상태 ═══════════════ */
const LIB = 'ctl:lib:v2';
const S = {
  tab: 'analyze', filter: 'all', q: '', res: null, token: 0,
  lib: lsGet(LIB, null) || migrate(),
  manual: lsGet('ctl:manual', {}),
  anti: lsGet('ctl:anti', []),
  items: new Map(), pending: new Map(), stack: [], critic: new Map(),
  btype: 'all', bfilter: '', report: null, rubric: null,
};
function migrate() { const old = lsGet('ctl:lib:v1', null); return old ? { entries: old.entries || [], version: old.version || 0, prevTop: old.prevTop || [] } : { entries: [], version: 0, prevTop: [] }; }
const saveLib = () => { if (!lsSet(LIB, S.lib)) toast('브라우저 저장 공간이 부족합니다. 백업을 내려받아 두세요.'); };
const saveManual = () => lsSet('ctl:manual', S.manual);
const entry = (key) => S.lib.entries.find((e) => e.key === key);
const getAn = (key) => entry(key)?.an || lsGet('ctl:a:' + key, null);
function putAn(key, an) { const e = entry(key); if (e) { e.an = an; saveLib(); } else lsSet('ctl:a:' + key, an); }
function slim(it) {
  const keep = ['kind', 'key', 'title', 'altTitle', 'artist', 'album', 'year', 'artwork', 'preview', 'previewAlt', 'appleUrl', 'appleId', 'appleAlbumId', 'appleArtistId', 'deezerId', 'deezerUrl', 'deezerAlbumId', 'deezerArtistId', 'durationMs', 'genre', 'explicit', 'trackCount', 'srcs', 'label', 'recordType', 'isrc'];
  return Object.fromEntries(keep.filter((k) => it[k] != null && it[k] !== '').map((k) => [k, it[k]]));
}
function reg(it) { if (!it.key) it.key = E.itemKey(it); const p = S.items.get(it.key); S.items.set(it.key, p ? Object.assign(p, it) : it); return it.key; }

/* ═══════════════ 분석 대기열(MusicBrainz 초당 1회 규칙 때문에 하나씩) ═══════════════ */
let chain = Promise.resolve();
function analyze(it) {
  const key = it.key;
  const have = getAn(key);
  if (have && !have.failed) return Promise.resolve(have);
  if (S.pending.has(key)) return S.pending.get(key).promise;
  const rec = { steps: ['대기 중'] };
  S.pending.set(key, rec);
  const onStep = (s) => { rec.steps.push(s); if (curKey() === key) renderModal(); };
  rec.promise = chain.then(async () => {
    rec.steps = [];
    const fn = it.kind === 'album' ? E.analyzeAlbum : it.kind === 'artist' ? E.analyzeArtist : E.analyzeTrack;
    const an = await fn(it, onStep); an.kind = it.kind;
    putAn(key, an);
    const e = entry(key); if (e) { e.item = slim({ ...e.item, ...it }); saveLib(); }
    return an;
  }).catch((err) => { console.warn(err); return { kind: it.kind, failed: true, errors: ['분석 중 오류가 났습니다. 다시 분석을 눌러 주세요.'] }; })
    .finally(() => { S.pending.delete(key); if (curKey() === key) renderModal(); renderBasket(); });
  chain = rec.promise.catch(() => {});
  renderBasket();
  return rec.promise;
}

/* ═══════════════ 점수·취향 프로필 ═══════════════ */
function scoreOf(kind, an, key) {
  if (!an || an.failed) return null;
  const man = S.manual[key] || {};
  if (kind === 'track') {
    const axes = {}, src = {};
    for (const a of E.AXES) {
      if (man.axes?.[a.k] != null) { axes[a.k] = man.axes[a.k]; src[a.k] = 'u'; }
      else if (an.auto?.[a.k] != null) { axes[a.k] = an.auto[a.k]; src[a.k] = 'm'; }
      else { axes[a.k] = E.DEFAULT_UNMEASURED; src[a.k] = 'g'; }
    }
    return { score: E.musicScore(axes, !!man.inst), axes, src, provisional: Object.values(src).includes('g') };
  }
  const r = E.setScore(kind, an, man.axes || {});
  return r ? { ...r, provisional: kind === 'album' && man.axes?.미 == null } : null;
}
const CORE = new Set(['작곡', '작사', '작사·작곡', '편곡', '프로듀서']);
function featsOf(e) {
  const an = e.an; if (!an || an.failed) return [];
  if (e.kind === 'track') return an.features ? [{ f: an.features, m: an.mood, d: e.item.durationMs }] : [];
  return (an.analyzed || []).filter((t) => !t.failed).map((t) => ({ f: t.features, m: t.mood, d: t.durationMs }));
}
function profile(exclude) {
  const P = { n: 0, genres: new Map(), credits: new Map(), vecs: [], pts: [], fs: [], artists: new Map() };
  for (const e of S.lib.entries) {
    if (e.key === exclude || !e.an || e.an.failed) continue;
    P.n++;
    (e.an.genres || []).forEach((g) => P.genres.set(g.name, (P.genres.get(g.name) || 0) + g.weight));
    for (const c of e.an.credits || []) if (CORE.has(c.role)) { const cur = P.credits.get(c.name) || { name: c.name, roles: new Set(), n: 0 }; cur.roles.add(c.role); cur.n += c.n || 1; P.credits.set(c.name, cur); }
    const nm = (e.kind === 'artist' ? e.item.title : e.item.artist || '').split(/\s*(?:,|&|feat\.?)\s*/i)[0];
    if (nm) P.artists.set(nm, { n: (P.artists.get(nm)?.n || 0) + 1, id: e.item.deezerArtistId || (e.kind === 'artist' ? e.item.deezerId : undefined) });
    const v = e.an.vec || e.an.vecMean; if (v) P.vecs.push(v);
    if (e.an.mood) P.pts.push({ x: e.an.mood.x, y: e.an.mood.y, label: e.item.title, kind: 'input' });
    P.fs.push(...featsOf(e));
  }
  return P;
}
const topGenres = (P, n = 5) => [...P.genres.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([g]) => g);
function fitOf(an, P) {
  if (!an || an.failed || P.vecs.length < 3) return null;
  const v = an.vec || an.vecMean; const dims = P.vecs[0].length;
  let sim = null;
  if (v) { let z = 0; for (let k = 0; k < dims; k++) { const col = P.vecs.map((x) => x[k]); const m = mean(col); const s = Math.max(0.12, sd(col)); z += ((v[k] - m) / s) ** 2; } sim = Math.exp(-0.5 * (z / dims)); }
  let gen = null;
  if (an.genres?.length && P.genres.size) { let dot = 0, a2 = 0, b2 = 0; for (const g of an.genres) { dot += g.weight * (P.genres.get(g.name) || 0); a2 += g.weight ** 2; } for (const w of P.genres.values()) b2 += w * w; gen = Math.min(1, (dot / Math.sqrt(a2 * b2 + 1e-9)) * 1.6); }
  const cr = (an.credits || []).filter((c) => CORE.has(c.role));
  const cred = cr.length ? Math.min(1, cr.filter((c) => P.credits.has(c.name)).length / 2) : null;
  const parts = [[sim, 0.5], [gen, 0.38], [cred, 0.12]].filter(([x]) => x != null);
  if (!parts.length) return null;
  let fit = (100 * parts.reduce((s, [x, w]) => s + x * w, 0)) / parts.reduce((s, [, w]) => s + w, 0);
  fit -= antiPenalty(an.features, an.mood, an.durationMs);
  return Math.max(0, Math.round(fit));
}

/* 피하고 싶은 요소: 측정 가능한 것만(측정값으로 감점) */
const ANTI = [
  { id: 'loop', label: '화성 변화 없이 같은 코드 반복', test: (f) => f.harmonicChange < 0.08 },
  { id: 'loud', label: '꽉 눌러 담은 라우드 믹스', test: (f) => f.crestDb < 8.5 },
  { id: 'edm', label: '과격한 고에너지 드롭', test: (f, m) => m && m.arousal > 0.8 && f.pulse > 0.7 },
  { id: 'short', label: '2분 30초 미만 짧은 곡', test: (f, m, d) => d && d < 150000 },
  { id: 'slow', label: '처지는 느린 템포(75 BPM 미만)', test: (f) => f.bpm < 75 },
  { id: 'harsh', label: '날카롭고 쨍한 고음 톤', test: (f) => f.centroid > 3500 },
];
function antiHits(f, m, d) { if (!f) return []; return ANTI.filter((a) => S.anti.includes(a.id) && a.test(f, m, d)); }
const antiPenalty = (f, m, d) => antiHits(f, m, d).length * 15;

/* ═══════════════ 플레이어 ═══════════════ */
const audio = $('#audio'); let playing = null;
function play(it) {
  const src = it.preview || it.previewAlt;
  if (!src) { toast('이 곡은 30초 미리듣기가 없습니다.'); return; }
  if (playing === it.key) { audio.paused ? audio.play() : audio.pause(); return; }
  audio.src = src; playing = it.key;
  audio.play().catch(() => toast('미리듣기를 재생하지 못했습니다.'));
  $('#player').hidden = false; $('#pArt').src = art(it); $('#pTitle').textContent = it.title; $('#pArtist').textContent = `${it.artist || ''} · 30초 미리듣기`;
}
function syncPlay() {
  $('#pToggle').textContent = audio.paused ? '▶ 재생' : '⏸ 정지';
  $$('[data-act="play"]').forEach((b) => { const on = b.dataset.key === playing && !audio.paused; b.classList.toggle('playing', on); if (b.classList.contains('icon-btn')) b.textContent = on ? '❚❚' : '▶'; });
}
['play', 'pause', 'ended'].forEach((ev) => audio.addEventListener(ev, syncPlay));
audio.addEventListener('timeupdate', () => { const c = audio.currentTime || 0; $('#pFill').style.width = `${Math.min(100, (c / (audio.duration || 30)) * 100)}%`; $('#pTime').textContent = `0:${String(Math.floor(c)).padStart(2, '0')}`; });
$('#pToggle').onclick = () => (audio.paused ? audio.play() : audio.pause());
$('#pClose').onclick = () => { audio.pause(); playing = null; $('#player').hidden = true; };

/* ═══════════════ 바구니 ═══════════════ */
function addItem(it, silent = false) {
  reg(it);
  if (entry(it.key)) { if (!silent) toast(`이미 담긴 항목입니다: ${it.title}`); return false; }
  S.lib.prevTop = topGenres(profile());
  S.lib.version = (S.lib.version || 0) + 1;
  const an = lsGet('ctl:a:' + it.key, null);
  S.lib.entries.unshift({ key: it.key, kind: it.kind, item: slim(it), an: an && !an.failed ? an : null, addedAt: Date.now() });
  try { localStorage.removeItem('ctl:a:' + it.key); } catch { /* 무시 */ }
  saveLib();
  if (!an) analyze(it);
  if (!silent) { toast(`담기 완료: ${it.artist && it.kind !== 'artist' ? it.artist + ' - ' : ''}${it.title}`); afterLibChange(); }
  return true;
}
function removeItem(key) {
  const i = S.lib.entries.findIndex((e) => e.key === key); if (i < 0) return;
  const [g] = S.lib.entries.splice(i, 1); if (g.an) lsSet('ctl:a:' + key, g.an);
  saveLib(); afterLibChange();
}
function toggleItem(key) { const it = S.items.get(key) || entry(key)?.item; if (!it) return; if (entry(key)) removeItem(key); else addItem(it); }
function afterLibChange() { renderBasket(); syncAdd(); if (curKey()) renderModal(); }
function syncAdd() {
  $$('[data-act="add"]').forEach((b) => {
    const on = !!entry(b.dataset.key);
    b.classList.toggle('added', on);
    if (b.classList.contains('icon-btn')) { b.textContent = on ? '✓' : '+'; b.title = on ? '바구니에서 빼기' : '취향 바구니에 담기'; }
    else b.textContent = on ? '✓ 담김' : '+ 담기';
  });
}
function renderBasket() {
  const list = $('#basketList');
  $('#basketCount').textContent = `${S.lib.entries.length}개`;
  const pend = S.lib.entries.filter((e) => !e.an || S.pending.has(e.key)).length;
  $('#queueText').textContent = pend ? `분석 중 ${pend}개 · 차례로 진행` : '브라우저에 자동 저장됨';
  const q = S.bfilter.toLowerCase();
  const rows = S.lib.entries.filter((e) => (S.btype === 'all' || e.kind === S.btype) && (!q || `${e.item.title} ${e.item.artist || ''} ${e.an?.genres?.[0]?.ko || ''}`.toLowerCase().includes(q)));
  if (!rows.length) {
    list.innerHTML = `<div class="empty">${S.lib.entries.length ? '조건에 맞는 항목이 없습니다.' : '아직 담은 음악이 없습니다.<br>왼쪽에서 검색해 <b>+</b>를 누르거나 체험 샘플을 눌러 보세요.'}</div>`;
    return;
  }
  list.innerHTML = rows.map((e) => {
    reg(e.item);
    const sc = scoreOf(e.kind, e.an, e.key);
    const g = e.an?.genres?.[0];
    const status = S.pending.has(e.key) || !e.an ? '<span class="bi-score">분석 중…</span>' : sc ? `<span class="bi-score"><b>${sc.score.toFixed(1)}</b>${E.grade(sc.score).g} · ${sc.provisional ? '잠정' : '확정'}</span>` : '<span class="bi-score">점수 없음</span>';
    return `<div class="basket-item"><div class="bi-main" data-act="open" data-key="${esc(e.key)}">
      <img src="${esc(art(e.item))}" alt="" class="${e.kind === 'artist' ? 'circle' : ''}" loading="lazy">
      <div style="min-width:0"><div class="track-title">${esc(e.item.title)}</div><div class="track-sub">${KIND[e.kind]}${e.kind !== 'artist' ? ' · ' + esc(e.item.artist || '') : ''}${g ? ' · ' + esc(g.ko || g.name) : ''}</div></div></div>
      ${status}<button type="button" class="btn-ghost" data-act="remove" data-key="${esc(e.key)}" aria-label="빼기">✕</button></div>`;
  }).join('');
}
function renderAnti() {
  $('#antiTags').innerHTML = ANTI.map((a) => `<button type="button" class="anti-pill${S.anti.includes(a.id) ? ' selected' : ''}" data-act="anti" data-id="${a.id}">${esc(a.label)}</button>`).join('');
}

/* ═══════════════ 검색 화면 ═══════════════ */
const results = $('#results'), qInput = $('#q');
const EXAMPLES = ['아이유 밤편지', '뉴진스 디토', '방탄소년단 봄날', '잔나비', 'Radiohead', '藤井風'];
function renderIntro() {
  results.innerHTML = `<div class="intro">좋아하는 가수나 곡을 검색해 <b>+ 담기</b>를 누르거나,<br>아티스트 카드를 눌러 <b>인기곡 TOP 30과 발매작 전체</b>를 둘러보세요.
    <div class="chips">${EXAMPLES.map((e) => `<button type="button" class="chip" data-act="q" data-q="${esc(e)}">${esc(e)}</button>`).join('')}</div></div>`;
}
function trackRow(it, rank = null) {
  const key = reg(it); const on = !!entry(key);
  const sub = [it.artist, it.album, it.year].filter(Boolean).join(' · ');
  return `<div class="track-row">${rank != null ? `<span class="rank">${rank}</span>` : ''}
    <img src="${esc(art(it))}" alt="" class="track-thumb" loading="lazy">
    <div class="track-meta" data-act="open" data-key="${esc(key)}" title="눌러서 곡 분석 보기"><div class="track-title">${it.explicit ? '<span class="badge badge-neutral" style="padding:0 5px;margin-right:4px">E</span>' : ''}${esc(it.title)}${it.altTitle && it.altTitle !== it.title ? ` <span class="muted" style="font-weight:500">(${esc(it.altTitle)})</span>` : ''}</div><div class="track-sub">${esc(sub)}</div></div>
    <div class="track-actions">
      ${it.preview || it.previewAlt ? `<button type="button" class="icon-btn" data-act="play" data-key="${esc(key)}" title="30초 미리듣기">▶</button>` : ''}
      ${chipsHtml(it.artist, it.altTitle || it.title)}
      <button type="button" class="icon-btn${on ? ' added' : ''}" data-act="add" data-key="${esc(key)}" title="${on ? '바구니에서 빼기' : '취향 바구니에 담기'}">${on ? '✓' : '+'}</button>
    </div></div>`;
}
function artistCard(a) {
  const key = reg(a); const on = !!entry(key);
  return `<div class="artist-card"><img src="${esc(art(a))}" alt="" class="artist-avatar" data-act="open" data-key="${esc(key)}" loading="lazy">
    <div class="track-title" data-act="open" data-key="${esc(key)}" style="cursor:pointer">${esc(a.title)}</div>
    <div class="track-sub" style="margin-bottom:8px">${esc(a.genre || '아티스트')}</div>
    <div class="row-gap" style="justify-content:center"><button type="button" class="btn-secondary" style="padding:4px 8px;font-size:11px" data-act="open" data-key="${esc(key)}">전체곡</button>
    <button type="button" class="icon-btn${on ? ' added' : ''}" style="width:28px;height:28px" data-act="add" data-key="${esc(key)}" title="아티스트 담기">${on ? '✓' : '+'}</button></div></div>`;
}
function albumCard(al) {
  const key = reg(al); const on = !!entry(key);
  const kind = al.recordType === 'single' ? '싱글' : al.recordType === 'ep' ? 'EP' : '';
  return `<div class="album-card"><img src="${esc(art(al))}" alt="" class="album-cover" data-act="open" data-key="${esc(key)}" loading="lazy">
    <div style="min-width:0"><div class="track-title" data-act="open" data-key="${esc(key)}" style="cursor:pointer" title="${esc(al.title)}">${esc(al.title)}</div><div class="track-sub">${esc([al.artist, al.year, kind].filter(Boolean).join(' · '))}</div></div>
    <div class="row-gap" style="margin-top:auto"><button type="button" class="btn-secondary" style="flex:1;padding:5px 8px;font-size:11.5px" data-act="open" data-key="${esc(key)}">수록곡</button>
    <button type="button" class="icon-btn${on ? ' added' : ''}" data-act="add" data-key="${esc(key)}" title="앨범 담기">${on ? '✓' : '+'}</button></div></div>`;
}
function renderResults(refining = false) {
  const r = S.res; if (!r) return;
  const f = S.filter;
  let h = '';
  if (r.failed.length) h += `<div class="notice">${esc(r.failed.join(', '))} 응답이 늦거나 막혀 나머지 결과만 표시합니다. 잠시 뒤 다시 검색하면 채워집니다.</div>`;
  if (refining) h += `<div class="notice" style="color:var(--accent-hover);background:var(--accent-soft);border-color:var(--accent-border)">한글·일본어 원어 이름을 연결해 정확한 곡을 찾는 중…</div>`;
  if (f === 'all' && r.top) {
    const t = r.top, key = reg(t), on = !!entry(key), isA = t.kind === 'artist';
    h += `<div class="section-label"><span>최상위 결과</span></div>
      <div class="top-result-card"><img src="${esc(art(t))}" alt="" class="top-result-art${isA ? ' circle' : ''}" data-act="open" data-key="${esc(key)}" style="cursor:pointer">
      <div class="top-result-info"><span class="badge">${KIND[t.kind]}</span><div class="top-title">${esc(t.title)}${t.altTitle && t.altTitle !== t.title ? ` <span class="muted" style="font-size:14px;font-weight:600">(${esc(t.altTitle)})</span>` : ''}</div>
        <div class="track-sub" style="margin:2px 0 8px">${isA ? '눌러서 인기곡·발매작 보기' : esc([t.artist, t.year].filter(Boolean).join(' · '))}</div>${chipsHtml(t.artist, isA ? '' : t.altTitle || t.title, true)}</div>
      <div class="row-gap">${t.kind === 'track' && (t.preview || t.previewAlt) ? `<button type="button" class="btn-secondary" data-act="play" data-key="${esc(key)}">▶ 미리듣기</button>` : ''}
        <button type="button" class="btn-secondary" data-act="open" data-key="${esc(key)}">${isA ? '인기곡·앨범' : t.kind === 'album' ? '수록곡·분석' : '곡 분석'}</button>
        <button type="button" class="btn-primary${on ? ' added' : ''}" data-act="add" data-key="${esc(key)}">${on ? '✓ 담김' : '+ 담기'}</button></div></div>`;
  }
  if ((f === 'all' || f === 'artist') && r.artists.length) {
    const list = f === 'all' ? r.artists.slice(0, 4) : r.artists;
    h += `<div class="section-label"><span>아티스트 (${r.artists.length})</span>${f === 'all' ? '<button type="button" class="more" data-act="filter" data-f="artist">모두 보기</button>' : ''}</div><div class="artist-grid">${list.map(artistCard).join('')}</div>`;
  }
  if ((f === 'all' || f === 'track') && r.tracks.length) {
    const list = f === 'all' ? r.tracks.slice(0, 8) : r.tracks;
    h += `<div class="section-label"><span>곡 (${r.tracks.length})</span>${f === 'all' ? '<button type="button" class="more" data-act="filter" data-f="track">모두 보기</button>' : ''}</div><div class="track-list">${list.map((t) => trackRow(t)).join('')}</div>`;
  }
  if ((f === 'all' || f === 'album') && r.albums.length) {
    const list = f === 'all' ? r.albums.slice(0, 4) : r.albums;
    h += `<div class="section-label"><span>앨범 (${r.albums.length})</span>${f === 'all' ? '<button type="button" class="more" data-act="filter" data-f="album">모두 보기</button>' : ''}</div><div class="album-grid">${list.map(albumCard).join('')}</div>`;
  }
  if (!r.tracks.length && !r.albums.length && !r.artists.length) h += `<div class="intro">‘${esc(r.q)}’에 맞는 결과가 없습니다. 철자를 확인하거나 가수 이름을 함께 넣어 보세요.</div>`;
  h += `<div class="manual-add"><span>찾는 곡이 없나요? 미발매곡·커버곡도 직접 담을 수 있습니다.</span><button type="button" class="btn-secondary" data-act="manual">+ "${esc(r.q)}" 직접 담기</button></div>`;
  results.innerHTML = h;
  syncPlay();
}
let debT;
function doSearch(now = false) {
  const q = qInput.value.trim();
  $('#clearQ').hidden = !qInput.value;
  clearTimeout(debT);
  if (!q) { S.q = ''; S.res = null; renderIntro(); $('#status').textContent = 'KR · US · JP 카탈로그'; return; }
  if (!now && q.length < 2) return;
  const go = async () => {
    const tok = ++S.token; S.q = q;
    $('#status').textContent = '검색 중…';
    if (!S.res) results.innerHTML = '<div class="skeleton-box"></div>'.repeat(4);
    try {
      let res = await E.search(q, S.filter);
      if (tok !== S.token) return;
      const refining = E.needsRefine(q);
      S.res = res; renderResults(refining);
      $('#status').textContent = `${res.tracks.length + res.albums.length + res.artists.length}건${refining ? ' · 원어 이름 연결 중' : ''}`;
      try { history.replaceState(null, '', `?q=${encodeURIComponent(q)}${S.filter !== 'all' ? '&t=' + S.filter : ''}`); } catch { /* 무시 */ }
      if (refining) {
        res = await E.refine(res).catch(() => res);
        if (tok !== S.token) return;
        S.res = res; renderResults(false);
        $('#status').textContent = `${res.tracks.length + res.albums.length + res.artists.length}건 · 원어 이름 연결 완료`;
      }
    } catch {
      if (tok !== S.token) return;
      $('#status').textContent = '연결 실패';
      results.innerHTML = '<div class="intro">검색 서버에 연결하지 못했습니다. 인터넷 연결을 확인한 뒤 다시 검색해 주세요.<div class="chips"><button type="button" class="chip" data-act="retry">다시 검색</button></div></div>';
    }
  };
  if (now) go(); else debT = setTimeout(go, 600);
}
qInput.addEventListener('input', () => doSearch(false));
$('#searchForm').addEventListener('submit', (e) => { e.preventDefault(); qInput.blur(); doSearch(true); });
$('#clearQ').onclick = () => { qInput.value = ''; S.res = null; doSearch(true); qInput.focus(); };
function setFilter(f) { S.filter = f; $$('#filters .pill').forEach((p) => p.classList.toggle('active', p.dataset.f === f)); S.res = null; if (qInput.value.trim()) doSearch(true); }

/* ═══════════════ 상세 창(아티스트·앨범·곡) ═══════════════ */
const modal = $('#modal'), mBody = $('#mBody');
const curKey = () => (!modal.hidden && S.stack.length ? S.stack[S.stack.length - 1] : null);
const detailCache = new Map();
function openModal(key) {
  const it = S.items.get(key) || entry(key)?.item; if (!it) return;
  reg(it);
  if (curKey() !== key) S.stack.push(key);
  modal.hidden = false; document.body.style.overflow = 'hidden';
  renderModal(); mBody.scrollTop = 0;
  const an = getAn(key);
  if (!an || an.failed) analyze(it); // 곡·앨범·아티스트 모두 열면 바로 분석
  if (it.kind !== 'track' && !detailCache.has(key)) loadDetail(it);
  if (it.kind !== 'artist' && !S.critic.has(key)) loadCritic(it);
}
function loadCritic(it) {
  const key = it.key; S.critic.set(key, { loading: true });
  E.criticInfo(it).then((v) => S.critic.set(key, v), () => S.critic.set(key, { found: false, error: true }))
    .finally(() => { if (curKey() === key) renderModal(); });
}
function reviewBlock(it, an) {
  const cr = S.critic.get(it.key);
  const paras = E.reviewText(it, an, cr && !cr.loading && !cr.error ? cr : null);
  let h = `<div class="d-block"><h4>객관적 평론</h4><div class="review">${paras.map((p) => `<p>${esc(p)}</p>`).join('')}</div>`;
  if (cr?.loading) h += '<p class="muted small">위키백과 평단 자료 확인 중…</p>';
  if (cr?.found) {
    if (cr.ratings?.length) h += `<div class="ratings">${cr.ratings.map((r) => `<div class="rating"><span>${esc(r.source)}${r.aggregate ? ' <em>종합</em>' : ''}</span><i style="--w:${Math.round(C(r.n / 100) * 100)}%"></i><b>${esc(r.text)}</b></div>`).join('')}</div>`;
    const sum = cr.summaryKo || cr.summaryEn;
    if (sum) h += `<blockquote class="wiki">${esc(sum.slice(0, 520))}${sum.length > 520 ? '…' : ''}</blockquote>`;
    if (cr.reception) h += `<details class="wiki"><summary>평단 반응 원문 보기(영문 위키백과)</summary><p>${esc(cr.reception)}</p></details>`;
    h += `<p class="foot">출처: <a href="${esc(safeUrl(cr.koUrl || cr.url))}" target="_blank" rel="noopener noreferrer">위키백과 ‘${esc(cr.title)}’</a> (CC BY-SA 4.0). 평단 점수는 근거로만 표시하고 음악성 점수에는 넣지 않습니다.</p>`;
  }
  return h + '</div>';
}
function closeModal() { modal.hidden = true; S.stack = []; document.body.style.overflow = ''; }
async function loadDetail(it) {
  const key = it.key; detailCache.set(key, { loading: true });
  try {
    if (it.kind === 'artist') detailCache.set(key, await E.artistDetail(it));
    else detailCache.set(key, { tracks: await E.albumTracks(it) });
  } catch { detailCache.set(key, { error: true, tracks: [], albums: [] }); }
  const d = detailCache.get(key); if (d && !d.error && !(d.tracks || []).length) setTimeout(() => detailCache.delete(key), 30000); // 빈 결과는 30초 뒤 다시 시도 가능
  if (curKey() === key) renderModal();
}
function renderModal() {
  const key = curKey(); if (!key) return;
  const it = S.items.get(key) || entry(key)?.item;
  $('#mBack').hidden = S.stack.length < 2;
  $('#mThumb').src = art(it); $('#mThumb').style.borderRadius = it.kind === 'artist' ? '999px' : '12px';
  $('#mBadge').textContent = it.kind === 'artist' ? '아티스트' : it.kind === 'album' ? '앨범' : '곡 분석';
  $('#mTitle').textContent = it.title + (it.altTitle && it.altTitle !== it.title ? ` (${it.altTitle})` : '');
  const inf = detailCache.get(key)?.info;
  const TYPE = { Group: '그룹', Person: '솔로', Orchestra: '오케스트라', Choir: '합창단' };
  $('#mSub').textContent = it.kind === 'artist' ? (inf ? [inf.country, inf.begin ? `${inf.begin.slice(0, 4)}년 활동 시작` : '', TYPE[inf.type] || '', inf.names?.length ? `다른 표기: ${inf.names.join(', ')}` : ''].filter(Boolean).join(' · ') : '인기곡 TOP 30 · 정식 발매작 · 아티스트 분석') : [it.artist, it.album !== it.title ? it.album : '', it.year].filter(Boolean).join(' · ');
  const on = !!entry(key);
  const add = $('#mAdd'); add.dataset.key = key; add.textContent = on ? '✓ 담김' : '+ 이 항목 담기'; add.classList.toggle('added', on);
  const top = mBody.scrollTop;
  mBody.innerHTML = it.kind === 'track' ? trackDetail(it) : setDetail(it);
  mBody.scrollTop = top;
  syncPlay();
  requestAnimationFrame(() => drawModalQuad(key));
}

/* 곡 분석 */
function progressBlock(key) {
  const rec = S.pending.get(key); const st = rec ? rec.steps : [];
  return `<div class="d-block"><h4>분석 중</h4><div class="progress-list">${(st.length ? st : ['준비 중']).map((s, i, a) => `<div class="${i < a.length - 1 ? 'done' : 'now'}">${esc(s)}</div>`).join('')}</div>
    <p class="muted small">30초 미리듣기를 내려받아 브라우저에서 직접 신호를 분석하고, 작곡·작사 크레딧은 MusicBrainz 이용 규칙(초당 1회)에 맞춰 조회합니다.</p></div>`;
}
function scoreBlock(key, an) {
  const sc = scoreOf('track', an, key); const man = S.manual[key] || {};
  const g = E.grade(sc.score);
  const label = sc.provisional ? '잠정 점수입니다. 오디오로 잴 수 있는 작곡(화성)·편곡만 측정했고, 나머지는 보수적 기본값 2.5점입니다. 직접 들어 보고 막대를 옮기면 확정됩니다.' : '모든 항목을 직접 채점한 확정 점수입니다.';
  const SRC = { m: ['m', '측정'], g: ['g', '기본값'], u: ['u', '직접'] };
  return `<div class="d-block"><h4>엄격 8축 채점</h4>
    <div class="score-box"><div><div class="score-big">${sc.score.toFixed(1)}<small> / 100</small></div></div><div><span class="badge ${sc.score >= 80 ? 'badge-ok' : sc.score < 60 ? 'badge-danger' : ''}">${g.g} · ${g.t}</span><p class="muted small" style="margin-top:6px">${label}</p></div></div>
    <div class="axes">${E.AXES.map((a) => {
      const v = sc.axes[a.k]; const [c, t] = SRC[sc.src[a.k]]; const off = man.inst && a.k === '가';
      return `<div class="axis"${off ? ' style="opacity:.35"' : ''}><span class="nm">${esc(a.name)}<small>가중치 ${a.w}</small></span>
        <input type="range" min="0" max="5" step="0.5" value="${v}" data-act="axis" data-key="${esc(key)}" data-axis="${a.k}" aria-label="${esc(a.name)} 점수"${off ? ' disabled' : ''}>
        <span class="v">${(+v).toFixed(1)}</span><span class="src ${c}">${t}</span><span class="hint">${esc(a.hint)} — ${esc(E.ANCHORS[Math.round(v)])}</span></div>`;
    }).join('')}</div>
    <div class="row-gap"><label class="check"><input type="checkbox" data-act="inst" data-key="${esc(key)}"${man.inst ? ' checked' : ''}> 연주곡(가사 항목 제외)</label>
      ${man.axes && Object.keys(man.axes).length ? `<button type="button" class="btn-ghost" data-act="resetAxes" data-key="${esc(key)}">직접 채점 지우기</button>` : ''}
      <button type="button" class="btn-ghost" data-act="toRubric" data-key="${esc(key)}">8축 채점기로 보내기</button></div>
    <p class="muted small">기준: 5 장르의 교본 · 4 장르 상위 10% · 3 탄탄함 · 2 평범 · 1 약점이 눈에 띔 · 0 곡을 해침. 자동 측정은 근거 없이 4점을 넘지 않고(작곡은 멜로디를 들을 수 없어 3.5점까지), 인기·차트·수상은 점수에 넣지 않습니다.</p>
    ${fitBlock(key, an, sc.score)}</div>`;
}
function fitBlock(key, an, score) {
  const P = profile(key); const fit = fitOf(an, P);
  const hits = antiHits(an.features, an.mood, an.durationMs);
  if (fit == null) return `<p class="muted small">취향 적합도는 다른 음악을 3개 이상 담고 분석이 끝나면 계산됩니다. (현재 ${P.n}개)</p>`;
  const fin = +(score * 0.6 + fit * 0.4).toFixed(1);
  return `<div class="kv-grid"><div class="kv"><span>내 취향 적합도</span><b>${fit}</b><em>담은 ${P.n}개와의 소리·장르·창작자 겹침${hits.length ? ` · 감점: ${esc(hits.map((h) => h.label).join(', '))}` : ''}</em></div>
    <div class="kv"><span>취향 반영 점수</span><b>${fin}</b><em>음악성 × 0.6 + 취향 × 0.4${score >= 85 && fit < 50 ? ' · ✦ 취향 밖 유레카' : ''}</em></div></div>`;
}
function genreBlock(an) {
  if (!an.genres?.length) return `<div class="d-block"><h4>세부장르</h4><p class="muted small">공개 데이터베이스에 장르 정보가 없습니다.</p></div>`;
  return `<div class="d-block"><h4>세부장르</h4><div class="genres">${an.genres.map((g, i) => `<div class="genre${i ? '' : ' lead'}"><b>${esc(g.ko || g.name)}</b><span>${g.ko ? esc(g.name) + ' · ' : ''}비중 ${Math.round(g.weight * 100)}</span></div>`).join('')}</div>
    <p class="muted small">MusicBrainz 장르·태그(곡 › 아티스트 순 가중), Deezer 앨범 장르, Apple 대표 장르를 합쳐 비중을 매겼습니다.</p></div>`;
}
const ROLE_ORDER = ['작사·작곡', '작곡', '작사', '편곡', '프로듀서', '믹스', '엔지니어', '레코딩', '마스터링', '프로그래밍', '보컬'];
function creditBlock(an, isSet) {
  const cr = an.credits || [];
  const src = an.mbUrl ? `<a href="${esc(safeUrl(an.mbUrl))}" target="_blank" rel="noopener noreferrer">MusicBrainz 원본</a>` : 'MusicBrainz';
  if (!cr.length) return `<div class="d-block"><h4>작곡 · 작사 · 프로듀서</h4><p class="muted small">공개 데이터베이스(MusicBrainz)에 이 ${isSet ? '앨범' : '곡'}의 크레딧이 아직 없습니다. 앨범 속지나 멜론 곡 정보에서 확인할 수 있습니다.</p><p class="foot">출처: ${src}</p></div>`;
  const G = new Map(); for (const c of cr) { if (!G.has(c.role)) G.set(c.role, []); G.get(c.role).push(c.n > 1 ? `${c.name} (${c.n}곡)` : c.name); }
  const roles = [...G.keys()].sort((a, b) => (ROLE_ORDER.indexOf(a) + 1 || 99) - (ROLE_ORDER.indexOf(b) + 1 || 99));
  return `<div class="d-block"><h4>작곡 · 작사 · 프로듀서</h4><div class="stack">${roles.map((r) => `<div class="credit"><span>${esc(r)}</span><b>${esc(G.get(r).join(', '))}</b></div>`).join('')}</div><p class="foot">출처: ${src} (사용자 참여형 데이터베이스라 누락이 있을 수 있음)</p></div>`;
}
const kv = (l, v, n, m) => `<div class="kv"><span>${esc(l)}</span><b>${v}</b>${m != null ? `<div class="meter"><i style="width:${Math.round(C(m) * 100)}%"></i></div>` : ''}<em>${esc(n)}</em></div>`;
function moodBlock(an, it) {
  const f = an.features, m = an.mood;
  if (!f) return `<div class="d-block"><h4>곡의 느낌</h4><p class="muted small">미리듣기를 분석하지 못해 느낌을 측정하지 못했습니다.${an.bpmRef ? ` Deezer 기준 템포는 ${an.bpmRef} BPM입니다.` : ''}</p></div>`;
  const bpmN = f.pulse < 0.12 ? '박이 뚜렷하지 않아 템포 추정이 불확실함' : f.bpmRaw ? `측정 ${Math.round(f.bpmRaw)} → 배수 오류 보정` : '30초 구간 타격음 주기로 추정';
  const keyN = Math.abs(f.modeMargin) < 0.1 ? `장조·단조 구분 불확실 (확신도 ${f.keyR.toFixed(2)})` : `조성 확신도 ${f.keyR.toFixed(2)}`;
  const hits = antiHits(f, m, it.durationMs);
  return `<div class="d-block"><h4>곡의 느낌</h4><div class="mood-words">${esc(m.words.join(' · '))}</div>
    <div class="tags">${m.texture.map((t) => `<span>${esc(t)}</span>`).join('')}${hits.map((h) => `<span class="badge badge-danger">감점 요소: ${esc(h.label)}</span>`).join('')}</div>
    <div class="kv-grid four">
      ${kv('템포', `${Math.round(f.bpm)} <small class="muted">BPM</small>`, bpmN)}
      ${kv('조성', `${esc(f.keyName)} <small class="muted">${esc(f.camelot)}</small>`, keyN)}
      ${kv('에너지', Math.round(m.energy * 100), '박동·타악기·잡음 성분', m.energy)}
      ${kv('밝기', Math.round(C((f.centroid - 900) / 2600) * 100), `소리 무게중심 ${f.centroid.toLocaleString()} Hz`, (f.centroid - 900) / 2600)}
      ${kv('다이내믹 레인지', `${f.dr} <small class="muted">dB</small>`, f.dr > 12 ? '강약 대비 큼' : f.dr < 6 ? '세기 변화 적음' : '보통', f.dr / 16)}
      ${kv('공간감', Math.round(C(f.width / 0.6) * 100), f.width < 0.03 ? '거의 모노' : f.width > 0.35 ? '넓게 퍼짐' : '보통', f.width / 0.6)}
      ${kv('화성 움직임', Math.round(C(f.harmonicChange / 0.2) * 100), '1초 단위 음높이 분포 변화', f.harmonicChange / 0.2)}
      ${kv('어쿠스틱 질감', Math.round(m.acoustic * 100), '잡음성·고역·비트 규칙성', m.acoustic)}
    </div>
    <div class="svg-box" id="mQuad"></div>
    <p class="muted small">취향 지도 위치: <b>${esc(m.quad)}</b> (가로: 밴드·어쿠스틱 ↔ 전자·R&amp;B / 세로: 아련 ↔ 밝음)</p></div>`;
}
function trackDetail(it) {
  const key = it.key, an = getAn(key);
  let h = `<div class="row-gap" style="margin-bottom:16px">${it.preview || it.previewAlt ? `<button type="button" class="btn-secondary" data-act="play" data-key="${esc(key)}">▶ 미리듣기</button>` : ''}${chipsHtml(it.artist, it.altTitle || it.title, true)}</div>`;
  if (!an || S.pending.has(key)) return h + progressBlock(key);
  if (an.failed) return h + `<p class="muted">${esc(an.errors?.[0] || '분석 실패')}</p><button type="button" class="btn-secondary" data-act="reanalyze" data-key="${esc(key)}">다시 분석</button>`;
  h += reviewBlock(it, an) + scoreBlock(key, an) + genreBlock(an) + creditBlock(an, false) + moodBlock(an, it);
  h += `<p class="foot">${an.errors?.length ? esc(an.errors.join(' · ')) + '<br>' : ''}분석 한계: 음원 전체가 아닌 30초 미리듣기로 측정했습니다. 템포·조성·느낌은 신호 처리 추정치이고, 멜로디의 매력·가사·혁신성은 기계가 판정할 수 없어 직접 채점 항목으로 남겼습니다. 데이터: Apple iTunes Search API, Deezer API, MusicBrainz(CC0).
    <br><button type="button" class="btn-ghost" style="margin-top:6px" data-act="reanalyze" data-key="${esc(key)}">다시 분석</button></p>`;
  return h;
}

/* 아티스트·앨범 */
function setDetail(it) {
  const key = it.key, d = detailCache.get(key), an = getAn(key);
  let h = '';
  // 분석 요약
  h += `<div class="d-block"><h4>${it.kind === 'artist' ? '아티스트' : '앨범'} 분석</h4>`;
  if (S.pending.has(key)) h += progressBlock(key).replace('<div class="d-block"><h4>분석 중</h4>', '<div>');
  else if (!an || an.failed) h += `<p class="muted small">${an?.failed ? '분석에 실패했습니다.' : '분석을 준비 중입니다.'}</p>${an?.failed ? `<div><button type="button" class="btn-primary" data-act="analyzeSet" data-key="${esc(key)}">다시 분석</button></div>` : ''}`;
  else h += setAnalysis(it, an);
  h += '</div>';
  if (!d || d.loading) return h + '<div class="skeleton-box"></div>'.repeat(4);
  if (it.kind === 'artist') {
    const fl = S.albumFilter || 'all';
    const albums = (d.albums || []).filter((a) => fl === 'all' || (fl === 'single' ? a.recordType === 'single' : a.recordType !== 'single'));
    h += `<div class="d-block"><div class="section-label" style="margin:0"><span>인기곡 TOP ${d.tracks.length}</span>${d.tracks.length ? '<button type="button" class="btn-secondary" data-act="addTop5">+ 상위 5곡 담기</button>' : ''}</div>
      <div class="track-list">${d.tracks.map((t, i) => trackRow(t, i + 1)).join('') || `<p class="muted small">인기곡을 불러오지 못했습니다. <button type="button" class="btn-ghost" data-act="reloadDetail" data-key="${esc(key)}">다시 불러오기</button></p>`}</div></div>
      <div class="d-block"><div class="section-label" style="margin:0"><span>발매작 (${albums.length} · 최신순)</span>
        <span class="pill-group">${[['all', `전체 (${(d.albums || []).length})`], ['album', '정규·EP'], ['single', '싱글']].map(([k, l]) => `<button type="button" class="pill${fl === k ? ' active' : ''}" data-act="albumFilter" data-f="${k}">${l}</button>`).join('')}</span></div>
      <div class="album-grid">${albums.map(albumCard).join('') || '<p class="muted small">발매작이 없습니다.</p>'}</div></div>`;
  } else {
    h += `<div class="d-block"><div class="section-label" style="margin:0"><span>수록곡 (${d.tracks.length})</span>${d.tracks.length ? '<button type="button" class="btn-secondary" data-act="addAll">+ 전곡 담기</button>' : ''}</div>
      <div class="track-list">${d.tracks.map((t, i) => trackRow({ ...t, album: t.album || it.title, year: t.year || it.year }, i + 1)).join('') || '<p class="muted small">수록곡 목록을 찾지 못했습니다. 위의 ‘담기’로 앨범 단위로 담을 수 있습니다.</p>'}</div></div>`;
  }
  return h;
}
function moodWord(m) { const a = m.arousal, v = m.valence; if (a > 0.62) return v > 0.45 ? '신나고 밝은 쪽' : '강렬하고 어두운 쪽'; if (a < 0.4) return v > 0.55 ? '잔잔하고 포근한 쪽' : '차분하고 아련한 쪽'; return v > 0.55 ? '산뜻한 중간 템포' : v < 0.4 ? '가라앉은 중간 템포' : '담백한 중간 지대'; }
function setAnalysis(it, an) {
  const key = it.key, sc = scoreOf(it.kind, an, key), man = S.manual[key]?.axes || {};
  const ok = (an.analyzed || []).filter((t) => !t.failed);
  let h = it.kind === 'album' ? reviewBlock(it, an) : '';
  if (sc) {
    const g = E.grade(sc.score);
    const label = it.kind === 'album'
      ? `상위 3곡 평균 ${sc.top3} × 50% + 통일성 ${(+sc.tong).toFixed(1)}점 × 30% + 미적 일체감 ${(+sc.mi).toFixed(1)}점 × 20% (분석 ${sc.n}곡)`
      : `대표곡 평균 ${sc.mean} × 55% + 상위 3곡 ${sc.top3} × 30% + 일관성 ${(+sc.tong).toFixed(1)}점 × 15%${sc.penalty ? ` − 한 곡 의존 감점 ${sc.penalty}` : ''} (분석 ${sc.n}곡)`;
    const ax = it.kind === 'album' ? [['통', '통일성', '앨범 흐름의 일관성(측정)', an.auto?.통], ['미', '미적 일체감', '사운드·커버·콘셉트 일치(직접 평가)', undefined]] : [['통', '일관성', '대표곡들의 소리 일관성(측정)', an.auto?.통]];
    h += `<div class="score-box"><div class="score-big">${sc.score.toFixed(1)}<small> / 100</small></div><div><span class="badge ${sc.score >= 80 ? 'badge-ok' : sc.score < 60 ? 'badge-danger' : ''}">${g.g} · ${g.t}</span><p class="muted small" style="margin-top:6px">${label}</p></div></div>
      <div class="axes">${ax.map(([k, n, hint, auto]) => { const v = man[k] ?? auto ?? E.DEFAULT_UNMEASURED; const s = man[k] != null ? ['u', '직접'] : auto != null ? ['m', '측정'] : ['g', '기본값'];
        return `<div class="axis"><span class="nm">${n}</span><input type="range" min="0" max="5" step="0.5" value="${v}" data-act="axis" data-key="${esc(key)}" data-axis="${k}" aria-label="${n} 점수"><span class="v">${(+v).toFixed(1)}</span><span class="src ${s[0]}">${s[1]}</span><span class="hint">${esc(hint)} — ${esc(E.ANCHORS[Math.round(v)])}</span></div>`; }).join('')}</div>`;
    h += fitBlock(key, an, sc.score);
  }
  h += genreBlock(an);
  if (it.kind === 'album') h += creditBlock(an, true);
  if (an.mood && ok.length) {
    h += `<div class="d-block"><h4>전체 느낌</h4><div class="mood-words">${esc(moodWord(an.mood))}</div>
      <div class="kv-grid four">${kv('평균 템포', `${Math.round(mean(ok.map((t) => t.features.bpm)))} <small class="muted">BPM</small>`, `범위 ${Math.round(Math.min(...ok.map((t) => t.features.bpm)))}–${Math.round(Math.max(...ok.map((t) => t.features.bpm)))}`)}
      ${kv('단조 비율', `${Math.round((ok.filter((t) => t.features.mode === 'minor').length / ok.length) * 100)}%`, '분석한 곡 중 단조 판정 비율')}
      ${kv(it.kind === 'album' ? '통일성' : '일관성', an.cohesion == null ? '–' : Math.round(an.cohesion * 100), '곡들의 소리 성향이 비슷한 정도', an.cohesion ?? 0)}
      ${kv('평균 에너지', Math.round(mean(ok.map((t) => t.mood.energy)) * 100), '분석한 곡 평균', mean(ok.map((t) => t.mood.energy)))}</div>
      <div class="svg-box" id="mQuad"></div></div>`;
  }
  return h;
}
function drawModalQuad(key) {
  const box = $('#mQuad'); if (!box) return;
  const an = getAn(key); if (!an?.mood) return;
  const P = profile(key);
  const pts = P.pts.map((p) => ({ ...p, kind: 'faint' }));
  for (const t of an.analyzed || []) if (!t.failed) pts.push({ x: t.mood.x, y: t.mood.y, label: t.title, kind: 'small' });
  pts.push({ x: an.mood.x, y: an.mood.y, label: S.items.get(key)?.title || '', kind: 'focus' });
  box.innerHTML = quadSvg(pts);
}

/* ═══════════════ SVG 차트 ═══════════════ */
function radarSvg(items) {
  const cx = 190, cy = 165, R = 100, n = items.length;
  const pt = (i, r) => { const a = (Math.PI * 2 * i) / n - Math.PI / 2; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; };
  let g = '';
  for (const lv of [0.25, 0.5, 0.75, 1]) g += `<polygon points="${items.map((_, i) => pt(i, R * lv).map((v) => v.toFixed(1)).join(',')).join(' ')}" fill="none" stroke="var(--chart-grid)"/>`;
  items.forEach((_, i) => { const [x, y] = pt(i, R); g += `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--chart-axis)"/>`; });
  const data = items.map((it, i) => pt(i, R * C(it.v / 100, 0.04, 1)));
  g += `<polygon points="${data.map((p) => p.map((v) => v.toFixed(1)).join(',')).join(' ')}" fill="var(--accent-soft)" stroke="var(--accent)" stroke-width="2.2"/>`;
  g += data.map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" fill="var(--accent)"/>`).join('');
  items.forEach((it, i) => { const a = (Math.PI * 2 * i) / n - Math.PI / 2; const [x, y] = pt(i, R + 22); const anc = Math.cos(a) > 0.25 ? 'start' : Math.cos(a) < -0.25 ? 'end' : 'middle';
    g += `<text x="${x.toFixed(1)}" y="${(y + 4).toFixed(1)}" text-anchor="${anc}" fill="var(--text-secondary)" font-size="11.5" font-weight="600">${esc(it.label)} ${Math.round(it.v)}</text>`; });
  return `<svg viewBox="0 0 380 330" role="img" aria-label="소리 성향 6축">${g}</svg>`;
}
function quadSvg(pts) {
  const cx = 190, cy = 165, sx = 140, sy = 120;
  const col = { input: 'var(--accent)', rec: 'var(--emerald)', eureka: 'var(--amber)', faint: 'var(--text-muted)', small: 'var(--accent)', focus: '#F43F5E' };
  const dots = pts.slice(0, 60).map((p) => {
    const x = cx + C(p.x, -1, 1) * sx, y = cy - C(p.y, -1, 1) * sy;
    const r = p.kind === 'focus' ? 6.5 : p.kind === 'faint' ? 3.5 : p.kind === 'small' ? 3.5 : 5;
    const lbl = p.kind === 'faint' || p.kind === 'small' ? '' : `<text x="${(x + (x > cx ? -8 : 8)).toFixed(1)}" y="${(y + 3.5).toFixed(1)}" text-anchor="${x > cx ? 'end' : 'start'}" fill="var(--text-secondary)" font-size="9.5">${esc(String(p.label || '').slice(0, 16))}</text>`;
    return `<g><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}" fill="${col[p.kind] || col.input}" fill-opacity="${p.kind === 'faint' ? 0.45 : 0.95}" stroke="var(--bg-surface)" stroke-width="1.5"><title>${esc(p.label || '')}</title></circle>${lbl}</g>`;
  }).join('');
  return `<svg viewBox="0 0 380 330" role="img" aria-label="장르와 무드 4분면 지도"><rect x="30" y="25" width="320" height="280" rx="12" fill="var(--chart-bg)" stroke="var(--chart-grid)"/>
    <line x1="${cx}" y1="25" x2="${cx}" y2="305" stroke="var(--chart-axis)" stroke-dasharray="4 3"/><line x1="30" y1="${cy}" x2="350" y2="${cy}" stroke="var(--chart-axis)" stroke-dasharray="4 3"/>
    <text x="${cx}" y="17" text-anchor="middle" fill="var(--text-secondary)" font-size="11" font-weight="700">밝음 · 설렘</text><text x="${cx}" y="322" text-anchor="middle" fill="var(--text-secondary)" font-size="11" font-weight="700">아련 · 처연</text>
    <text x="38" y="${cy - 6}" fill="var(--text-muted)" font-size="10.5" font-weight="600">밴드·어쿠스틱</text><text x="342" y="${cy - 6}" text-anchor="end" fill="var(--text-muted)" font-size="10.5" font-weight="600">전자·댄스·R&amp;B</text>
    <text x="40" y="42" fill="var(--text-muted)" font-size="10" opacity=".7">청춘 기타팝</text><text x="340" y="42" text-anchor="end" fill="var(--text-muted)" font-size="10" opacity=".7">화사한 댄스</text>
    <text x="40" y="296" fill="var(--text-muted)" font-size="10" opacity=".7">서정의 발라드</text><text x="340" y="296" text-anchor="end" fill="var(--text-muted)" font-size="10" opacity=".7">밤의 R&amp;B</text>${dots}</svg>`;
}

/* ═══════════════ 취향 정밀 분석 리포트 ═══════════════ */
const DIMS = [
  { k: 'space', label: '공간감', get: (x) => C(x.f.width / 0.6), hi: '넓게 퍼지는 공간감', lo: '가깝고 좁은 무대' },
  { k: 'harm', label: '화성 움직임', get: (x) => C(x.f.harmonicChange / 0.2), hi: '코드가 자주 움직이는 화성', lo: '반복적이고 안정된 화성' },
  { k: 'beat', label: '비트 선명도', get: (x) => C((x.f.pulse - 0.1) / 0.6), hi: '또렷한 비트와 그루브', lo: '박이 앞에 나서지 않는 흐름' },
  { k: 'energy', label: '에너지', get: (x) => x.m.energy, hi: '높은 에너지', lo: '잔잔한 에너지' },
  { k: 'bright', label: '밝기', get: (x) => C((x.f.centroid - 900) / 2600), hi: '밝고 선명한 톤', lo: '어둡고 따뜻한 톤' },
  { k: 'acoustic', label: '어쿠스틱', get: (x) => x.m.acoustic, hi: '생악기 중심의 어쿠스틱 질감', lo: '전자음 중심의 질감' },
];
function step(lines, i) { return `<div class="card"><h3 class="card-title" style="margin-bottom:10px">취향 분석 중</h3><div class="progress-list">${lines.map((s, j) => `<div class="${j < i ? 'done' : j === i ? 'now' : ''}">${esc(s)}</div>`).join('')}</div></div>`; }
async function runAnalysis() {
  if (!S.lib.entries.length) { toast('먼저 취향 바구니에 1개 이상 담아 주세요.'); return; }
  const btn = $('#analyzeBtn'), area = $('#report');
  btn.disabled = true; area.hidden = false;
  const lines = ['담은 음악 분석 마무리', '취향 공식 계산', '연관 아티스트 탐색(Deezer)', '추천 후보 미리듣기 측정', '리포트 작성'];
  const show = (i) => { area.innerHTML = step(lines, i); };
  try {
    show(0); btn.textContent = '담은 음악 분석 마무리 중…';
    for (const e of S.lib.entries) if (!e.an) { reg(e.item); analyze(e.item); }
    await Promise.all(S.lib.entries.map((e) => (S.pending.get(e.key)?.promise || Promise.resolve())));
    show(1); const P = profile();
    if (!P.fs.length) { area.innerHTML = '<div class="card"><p>분석된 음원이 없어 취향을 계산할 수 없습니다. 미리듣기가 있는 곡을 담아 주세요.</p></div>'; return; }
    show(2); btn.textContent = '추천 후보 찾는 중…';
    const recs = await buildRecs(P, (i, n) => { lines[3] = `추천 후보 미리듣기 측정 ${i}/${n}`; show(3); });
    show(4);
    S.report = makeReport(P, recs);
    renderReport();
    area.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    console.warn(e); area.innerHTML = '<div class="card"><p>분석 중 오류가 났습니다. 잠시 뒤 다시 실행해 주세요.</p></div>';
  } finally { btn.disabled = false; btn.textContent = '내 음악 취향 정밀 분석 다시 실행'; }
}
async function buildRecs(P, onProg) {
  const tops = [...P.artists.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 4);
  const have = new Set(S.lib.entries.map((e) => (e.kind === 'artist' ? e.item.title : e.item.artist || '').toLowerCase()));
  const lists = await Promise.all(tops.map(([n, v]) => E.relatedArtists(n, v.id).catch(() => [])));
  const freq = new Map();
  lists.forEach((l, li) => l.forEach((a, i) => { if (have.has(a.title.toLowerCase())) return; const c = freq.get(a.title) || { a, n: 0, from: new Set(), rank: 0 }; c.n++; c.from.add(tops[li][0]); c.rank += i; freq.set(a.title, c); }));
  const cands = [...freq.values()].sort((x, y) => y.n - x.n || x.rank - y.rank).slice(0, 7);
  const tracks = [];
  for (const c of cands) { const t = await E.artistTopTracks(c.a).catch(() => []); t.slice(0, 2).forEach((x) => tracks.push({ t: x, c })); }
  const out = [];
  for (let i = 0; i < tracks.length; i++) {
    onProg(i + 1, tracks.length);
    const { t, c } = tracks[i];
    if (!t.preview) continue;
    try {
      const f = E.fixTempo(await E.analyzeAudio(t.preview), 0); const m = E.moodOf(f, []); const auto = E.autoAxes(f, 'other').axes;
      const an = { features: f, mood: m, vec: E.vec(f, m), durationMs: t.durationMs };
      const fit = fitOf(an, P) ?? Math.round(60 - antiPenalty(f, m, t.durationMs));
      const score = E.musicScore(auto);
      out.push({ t, c, f, m, fit, score, rank: fit * 0.6 + score * 0.4 });
    } catch { /* 미리듣기 차단 곡은 건너뜀 */ }
  }
  const seen = new Set();
  const songs = out.sort((a, b) => b.rank - a.rank).filter((r) => { if (seen.has(r.c.a.title)) return false; seen.add(r.c.a.title); return true; }).slice(0, 6);
  const albums = [];
  for (const r of songs.slice(0, 3)) { if (r.t.album && r.t.deezerAlbumId) albums.push({ kind: 'album', title: r.t.album, artist: r.t.artist, artwork: r.t.artwork, deezerId: r.t.deezerAlbumId, why: `추천곡 ‘${r.t.title}’ 수록` }); }
  return { songs, artists: cands.slice(0, 5), albums };
}
function makeReport(P, recs) {
  const fs = P.fs;
  const radar = DIMS.map((d) => { const vals = fs.map(d.get); return { ...d, v: mean(vals) * 100, sd: sd(vals) }; });
  const ranked = [...radar].map((d) => ({ ...d, s: (1 - Math.min(1, d.sd / 0.35)) * Math.abs(d.v / 100 - 0.5) * 2 })).sort((a, b) => b.s - a.s);
  const ess = ranked.slice(0, 3).map((d) => ({ name: d.v >= 50 ? d.hi : d.lo, desc: `${d.label} 평균 ${Math.round(d.v)} · 곡 간 편차 ${Math.round(d.sd * 100)} (작을수록 일관된 취향)`, opp: d.v >= 50 ? d.lo : d.hi }));
  const bpms = fs.map((x) => x.f.bpm), minor = fs.filter((x) => x.f.mode === 'minor').length / fs.length;
  const ax = mean(P.pts.map((p) => p.x)), ay = mean(P.pts.map((p) => p.y));
  const quad = ay >= 0 ? (ax < 0 ? '청춘 기타팝' : '화사한 댄스') : (ax < 0 ? '서정의 발라드' : '밤의 R&B');
  const tg = topGenres(P, 4); const totalG = [...P.genres.values()].reduce((a, b) => a + b, 0) || 1;
  const gText = tg.length ? tg.map((g) => `${E.GENRE_KO[g] || g} ${Math.round((P.genres.get(g) / totalG) * 100)}%`).join(' · ') : '장르 정보 부족';
  const creators = [...P.credits.values()].filter((c) => c.n >= 2).sort((a, b) => b.n - a.n).slice(0, 3);
  const en = mean(fs.map((x) => x.m.energy));
  const headline = `${quad} 쪽, ${ess[0].name}에 끌리는 리스너`;
  const core = `분석한 ${fs.length}곡은 템포 <b>${Math.round(qtl(bpms, 0.25))}–${Math.round(qtl(bpms, 0.75))} BPM</b>, 에너지 <b>${Math.round(en * 100)}</b>/100, 단조 비율 <b>${Math.round(minor * 100)}%</b>에 모여 있습니다. 곡이 바뀌어도 가장 일관되게 유지되는 특징은 <b>${esc(ess[0].name)}</b>, <b>${esc(ess[1].name)}</b>, <b>${esc(ess[2].name)}</b>입니다.${creators.length ? ` 크레딧에는 <b>${esc(creators.map((c) => c.name).join(', '))}</b>의 이름이 반복해서 나옵니다.` : ''}`;
  const cnt = { '청춘 기타팝': 0, '화사한 댄스': 0, '서정의 발라드': 0, '밤의 R&B': 0 };
  P.pts.forEach((p) => { cnt[p.y >= 0 ? (p.x < 0 ? '청춘 기타팝' : '화사한 댄스') : (p.x < 0 ? '서정의 발라드' : '밤의 R&B')]++; });
  const empty = Object.entries(cnt).sort((a, b) => a[1] - b[1])[0];
  const inEmpty = recs.songs.find((r) => (r.m.y >= 0 ? (r.m.x < 0 ? '청춘 기타팝' : '화사한 댄스') : (r.m.x < 0 ? '서정의 발라드' : '밤의 R&B')) === empty[0]);
  const blind = `취향 지도에서 ‘${empty[0]}’ 영역이 가장 비어 있습니다(${empty[1]}곡).${inEmpty ? ` 이 영역의 추천곡 ‘${inEmpty.t.title}’(${inEmpty.t.artist})부터 들어 보면 범위를 넓히기 좋습니다.` : ' 이 영역의 곡을 몇 개 담아 보면 취향 경계가 더 분명해집니다.'}`;
  const formula = {
    version: `v${S.lib.version || 1}`,
    ess: ess.map((e) => ({ ...e, w: 25 })),
    bonus: [tg[0] && { name: `${E.GENRE_KO[tg[0]] || tg[0]} 계열`, w: 10 }, creators[0] ? { name: `${creators[0].name} 참여작`, w: 8 } : { name: `템포 ${Math.round(qtl(bpms, 0.25))}–${Math.round(qtl(bpms, 0.75))} BPM`, w: 8 }, { name: `${quad} 분면`, w: 7 }].filter(Boolean),
    ded: [...ANTI.filter((a) => S.anti.includes(a.id)).map((a) => a.label), ...ess.slice(0, 2).map((e) => `반대 성향: ${e.opp}`)],
  };
  const prev = S.lib.prevTop || [], now = topGenres(P, 5);
  const added = now.filter((g) => !prev.includes(g)).map((g) => E.GENRE_KO[g] || g), dropped = prev.filter((g) => !now.includes(g)).map((g) => E.GENRE_KO[g] || g);
  const change = prev.length && (added.length || dropped.length) ? `직전 버전 대비 ${added.length ? '새로 들어온 장르: ' + added.join(', ') : ''}${added.length && dropped.length ? ' · ' : ''}${dropped.length ? '밀려난 장르: ' + dropped.join(', ') : ''}` : '';
  const pts = [...P.pts, ...recs.songs.map((r) => ({ x: r.m.x, y: r.m.y, label: r.t.title, kind: r.score >= 85 && r.fit < 50 ? 'eureka' : 'rec' }))];
  return { headline, core, gText, blind, radar, formula, change, pts, recs, n: fs.length, quad, items: S.lib.entries.length };
}
function renderReport() {
  const R = S.report; const area = $('#report'); if (!R) return;
  const card = [`[청음실 취향 프로필 카드 ${R.formula.version}]`, `• 핵심: ${R.headline}`, `• 장르: ${R.gText}`, `• 필수 공식: ${R.formula.ess.map((e) => `${e.name}(${e.w})`).join(' + ')}`, `• 감점: ${R.formula.ded.join(', ') || '없음'}`, `• 기준 곡: ${S.lib.entries.slice(0, 8).map((e) => `${e.item.artist ? e.item.artist + '-' : ''}${e.item.title}`).join(', ')}`].join('\n');
  S.cardText = card;
  const recCards = R.recs.songs.map((r, i) => {
    const key = reg(r.t);
    return `<div class="rec-card"><div><div class="row-gap" style="justify-content:space-between;margin-bottom:8px"><span class="badge ${r.score >= 85 && r.fit < 50 ? 'badge-warn' : 'badge-ok'}">${r.score >= 85 && r.fit < 50 ? '✦ 유레카' : '●'} 취향 적합도 ${r.fit}</span><span class="small" style="font-weight:800;color:var(--accent-hover)">측정 음악성 ${r.score.toFixed(1)}</span></div>
      <div class="rec-head"><img src="${esc(art(r.t))}" alt="" loading="lazy"><div style="min-width:0"><div class="track-title" style="font-size:15px">${esc(r.t.title)}</div><div class="track-sub">${esc(r.t.artist)}</div></div></div>
      <p class="small" style="margin-top:8px;line-height:1.55">${esc(r.m.words.join(' · '))} · ${Math.round(r.f.bpm)} BPM · ${esc(r.f.keyName)}. 담은 ${esc([...r.c.from].join(', '))}와(과) 연관된 아티스트입니다.</p></div>
      <div class="rec-foot">${chipsHtml(r.t.artist, r.t.title)}<span class="row-gap">${r.t.preview ? `<button type="button" class="icon-btn" data-act="play" data-key="${esc(key)}" title="미리듣기">▶</button>` : ''}<button type="button" class="btn-secondary" style="padding:5px 9px;font-size:11.5px" data-act="open" data-key="${esc(key)}">분석</button><button type="button" class="icon-btn${entry(key) ? ' added' : ''}" data-act="add" data-key="${esc(key)}" title="담기">${entry(key) ? '✓' : '+'}</button></span></div></div>`;
  }).join('') || '<p class="muted small">연관 아티스트를 찾지 못했습니다. 아티스트가 다양한 곡을 더 담아 주세요.</p>';
  area.innerHTML = `
    <div class="card"><div class="card-header"><div><span class="badge">취향 공식 ${esc(R.formula.version)} · 담은 ${R.items}개 · 분석 음원 ${R.n}곡</span><h2 class="report-h">${esc(R.headline)}</h2></div><button type="button" class="btn-secondary" data-act="copyCard">취향 프로필 카드 복사</button></div>
      <p class="lead">${R.core}</p>
      <div class="stack" style="margin-bottom:12px"><div class="info-box"><b style="color:var(--accent-hover)">장르 스펙트럼:</b> ${esc(R.gText)}</div><div class="info-box"><b style="color:var(--amber-text)">아직 비어 있는 영역:</b> ${esc(R.blind)}</div>${R.change ? `<div class="info-box muted">${esc(R.change)}</div>` : ''}</div>
      <div class="mono-card">${esc(card)}</div></div>
    <div class="report-grid-2">
      <div class="card"><div class="card-header"><div><h3 class="card-title">소리 성향 6축</h3><p class="card-desc">담은 음악의 미리듣기를 실제로 측정한 평균값(0~100)</p></div></div>
        <div class="svg-box">${radarSvg(R.radar.map((d) => ({ label: d.label, v: d.v })))}</div>
        <div class="stack" style="margin-top:12px">${R.radar.map((d) => `<div class="info-box small"><b>${esc(d.label)} ${Math.round(d.v)}:</b> <span class="muted">${esc(d.v >= 50 ? d.hi : d.lo)} 쪽 · 곡 간 편차 ${Math.round(d.sd * 100)}</span></div>`).join('')}</div></div>
      <div class="card"><div class="card-header"><div><h3 class="card-title">장르 × 무드 4분면 지도</h3><p class="card-desc">파랑: 담은 음악 · 초록: 추천 · 주황: 취향 밖 유레카</p></div></div>
        <div class="svg-box">${quadSvg(R.pts)}</div>
        <h4 style="font-size:13.5px;margin:14px 0 8px">나만의 100점 취향 공식 (${esc(R.formula.version)})</h4>
        <div class="stack">${R.formula.ess.map((e) => `<div class="formula-bar"><div><div style="font-size:13px;font-weight:700">[필수] ${esc(e.name)}</div><div class="muted small">${esc(e.desc)}</div></div><span class="badge">+${e.w}</span></div>`).join('')}
        ${R.formula.bonus.map((b) => `<div class="formula-bar"><div style="font-size:12.5px;font-weight:600">[가산] ${esc(b.name)}</div><span class="badge badge-ok">+${b.w}</span></div>`).join('')}
        ${R.formula.ded.length ? `<div class="formula-bar"><div style="font-size:12.5px;font-weight:600">[감점] ${esc(R.formula.ded.join(' · '))}</div><span class="badge badge-danger">−15씩</span></div>` : ''}</div></div>
    </div>
    <div class="card"><div class="card-header"><div><h3 class="card-title">취향 기반 추천곡 (차트 인기 배제)</h3><p class="card-desc">담은 아티스트의 Deezer 연관 아티스트 → 대표곡 미리듣기를 실제로 측정해 취향 적합도 × 0.6 + 측정 음악성 × 0.4로 정렬</p></div></div>
      <div class="report-grid-3">${recCards}</div></div>
    <div class="report-grid-2">
      <div class="card"><h3 class="card-title" style="margin-bottom:12px">추천 아티스트</h3><div class="stack">${R.recs.artists.map((c) => { const k = reg(c.a); return `<div class="formula-bar"><div class="rec-head" style="cursor:pointer" data-act="open" data-key="${esc(k)}"><img src="${esc(art(c.a))}" alt="" style="width:40px;height:40px;border-radius:999px"><div><div style="font-weight:800">${esc(c.a.title)}</div><div class="muted small">${esc([...c.from].join(', '))}와(과) 연관${c.n > 1 ? ` · ${c.n}명과 겹침` : ''}</div></div></div>${chipsHtml(c.a.title, '')}</div>`; }).join('') || '<p class="muted small">없음</p>'}</div></div>
      <div class="card"><h3 class="card-title" style="margin-bottom:12px">통째로 들어 볼 앨범</h3><div class="stack">${R.recs.albums.map((a) => { const k = reg(a); return `<div class="formula-bar"><div class="rec-head" style="cursor:pointer" data-act="open" data-key="${esc(k)}"><img src="${esc(art(a))}" alt="" style="width:40px;height:40px"><div><div style="font-weight:800">${esc(a.title)}</div><div class="muted small">${esc(a.artist)} · ${esc(a.why)}</div></div></div>${chipsHtml(a.artist, a.title)}</div>`; }).join('') || '<p class="muted small">없음</p>'}</div></div>
    </div>
    <p class="muted small" style="text-align:center">모든 수치는 30초 미리듣기 신호 측정값과 공개 데이터베이스(MusicBrainz·Deezer·Apple)에서 계산했습니다. 멜로디의 매력·가사는 기계가 판정할 수 없어 점수에서 기본값으로 둡니다.</p>`;
  syncPlay();
}

/* ═══════════════ 8축 채점 탭 ═══════════════ */
const RD = { 작: 3, 편: 3, 연: 3, 가: 3, 혁: 3, 통: 3, 유: 2, 미: 3 };
S.rubric = { axes: { ...RD }, src: {}, an: null, item: null };
function renderRubricAxes() {
  const opts = [5, 4.5, 4, 3.5, 3, 2.5, 2, 1.5, 1, 0.5, 0];
  const lab = { 5: '5 정점', 4: '4 상위10%', 3: '3 평작', 2: '2 관습적', 1: '1 약점', 0: '0 해침' };
  $('#rAxes').innerHTML = E.AXES.map((a) => `<tr><td><b>${esc(a.name)}</b>${S.rubric.src[a.k] === 'm' ? ' <span class="src m">측정</span>' : ''}</td><td>${a.w}%</td>
    <td><select class="field-select" data-act="raxis" data-axis="${a.k}">${opts.map((o) => `<option value="${o}"${+S.rubric.axes[a.k] === o ? ' selected' : ''}>${lab[o] || o}</option>`).join('')}</select></td><td class="hint">${esc(a.hint)}</td></tr>`).join('');
}
function calcRubric() {
  const title = $('#rTitle').value.trim() || '제목 미입력', artist = $('#rArtist').value.trim() || '아티스트 미입력';
  const ev = $('#rEvidence').value, inst = $('#rInst').checked, notes = $('#rNotes').value.trim();
  const cap = ev === 'C' || ev === 'J'; const alerts = [], strong = [], weak = []; const axes = {};
  for (const a of E.AXES) {
    let v = +S.rubric.axes[a.k];
    if ((cap || (ev === 'B' && S.rubric.src[a.k] !== 'm' && !S.rubric.an)) && v > 4) { alerts.push(`${a.name} ${v}점 → 근거 등급 ${ev} 상한으로 4점`); v = 4; }
    axes[a.k] = v;
    if (!(inst && a.k === '가')) { if (v >= 4) strong.push(`${a.name}(${v})`); if (v <= 2) weak.push(`${a.name}(${v})`); }
  }
  let score = E.musicScore(axes, inst);
  if (cap && score > 80) { alerts.push(`총점 ${score} → 근거 등급 ${ev} 상한으로 80점`); score = 80; }
  const v = score >= 90 ? ['시대·장르 대표작급 (90+)', 'badge-ok'] : score >= 80 ? ['수작 · 완성도 높음 (80–89)', 'badge-ok'] : score >= 68 ? ['준수 · 일부 구조적 한계 (68–79)', ''] : ['평범·관습적 · 엄격 기준 미달 (68 미만)', 'badge-danger'];
  let fitH = '';
  if (S.rubric.an?.features) { const P = profile(S.rubric.item?.key); const fit = fitOf(S.rubric.an, P); if (fit != null) fitH = `<div class="kv-grid" style="margin-bottom:12px"><div class="kv"><span>내 취향 적합도</span><b>${fit}</b><em>바구니 ${P.n}개 기준</em></div><div class="kv"><span>취향 반영 점수</span><b>${(score * 0.6 + fit * 0.4).toFixed(1)}</b><em>음악성 × 0.6 + 취향 × 0.4</em></div></div>`; }
  const m = S.rubric.an?.mood, f = S.rubric.an?.features;
  $('#rResult').innerHTML = `<div class="score-box" style="margin-bottom:12px;grid-template-columns:minmax(0,1fr) auto"><div><span class="badge ${v[1]}">${v[0]}</span><div style="font-size:17px;font-weight:800;margin-top:6px">${esc(artist)} – ${esc(title)}</div><div class="muted small">근거 등급 ${ev} · ${inst ? '연주곡 재정규화' : '8축 표준'}</div></div><div class="score-big">${score.toFixed(1)}<small> / 100</small></div></div>
    ${alerts.length ? `<div class="notice" style="margin:0 0 12px"><b>상한 규칙 적용:</b><br>${alerts.map((a) => '• ' + esc(a)).join('<br>')}</div>` : ''}
    ${fitH}
    ${f ? `<div class="info-box small" style="margin-bottom:8px"><b>측정값:</b> ${esc(m.words.join(' · '))} · ${Math.round(f.bpm)} BPM · ${esc(f.keyName)} · 에너지 ${Math.round(m.energy * 100)}</div>` : ''}
    <div class="stack small"><div class="info-box"><b>강점 (4점 이상):</b> ${esc(strong.join(', ') || '없음')}</div><div class="info-box"><b>보완 (2점 이하):</b> ${esc(weak.join(', ') || '없음')}</div><div class="info-box"><b>메모:</b> ${esc(notes || '구체적 근거를 적으면 여기에 남습니다.')}</div></div>
    <div class="row-gap" style="margin-top:12px">${chipsHtml(artist, title, true)}${S.rubric.item ? `<button type="button" class="btn-secondary" data-act="rSave">이 점수를 바구니 곡에 반영</button>` : ''}</div>
    <p class="muted small" style="margin-top:12px">인기·차트 순위는 점수에 넣지 않습니다. 측정 항목은 30초 미리듣기 신호 기준이고, 나머지는 직접 들어 보고 고른 값입니다.</p>`;
}
async function measureRubric() {
  const t = $('#rTitle').value.trim(), a = $('#rArtist').value.trim();
  if (!t) { toast('곡명을 먼저 입력해 주세요.'); return; }
  const b = $('#measureBtn'); b.disabled = true; b.textContent = '곡 찾는 중…';
  try {
    const it = await E.resolveTrack(a ? `${a} - ${t}` : t);
    if (!it) { toast('곡을 찾지 못했습니다. 철자를 확인해 주세요.'); return; }
    reg(it); S.rubric.item = it;
    $('#measureNote').textContent = `찾은 곡: ${it.artist} – ${it.title}${it.altTitle ? ` (${it.altTitle})` : ''} · 분석 중…`;
    b.textContent = '음향 측정 중…';
    const an = getAn(it.key) || await analyze(it);
    S.rubric.an = an;
    if (an?.auto) for (const k of Object.keys(an.auto)) { S.rubric.axes[k] = Math.round(an.auto[k] * 2) / 2; S.rubric.src[k] = 'm'; }
    if (an?.genres?.length && !$('#rGenre').value) $('#rGenre').value = `${an.genres.slice(0, 2).map((g) => g.ko || g.name).join(' · ')}${it.year ? ' · ' + it.year : ''}`;
    $('#measureNote').textContent = an?.features ? `찾은 곡: ${it.artist} – ${it.title} · 작곡(화성)·편곡 항목을 측정값으로 채웠습니다. 나머지는 직접 골라 주세요.` : `찾은 곡: ${it.artist} – ${it.title} · 미리듣기를 분석하지 못해 측정값이 없습니다.`;
    renderRubricAxes(); calcRubric();
  } finally { b.disabled = false; b.textContent = '곡 찾아서 음향 측정하기'; }
}

/* ═══════════════ 붙여넣기·샘플·백업 ═══════════════ */
const PRESETS = {
  garage: ['NewJeans - Ditto', 'izna - SIGN', '宇多田ヒカル - One Last Kiss', 'SZA - Snooze', 'LE SSERAFIM - Impurities', '이하이 - 안전지대'],
  band: ['검정치마 - Ling Ling', '藤井風 - 死ぬのがいいわ', '최유리 - 숲', '한로로 - 입춘', 'ヨルシカ - 春泥棒', '羊文学 - more than words'],
  glam: ['Zara Larsson - Midnight Sun', 'JENNIE - Seoul City', '우주소녀 - 이루리', 'TWICE - I CAN\'T STOP ME', 'Tate McRae - Sports car', 'Dua Lipa - Houdini'],
};
async function addLines(lines, onProg) {
  let ok = 0; const miss = [];
  for (let i = 0; i < lines.length; i++) {
    onProg?.(i + 1, lines.length, lines[i]);
    const it = await E.resolveTrack(lines[i]).catch(() => null);
    if (it && addItem(it, true)) ok++; else if (!it) miss.push(lines[i]);
  }
  afterLibChange();
  return { ok, miss };
}
async function runPreset(p) {
  toast('샘플 곡을 찾는 중…');
  const { ok, miss } = await addLines(PRESETS[p] || [], (i, n) => { $('#queueText').textContent = `샘플 찾는 중 ${i}/${n}`; });
  toast(`샘플 ${ok}곡을 담았습니다${miss.length ? ` · 못 찾음: ${miss.join(', ')}` : ''}`);
}
async function runBulk() {
  const lines = $('#bulkText').value.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) { toast('곡 목록을 입력해 주세요.'); return; }
  const b = $('#bulkRun'); b.disabled = true;
  const { ok, miss } = await addLines(lines, (i, n, l) => { $('#bulkMsg').textContent = `찾는 중 ${i}/${n}: ${l}`; });
  b.disabled = false; $('#bulkMsg').textContent = '줄마다 가장 정확한 곡을 찾아 담습니다.';
  if (!miss.length) { $('#bulkText').value = ''; $('#bulk').hidden = true; } else $('#bulkText').value = miss.join('\n');
  toast(`${ok}곡을 담았습니다${miss.length ? ` · 못 찾은 ${miss.length}줄은 입력창에 남겨 두었습니다` : ''}`);
}
function exportLib() {
  const blob = new Blob([JSON.stringify({ app: 'cheongeumsil', v: 2, lib: S.lib, manual: S.manual, anti: S.anti }, null, 1)], { type: 'application/json' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `청음실-취향-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
async function importLib(file) {
  try {
    const d = JSON.parse(await file.text());
    if (d.app !== 'cheongeumsil' || !Array.isArray(d.lib?.entries)) throw new Error();
    const have = new Set(S.lib.entries.map((e) => e.key)); let n = 0;
    for (const e of d.lib.entries) if (e?.key && e.item && !have.has(e.key)) { S.lib.entries.push(e); n++; }
    Object.assign(S.manual, d.manual || {}); if (Array.isArray(d.anti)) S.anti = d.anti;
    S.lib.version = Math.max(S.lib.version || 0, d.lib.version || 0) + (n ? 1 : 0);
    saveLib(); saveManual(); lsSet('ctl:anti', S.anti); renderAnti(); afterLibChange(); toast(`${n}개를 불러왔습니다.`);
  } catch { toast('청음실 백업 파일이 아니거나 손상되었습니다.'); }
}

/* ═══════════════ 이벤트 ═══════════════ */
function setTab(t) {
  S.tab = t; $('#viewAnalyze').hidden = t !== 'analyze'; $('#viewRubric').hidden = t !== 'rubric';
  $$('.nav-btn').forEach((b) => b.classList.toggle('active', b.dataset.tab === t));
  if (t === 'rubric') { renderRubricAxes(); calcRubric(); }
  window.scrollTo(0, 0);
}
document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]'); if (!el) return;
  const a = el.dataset.act, key = el.dataset.key;
  if (el.tagName === 'A' && a === 'tab') e.preventDefault();
  switch (a) {
    case 'tab': setTab(el.dataset.tab); break;
    case 'filter': setFilter(el.dataset.f); break;
    case 'q': qInput.value = el.dataset.q; setTab('analyze'); closeModal(); doSearch(true); break;
    case 'retry': doSearch(true); break;
    case 'open': e.stopPropagation(); openModal(key); break;
    case 'play': e.stopPropagation(); { const it = S.items.get(key); if (it) play(it); } break;
    case 'add': e.stopPropagation(); toggleItem(key); break;
    case 'remove': removeItem(key); break;
    case 'manual': { const r = S.res?.q || ''; const p = r.split(/\s*[-–—]\s*/); const it = { kind: 'track', title: (p[1] || p[0]).trim(), artist: p[1] ? p[0].trim() : '직접 입력', genre: '직접 입력', srcs: ['manual'] }; addItem(it); break; }
    case 'preset': runPreset(el.dataset.p); break;
    case 'btype': S.btype = el.dataset.t; $$('#basketTypes .pill').forEach((p) => p.classList.toggle('active', p.dataset.t === S.btype)); renderBasket(); break;
    case 'anti': { const id = el.dataset.id; S.anti = S.anti.includes(id) ? S.anti.filter((x) => x !== id) : [...S.anti, id]; lsSet('ctl:anti', S.anti); renderAnti(); renderBasket(); break; }
    case 'analyze': runAnalysis(); break;
    case 'export': exportLib(); break;
    case 'clearAsk': el.hidden = true; $('[data-act="clearYes"]').hidden = false; setTimeout(() => { el.hidden = false; $('[data-act="clearYes"]').hidden = true; }, 4000); break;
    case 'clearYes': S.lib = { entries: [], version: 0, prevTop: [] }; saveLib(); afterLibChange(); el.hidden = true; $('[data-act="clearAsk"]').hidden = false; toast('바구니를 비웠습니다.'); break;
    case 'bulkOpen': $('#bulk').hidden = false; $('#bulkText').focus(); break;
    case 'bulkClose': $('#bulk').hidden = true; break;
    case 'bulkRun': runBulk(); break;
    case 'mClose': closeModal(); break;
    case 'mBack': S.stack.pop(); renderModal(); break;
    case 'mAdd': toggleItem(key); break;
    case 'reloadDetail': { const it = S.items.get(key); if (it) { detailCache.delete(key); loadDetail(it); renderModal(); } break; }
    case 'albumFilter': S.albumFilter = el.dataset.f; renderModal(); break;
    case 'addTop5': { const d = detailCache.get(curKey()); let n = 0; (d?.tracks || []).slice(0, 5).forEach((t) => { if (addItem(t, true)) n++; }); afterLibChange(); toast(`인기곡 ${n}곡을 담았습니다.`); break; }
    case 'addAll': { const k = curKey(); const it = S.items.get(k); const d = detailCache.get(k); let n = 0; (d?.tracks || []).forEach((t) => { if (addItem({ ...t, album: t.album || it.title }, true)) n++; }); afterLibChange(); toast(`수록곡 ${n}곡을 담았습니다.`); break; }
    case 'analyzeSet': { const it = S.items.get(key); if (it) { const ent = entry(key); if (ent?.an?.failed) ent.an = null; analyze(it); renderModal(); } break; }
    case 'reanalyze': { const ent = entry(key); if (ent) { ent.an = null; saveLib(); } try { localStorage.removeItem('ctl:a:' + key); } catch { /* 무시 */ } const it = S.items.get(key) || ent?.item; if (it) { reg(it); analyze(it); renderModal(); } break; }
    case 'resetAxes': delete S.manual[key]; saveManual(); renderModal(); renderBasket(); break;
    case 'toRubric': { const it = S.items.get(key); if (!it) break; closeModal(); $('#rTitle').value = it.title; $('#rArtist').value = it.artist || ''; S.rubric = { axes: { ...RD }, src: {}, an: getAn(key), item: it }; const an = S.rubric.an; if (an?.auto) for (const k of Object.keys(an.auto)) { S.rubric.axes[k] = Math.round(an.auto[k] * 2) / 2; S.rubric.src[k] = 'm'; } const man = S.manual[key]?.axes || {}; Object.assign(S.rubric.axes, man); const cr = S.critic.get(key); $('#rEvidence').value = cr?.ratings?.filter((r) => !r.aggregate).length >= 2 ? 'A' : 'C'; setTab('rubric'); break; }
    case 'measure': measureRubric(); break;
    case 'rSave': { const it = S.rubric.item; if (!it) break; S.manual[it.key] = { ...(S.manual[it.key] || {}), axes: { ...S.rubric.axes }, inst: $('#rInst').checked }; saveManual(); renderBasket(); toast(entry(it.key) ? '바구니의 곡 점수에 반영했습니다.' : '저장했습니다. 이 곡을 담으면 이 점수로 표시됩니다.'); break; }
    case 'copyCard': navigator.clipboard?.writeText(S.cardText || '').then(() => toast('취향 프로필 카드를 복사했습니다.'), () => toast('복사하지 못했습니다. 카드 내용을 직접 선택해 주세요.')); break;
    default: break;
  }
});
document.addEventListener('input', (e) => {
  const el = e.target;
  if (el.dataset.act === 'axis') { const row = el.closest('.axis'); row.querySelector('.v').textContent = (+el.value).toFixed(1); const s = row.querySelector('.src'); s.className = 'src u'; s.textContent = '직접'; }
  if (el.id === 'basketFilter') { S.bfilter = el.value; renderBasket(); }
  if (['rTitle', 'rArtist', 'rGenre', 'rNotes'].includes(el.id)) { if (el.id === 'rTitle' || el.id === 'rArtist') { S.rubric.item = null; S.rubric.an = null; S.rubric.src = {}; } calcRubric(); }
});
document.addEventListener('change', (e) => {
  const el = e.target, key = el.dataset.key;
  if (el.dataset.act === 'axis') { const m = S.manual[key] || (S.manual[key] = {}); (m.axes || (m.axes = {}))[el.dataset.axis] = +el.value; saveManual(); renderModal(); renderBasket(); }
  else if (el.dataset.act === 'inst') { const m = S.manual[key] || (S.manual[key] = {}); m.inst = el.checked; saveManual(); renderModal(); renderBasket(); }
  else if (el.dataset.act === 'raxis') { S.rubric.axes[el.dataset.axis] = +el.value; delete S.rubric.src[el.dataset.axis]; renderRubricAxes(); calcRubric(); }
  else if (el.id === 'rEvidence' || el.id === 'rInst') calcRubric();
  else if (el.dataset.act === 'import' && el.files?.[0]) importLib(el.files[0]);
});
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { if (!modal.hidden) closeModal(); else if (!$('#bulk').hidden) $('#bulk').hidden = true; } });
modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
$('#bulk').addEventListener('click', (e) => { if (e.target.id === 'bulk') $('#bulk').hidden = true; });
document.addEventListener('error', (e) => { const t = e.target; if (t?.tagName === 'IMG' && !t.dataset.ph) { t.dataset.ph = '1'; t.src = PH(t.alt || '?'); } }, true);

/* 테마 */
function applyTheme(t) {
  document.documentElement.classList.toggle('light', t === 'light');
  $('#themeBtn').textContent = t === 'light' ? '블랙' : '라이트';
  $('#themeBtn').setAttribute('aria-label', t === 'light' ? '검은 화면으로 전환' : '밝은 화면으로 전환');
  lsSet('ctl:theme', t);
}
$('#themeBtn').onclick = () => applyTheme(document.documentElement.classList.contains('light') ? 'dark' : 'light');

/* 시작 */
applyTheme(lsGet('ctl:theme', 'dark'));
renderAnti(); renderBasket(); renderRubricAxes(); calcRubric();
const params = new URLSearchParams(location.search);
if (['track', 'album', 'artist'].includes(params.get('t'))) { S.filter = params.get('t'); $$('#filters .pill').forEach((p) => p.classList.toggle('active', p.dataset.f === S.filter)); }
if (params.get('q')) { qInput.value = params.get('q'); doSearch(true); } else renderIntro();
for (const e of S.lib.entries) if (!e.an) { reg(e.item); analyze(e.item); }
