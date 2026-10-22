/* ============================================================
 * 智影 · UI 工具库：转义、格式化、星级、海报降级、Toast 等
 * ============================================================ */
(function () {
  'use strict';

  const UI = {};

  /* ---------- 基础工具 ---------- */
  UI.esc = function (s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };

  UI.debounce = function (fn, ms) {
    let t = null;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  };

  UI.throttle = function (fn, ms) {
    let last = 0, t = null;
    return function (...args) {
      const now = Date.now();
      if (now - last >= ms) { last = now; fn.apply(this, args); }
      else { clearTimeout(t); t = setTimeout(() => { last = Date.now(); fn.apply(this, args); }, ms - (now - last)); }
    };
  };

  /* ---------- 格式化 ---------- */
  UI.fmtRating = function (v) {
    if (v === null || v === undefined || isNaN(Number(v))) return '—';
    return Number(v).toFixed(1);
  };

  UI.fmtYear = function (dateStr) {
    if (!dateStr) return '';
    const m = String(dateStr).match(/^(\d{4})/);
    return m ? m[1] : '';
  };

  UI.fmtDate = function (dateStr) {
    if (!dateStr) return '';
    const m = String(dateStr).match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[1]}年${m[2]}月${m[3]}日` : dateStr;
  };

  UI.fmtTime = function (isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };

  UI.fmtNum = function (n) {
    if (n === null || n === undefined) return '0';
    n = Number(n);
    if (n >= 10000) return (n / 10000).toFixed(1) + '万';
    return String(n);
  };

  /* ---------- 电影名展示 ---------- */
  UI.movieName = function (movie) {
    return movie.name_zh || movie.moviename || '未知影片';
  };
  UI.movieSubName = function (movie) {
    const zh = movie.name_zh;
    const en = movie.moviename;
    if (zh && en && zh !== en) return en;
    return '';
  };

  /* ---------- 类型解析 ---------- */
  UI.parseGenres = function (typelist) {
    if (!typelist) return [];
    const aliases = window.GENRE_ALIASES || {};
    const seen = {};
    const out = [];
    String(typelist).split(',').forEach(function (raw) {
      let g = String(raw).trim();
      if (!g) return;
      if (aliases[g]) g = aliases[g];
      if (!seen[g]) { seen[g] = 1; out.push(g); }
    });
    return out;
  };

  UI.genreCn = function (g) {
    const found = (window.APP_CONFIG.GENRES || []).find(function (x) { return x.key === g; });
    if (found) return found.cn;
    const extra = (window.MOCK_GENRE_CN || {})[g];
    return extra || g;
  };

  /* ---------- 图片降级 ---------- */
  UI.imgCache = {};
  UI.fallbackSvg = function (text) {
    const label = String(text || '电影').slice(0, 14);
    const svg =
      `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600">` +
      `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
      `<stop offset="0" stop-color="#23242f"/><stop offset="1" stop-color="#14151c"/>` +
      `</linearGradient></defs>` +
      `<rect width="400" height="600" fill="url(#g)"/>` +
      `<g transform="translate(200,240)"><path d="M0-28 L31 4 L19 4 L19 30 H-19 V4 H-31 Z" fill="none" stroke="#3d3f4d" stroke-width="4" stroke-linejoin="round"/></g>` +
      `<g transform="translate(200,260)"><text y="0" font-size="20" text-anchor="middle">🎬</text></g>` +
      `<text x="200" y="330" font-size="26" text-anchor="middle" fill="#8b8fa3" font-family="Microsoft YaHei, sans-serif">${label}</text>` +
      `<text x="200" y="360" font-size="15" text-anchor="middle" fill="#55586b" font-family="Arial">ZHIYING MOVIE</text>` +
      `</svg>`;
    return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  };

  UI.posterOnError = function (img, title) {
    const key = img.dataset.fbKey || 'default';
    if (img.dataset.failed === '1') return;
    img.dataset.failed = '1';
    const fallback = UI.fallbackSvg(title || key);
    img.onerror = function () { img.onerror = null; img.src = fallback; };
    img.src = fallback;
  };

  /* 生成 <img> 字符串，自动绑定 onerror */
  UI.posterImg = function (src, title, extraClass) {
    const key = String(src || 'noimg').slice(0, 40);
    const cls = extraClass ? ' class="' + extraClass + '"' : '';
    const fb = UI.esc(UI.fallbackSvg(title));
    return `<img${cls} loading="lazy" decoding="async" alt="${UI.esc(title)}"` +
      ` src="${UI.esc(src || '')}"` +
      ` onerror="UI.posterOnError(this,'${UI.esc(String(title || '').replace(/'/g, ''))}')">`;
  };

  /* ---------- 星级渲染 ---------- */
  /* rating: 0-10 分制；返回 5 星 HTML（支持半星/四分之一填充） */
  UI.starsHtml = function (rating, opts) {
    opts = opts || {};
    const size = opts.size || 13;
    const r = rating === null || rating === undefined ? 0 : Math.max(0, Math.min(10, Number(rating)));
    const filled = r / 2; // 5 星制
    let html = `<span class="stars" style="--star-size:${size}px" title="${UI.fmtRating(r)} 分">`;
    for (let i = 1; i <= 5; i++) {
      let pct = 0;
      if (filled >= i) pct = 100;
      else if (filled > i - 1) pct = Math.round((filled - (i - 1)) * 100);
      if (pct > 0 && pct < 12) pct = 0;
      html += `<span class="star">` +
        `<svg viewBox="0 0 24 24" width="${size}" height="${size}"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.9l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"/></svg>` +
        (pct > 0 ? `<span class="star-fill" style="width:${pct}%"><svg viewBox="0 0 24 24" width="${size}" height="${size}"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.9l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"/></svg></span>` : '') +
        `</span>`;
    }
    html += '</span>';
    return html;
  };

  /* 5 星制（1-5）渲染 —— 用于影评 */
  UI.stars5Html = function (n) {
    return UI.starsHtml((Number(n) || 0) * 2);
  };

  /* ---------- Toast ---------- */
  UI.toast = function (msg, type) {
    const wrap = document.getElementById('toastWrap');
    if (!wrap) return;
    const el = document.createElement('div');
    el.className = 'toast' + (type ? ' toast-' + type : '');
    el.innerHTML = `<span class="toast-dot"></span><span>${UI.esc(msg)}</span>`;
    wrap.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 350);
    }, 3200);
  };

  /* ---------- 滚动控制 ---------- */
  UI.scrollTop = function (behavior) {
    window.scrollTo({ top: 0, behavior: behavior || 'auto' });
  };

  /* 横滑轨道：按一屏宽度滚动 */
  UI.slideRail = function (track, dir) {
    if (!track) return;
    const first = track.firstElementChild;
    if (!first) return;
    const gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap || 0) || 20;
    const step = first.offsetWidth + gap;
    const max = track.scrollWidth - track.clientWidth;
    const target = Math.min(Math.max(0, track.scrollLeft + dir * step), max);
    track.scrollTo({ left: target, behavior: 'smooth' });
  };

  /* 更新页码指示器 */
  UI.bindRailPager = function (track, pagerEl, prevBtn, nextBtn) {
    if (!track) return;
    const update = UI.throttle(function () {
      const first = track.firstElementChild;
      if (!first || !pagerEl) return;
      const gap = parseFloat(getComputedStyle(track).columnGap || getComputedStyle(track).gap || 0) || 20;
      const step = first.offsetWidth + gap;
      const pages = Math.max(1, Math.ceil((track.scrollWidth - track.clientWidth + 1) / step) + 1);
      const cur = Math.min(pages, Math.floor(track.scrollLeft / step) + 1);
      if (pagerEl) pagerEl.innerHTML = `<b>${cur}</b> / ${pages}`;
      if (prevBtn) prevBtn.disabled = track.scrollLeft <= 4;
      if (nextBtn) nextBtn.disabled = track.scrollLeft >= track.scrollWidth - track.clientWidth - 4;
    }, 80);
    track.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
    update();
    return update;
  };

  /* ---------- 骨架屏 ---------- */
  UI.skeletonCards = function (n) {
    let html = '<div class="skeleton-row">';
    for (let i = 0; i < (n || 6); i++) {
      html += `<div class="sk-card"><div class="sk-poster"></div><div class="sk-line w70"></div><div class="sk-line w40"></div></div>`;
    }
    return html + '</div>';
  };

  /* ---------- 兜底海报 URL ---------- */
  UI.backdropUrl = function (src) {
    if (!src) return '';
    if (typeof src !== 'string') return '';
    // 用更高分辨率替代 w185，作为巨幕背景
    return src.replace('/w185/', '/w780/');
  };

  /* 导出 */
  window.UI = UI;
})();
