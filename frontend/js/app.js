/* ============================================================
 * 智影 · 应用主逻辑
 * 路由 / 视图 / 巨幕轮播 / 评分 / 推荐 / 收藏 / 个人中心
 * ============================================================ */
(function () {
  'use strict';

  const UI = window.UI;
  const Api = window.Api;
  const Net = window.Net;
  const CFG = window.APP_CONFIG;

  const App = {
    state: {
      view: null,
      homeCat: null,        // 首页分类筛选 {key, id, cn}
      filterCat: null,      // 头部筛选器
      search: { q: '', page: 1, sort: 'rating', order: 'desc' },
      heroTimer: null,
      cleanup: []           // 视图清理函数
    },

    /* ================= 生命周期 ================= */
    async boot() {
      await Net.probe();
      this.updateEngineBadge();
      this.bindGlobalEvents();
      await this.restoreSession();
      this.renderTopbar();
      window.addEventListener('hashchange', () => this.route());
      this.route();
    },

    updateEngineBadge() {
      const el = document.getElementById('apiStatus');
      const modeEl = document.getElementById('footerMode');
      const apiEl = document.getElementById('footerApi');
      if (Net.mode === 'real') {
        el.textContent = '在线模式 · 已连接 API';
        if (modeEl) { modeEl.textContent = '在线模式'; modeEl.className = 'mode-chip online'; }
        if (apiEl) apiEl.textContent = CFG.API_BASE_URL;
        Api.health().then(r => { el.textContent = r && r.message ? r.message : '后端服务正常'; })
          .catch(() => { el.textContent = 'API 已连接（健康检查失败）'; });
      } else {
        el.textContent = '演示模式 · 内置 Mock 数据';
        if (modeEl) { modeEl.textContent = '演示模式（未连接后端）'; modeEl.className = 'mode-chip demo'; }
        if (apiEl) apiEl.textContent = '接口切换：见 js/config.js → DATA_MODE';
      }
    },

    async restoreSession() {
      if (!Net.isLoggedIn()) return;
      try {
        const res = await Api.me();
        Net.setCurrentUser(res.data);
        Net.setCurrentUserId(res.data.userid);
      } catch (e) {
        Net.setToken(null);
        Net.setCurrentUser(null);
        Net.setCurrentUserId(0);
      }
    },

    onSessionExpired() {
      UI.toast('登录已失效，请重新登录', 'warn');
      this.renderTopbar();
      this.openAuth('login');
      if (this.state.view && this.state.view.needsAuth) this.route();
    },

    /* ================= 全局事件 ================= */
    bindGlobalEvents() {
      // 顶栏滚动渐变
      const topbar = document.getElementById('topbar');
      const onScroll = UI.throttle(() => {
        topbar.classList.toggle('scrolled', window.scrollY > 24);
      }, 80);
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();

      // 搜索
      const input = document.getElementById('searchInput');
      const go = () => this.doSearch();
      document.getElementById('searchGoBtn').addEventListener('click', go);
      input.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });

      // 筛选弹层
      document.getElementById('searchFilterBtn').addEventListener('click', e => {
        e.stopPropagation();
        this.renderFilterPop();
        const pop = document.getElementById('filterPop');
        pop.hidden = !pop.hidden;
      });
      document.addEventListener('click', e => {
        const pop = document.getElementById('filterPop');
        if (!pop.hidden && !e.target.closest('#searchCapsule') && !e.target.closest('#filterPop')) pop.hidden = true;
      });
      document.getElementById('filterClearBtn').addEventListener('click', () => {
        this.state.filterCat = null;
        this.renderFilterPop();
        if (this.state.view && this.state.view.name === 'search') {
          this.state.search.page = 1;
          this.loadSearch();
        }
      });
      document.getElementById('filterApplyBtn').addEventListener('click', () => {
        document.getElementById('filterPop').hidden = true;
        if (this.state.view && this.state.view.name === 'search') {
          this.state.search.page = 1;
          this.loadSearch();
        } else {
          const cat = this.state.filterCat;
          location.hash = cat ? '#/search?cat=' + cat.id : '#/search';
        }
      });

      // 抽屉 / 弹窗关闭
      document.getElementById('drawerClose').addEventListener('click', () => this.closeDrawer());
      document.getElementById('drawerLayer').addEventListener('click', e => {
        if (e.target === e.currentTarget) this.closeDrawer();
      });
      document.getElementById('lightboxClose').addEventListener('click', () => {
        document.getElementById('lightbox').hidden = true;
      });
      document.getElementById('lightbox').addEventListener('click', e => {
        if (e.target === e.currentTarget) document.getElementById('lightbox').hidden = true;
      });
    },

    /* ================= 路由 ================= */
    route() {
      // 清理旧视图
      if (this.state.heroTimer) { clearInterval(this.state.heroTimer); this.state.heroTimer = null; }
      (this.state.cleanup || []).forEach(fn => { try { fn(); } catch (e) { /* noop */ } });
      this.state.cleanup = [];

      const hash = location.hash || '#/';
      const parts = hash.replace(/^#\/?/, '').split('?');
      const path = parts[0];
      const params = new URLSearchParams(parts[1] || '');
      const segs = path.split('/').filter(Boolean);
      const view = document.getElementById('view');
      this.setActiveNav(path);

      const render = (name, fn, needsAuth) => {
        this.state.view = { name, needsAuth };
        UI.scrollTop();
        fn().catch(err => {
          console.error(err);
          view.innerHTML = '<div class="state-box"><div class="state-ico">⚠️</div><div class="state-title">页面加载失败</div><div class="state-sub">' + UI.esc(err.detail || err.message || '未知错误') + '</div><button class="btn-primary" onclick="location.reload()">刷新重试</button></div>';
        });
      };

      if (segs.length === 0) render('home', () => this.loadHome());
      else if (segs[0] === 'search') {
        this.state.search.q = params.get('q') || '';
        if (params.get('cat')) {
          const id = Number(params.get('cat'));
          const g = CFG.GENRES[id - 1];
          this.state.filterCat = g ? { key: g.key, id, cn: g.cn } : null;
        }
        this.state.search.page = 1;
        render('search', () => this.loadSearch());
      }
      else if (segs[0] === 'movie') render('detail', () => this.loadDetail(segs[1]));
      else if (segs[0] === 'rate') render('rate', () => this.loadRate(), true);
      else if (segs[0] === 'recommend') render('recommend', () => this.loadRecommend(), true);
      else if (segs[0] === 'top') render('top', () => this.loadTop());
      else if (segs[0] === 'reviews') render('reviews', () => this.loadReviews());
      else if (segs[0] === 'myratings') render('myratings', () => this.loadMyRatings(), true);
      else if (segs[0] === 'myfavorites') render('myfavorites', () => this.loadMyFavorites(), true);
      else render('home', () => this.loadHome());

      // 关闭浮动层
      document.getElementById('filterPop').hidden = true;
    },

    setActiveNav(path) {
      const map = { '': 'home', search: null, movie: null, rate: 'rate', recommend: 'recommend', top: 'top', reviews: 'reviews', myratings: 'myratings', myfavorites: 'myfavorites' };
      const key = map[path.split('/')[0]];
      document.querySelectorAll('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.route === key));
    },

    requireAuth(openModal) {
      if (Net.isLoggedIn()) return true;
      if (openModal !== false) this.openAuth('login');
      return false;
    },

    doSearch() {
      const q = document.getElementById('searchInput').value.trim();
      if (!q) { UI.toast('请输入要搜索的关键词', 'warn'); return; }
      this.state.search.q = q;
      location.hash = '#/search?q=' + encodeURIComponent(q);
    },

    /* ================= 顶栏用户区 ================= */
    renderTopbar() {
      const el = document.getElementById('topbarUser');
      const user = Net.currentUser();
      if (!user || !Net.isLoggedIn()) {
        el.innerHTML = `
          <button class="pill ghost" id="hdrLogin">登录</button>
          <button class="pill solid" id="hdrRegister">注册</button>`;
        document.getElementById('hdrLogin').addEventListener('click', () => this.openAuth('login'));
        document.getElementById('hdrRegister').addEventListener('click', () => this.openAuth('register'));
        return;
      }
      const avatar = user.avatar ? `<img class="hdr-avatar-img" src="${UI.esc(user.avatar)}" onerror="UI.posterOnError(this,'${UI.esc(user.username)}')">`
        : `<span class="hdr-avatar-letter">${UI.esc((user.username || '?').slice(0, 1).toUpperCase())}</span>`;
      el.innerHTML = `
        <div class="hdr-user" id="hdrUser">
          <span class="hdr-avatar">${avatar}</span>
          <span class="hdr-welcome">欢迎您，<b>${UI.esc(user.username)}</b></span>
          <svg class="hdr-caret" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>
          <div class="hdr-drop" id="hdrDrop" hidden>
            <div class="drop-item" data-act="profile">👤 我的资料</div>
            <div class="drop-item" data-act="password">🔒 修改密码</div>
            <div class="drop-item" data-act="rate">⭐ 重新打分</div>
            <div class="drop-item" data-act="myratings">🎞️ 我的评分</div>
            <div class="drop-item" data-act="myfavorites">❤️ 我的收藏</div>
            <div class="drop-sep"></div>
            <div class="drop-item danger" data-act="logout">⏻ 退出登录</div>
          </div>
        </div>`;
      document.getElementById('hdrUser').addEventListener('click', e => {
        e.stopPropagation();
        const drop = document.getElementById('hdrDrop');
        drop.hidden = !drop.hidden;
      });
      document.addEventListener('click', e => {
        const drop = document.getElementById('hdrDrop');
        if (drop && !drop.hidden && !e.target.closest('#hdrUser')) drop.hidden = true;
      });
      document.getElementById('hdrDrop').addEventListener('click', e => {
        const item = e.target.closest('.drop-item');
        if (!item) return;
        const act = item.dataset.act;
        document.getElementById('hdrDrop').hidden = true;
        if (act === 'logout') this.logout();
        else if (act === 'profile') this.openProfile();
        else if (act === 'password') this.openPassword();
        else if (act === 'rate') location.hash = '#/rate';
        else if (act === 'myratings') location.hash = '#/myratings';
        else if (act === 'myfavorites') location.hash = '#/myfavorites';
      });
    },

    logout() {
      Net.setToken(null);
      Net.setCurrentUser(null);
      Net.setCurrentUserId(0);
      UI.toast('已安全退出登录');
      this.renderTopbar();
      const v = this.state.view;
      if (v && v.needsAuth) location.hash = '#/';
      else this.route();
    },

    /* ================= 筛选弹层 ================= */
    renderFilterPop() {
      const grid = document.getElementById('filterPopGrid');
      let html = `<button type="button" class="filter-chip ${!this.state.filterCat ? 'active' : ''}" data-id="0">全部</button>`;
      CFG.GENRES.forEach((g, i) => {
        const active = this.state.filterCat && this.state.filterCat.id === i + 1;
        html += `<button type="button" class="filter-chip ${active ? 'active' : ''}" data-id="${i + 1}">${UI.esc(g.cn)}</button>`;
      });
      grid.innerHTML = html;
      grid.querySelectorAll('.filter-chip').forEach(b => b.addEventListener('click', () => {
        const id = Number(b.dataset.id);
        this.state.filterCat = id > 0 ? { key: CFG.GENRES[id - 1].key, id, cn: CFG.GENRES[id - 1].cn } : null;
        this.renderFilterPop();
      }));
    },

    /* ================= 首页 ================= */
    async loadHome() {
      const view = document.getElementById('view');
      view.innerHTML = `
        <section class="home">
          <div id="heroMount"></div>
          <div class="home-body">
            <div class="home-main">
              <div id="pillsMount" class="cat-pills-wrap"></div>
              <div id="railMainMount"></div>
              <div id="railNewMount"></div>
              <div id="railGuessMount"></div>
            </div>
            <aside class="home-side">
              <div id="topMount"></div>
              <div id="reviewMount"></div>
            </aside>
          </div>
        </section>`;

      await this.loadHero();
      this.renderCatPills();
      await this.loadRailMain();
      this.loadRailNew();
      this.loadRailGuess();
      this.loadTop10();
      this.loadHomeReviews();
    },

    /* ---- 模块 A：巨幕轮播 ---- */
    async loadHero() {
      const mount = document.getElementById('heroMount');
      let items = [];
      if (Net.mode === 'mock') {
        const ids = [148478, 4993, 318, 98809, 109487]; // 大圣归来/魔戒/肖申克/霍比特人/星际穿越
        items = ids.map(id => window.MOCK_MOVIES.find(m => m.movieid === id)).filter(Boolean);
      } else {
        try {
          const res = await Api.movies({ sort_by: 'rating', order: 'desc', page: 1, page_size: 10 });
          items = (res.data.items || []).slice(0, 5).filter(m => m.picture);
          if (items.length < 3) {
            const r = await Api.randomMovies();
            const extra = (r.data || []).filter(m => m.picture);
            const have = new Set(items.map(m => m.movieid));
            extra.forEach(m => { if (!have.has(m.movieid)) items.push(m); });
            items = items.slice(0, 5);
          }
        } catch (e) { /* 保留空，显示兜底 */ }
      }
      if (!items.length) {
        mount.innerHTML = '<div class="hero hero-empty"><div class="hero-empty-text">暂无影片数据，请检查后端服务</div></div>';
        return;
      }

      let idx = 0;
      const renderSlide = () => {
        const m = items[idx];
        const bg = UI.backdropUrl(m.picture);
        const year = UI.fmtYear(m.releasetime);
        const genres = UI.parseGenres(m.typelist).slice(0, 3);
        const zh = m.name_zh || '';
        const en = m.moviename || '';
        const rating = UI.fmtRating(m.averating);
        const tagline = m.tagline || (m.description ? String(m.description).slice(0, 80) + '…' : '');
        return `
          <div class="hero-slide ${idx === 0 ? 'active' : ''}" data-i="${idx}">
            <div class="hero-bg-wrap">
              <img class="hero-bg" src="${UI.esc(bg || '')}" alt="" onerror="UI.posterOnError(this,'${UI.esc(zh || en)}')">
              <div class="hero-vignette"></div>
            </div>
            <div class="hero-inner">
              <div class="hero-info">
                <div class="hero-badges">
                  <span class="hero-badge gold"><svg viewBox="0 0 24 24" width="13" height="13"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.9l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z" fill="currentColor"/></svg>${rating} 分</span>
                  ${genres.map(g => `<span class="hero-badge">${UI.esc(UI.genreCn(g))}</span>`).join('')}
                </div>
                <h1 class="hero-title"><span class="hero-title-zh">${UI.esc(zh)}</span><span class="hero-title-en">${UI.esc(en)}${year ? ' · ' + year : ''}</span></h1>
                <p class="hero-tagline">${UI.esc(tagline)}</p>
                <div class="hero-actions">
                  <button class="hero-btn primary" data-act="detail" data-id="${m.movieid}">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M7 4.5v15l13-7.5Z"/></svg>立即查看详情
                  </button>
                  <button class="hero-btn ghost" data-act="rate">
                    <svg viewBox="0 0 24 24" width="16" height="16"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.9l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z" fill="currentColor"/></svg>参与打分定制推荐
                  </button>
                </div>
              </div>
              <div class="hero-poster">
                ${UI.posterImg(m.picture, zh || en, '')}
              </div>
            </div>
          </div>`;
      };

      mount.innerHTML = `
        <div class="hero" id="hero">
          <div class="hero-slides" id="heroSlides">${items.map((m, i) => { idx = i; return renderSlide(); }).join('')}</div>
          <div class="hero-controls">
            <button class="hero-arrow" id="heroPrev" type="button" aria-label="上一部">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 5-7 7 7 7"/></svg>
            </button>
            <div class="hero-thumbs" id="heroThumbs">
              ${items.map((m, i) => `
                <button type="button" class="hero-thumb ${i === 0 ? 'active' : ''}" data-i="${i}">
                  ${UI.posterImg(m.picture, m.name_zh || m.moviename, '')}
                  <span class="hero-thumb-name">${UI.esc(m.name_zh || m.moviename)}</span>
                  <span class="hero-thumb-bar"></span>
                </button>`).join('')}
            </div>
            <button class="hero-arrow" id="heroNext" type="button" aria-label="下一部">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 5 7 7-7 7"/></svg>
            </button>
          </div>
        </div>`;

      const hero = document.getElementById('hero');
      const slides = hero.querySelectorAll('.hero-slide');
      const thumbs = hero.querySelectorAll('.hero-thumb');

      const goTo = (i, user) => {
        idx = (i + items.length) % items.length;
        slides.forEach((s, j) => s.classList.toggle('active', j === idx));
        thumbs.forEach((t, j) => t.classList.toggle('active', j === idx));
        if (user) restartAuto();
      };
      const restartAuto = () => {
        if (this.state.heroTimer) clearInterval(this.state.heroTimer);
        this.state.heroTimer = setInterval(() => goTo(idx + 1, false), CFG.HERO_INTERVAL);
      };

      hero.querySelector('#heroPrev').addEventListener('click', () => goTo(idx - 1, true));
      hero.querySelector('#heroNext').addEventListener('click', () => goTo(idx + 1, true));
      thumbs.forEach(t => {
        t.addEventListener('click', () => goTo(Number(t.dataset.i), true));
        t.addEventListener('mouseenter', () => goTo(Number(t.dataset.i), true));
      });
      hero.addEventListener('click', e => {
        const b = e.target.closest('[data-act]');
        if (!b) return;
        if (b.dataset.act === 'detail') location.hash = '#/movie/' + b.dataset.id;
        else if (b.dataset.act === 'rate') this.requireAuth() && (location.hash = '#/rate');
      });
      restartAuto();
      this.state.cleanup.push(() => { if (this.state.heroTimer) clearInterval(this.state.heroTimer); });
    },

    /* ---- 模块 B：分类胶囊 ---- */
    renderCatPills() {
      const mount = document.getElementById('pillsMount');
      let html = `<button type="button" class="cat-pill ${!this.state.homeCat ? 'active' : ''}" data-id="0"><span>全部</span><em>All</em></button>`;
      CFG.GENRES.forEach((g, i) => {
        const active = this.state.homeCat && this.state.homeCat.id === i + 1;
        html += `<button type="button" class="cat-pill ${active ? 'active' : ''}" data-id="${i + 1}"><span>${UI.esc(g.cn)}</span><em>${UI.esc(g.en)}</em></button>`;
      });
      mount.innerHTML = html;
      mount.querySelectorAll('.cat-pill').forEach(b => b.addEventListener('click', () => {
        const id = Number(b.dataset.id);
        this.state.homeCat = id > 0 ? { key: CFG.GENRES[id - 1].key, id, cn: CFG.GENRES[id - 1].cn } : null;
        this.renderCatPills();
        this.loadRailMain();
      }));
    },

    /* ---- 电影卡片 ---- */
    movieCard(m, opts) {
      opts = opts || {};
      const zh = m.name_zh || m.moviename || '';
      const en = (m.name_zh && m.moviename && m.moviename !== m.name_zh) ? m.moviename : '';
      const year = UI.fmtYear(m.releasetime);
      const rating = Number(m.averating);
      const isNew = year && Number(year) >= new Date().getFullYear() - 1;
      const isHot = (m.numrating || 0) >= 20000;
      const isTop = !isNaN(rating) && rating >= 8.6;
      const badge = isTop ? '<span class="poster-badge gold">高分</span>'
        : isNew ? '<span class="poster-badge green">新片</span>'
        : isHot ? '<span class="poster-badge hot">热播</span>' : '';
      const rank = opts.rank ? `<span class="rank-badge r${Math.min(3, opts.rank)}">${opts.rank}</span>` : '';
      return `
        <article class="movie-card" data-id="${m.movieid}">
          <div class="poster">
            ${UI.posterImg(m.picture, zh, '')}
            ${badge}${rank}
            ${!isNaN(rating) ? `<span class="poster-score">${UI.fmtRating(rating)}</span>` : ''}
            <div class="poster-shade"></div>
            <div class="poster-actions">
              <button type="button" class="pa-btn primary" data-act="detail">查看详情</button>
              <button type="button" class="pa-btn" data-act="quickrate">快速评分</button>
            </div>
          </div>
          <div class="mc-info">
            <h3 class="mc-name" title="${UI.esc(zh)}${en ? ' ' + UI.esc(en) : ''}">${UI.esc(zh)}</h3>
            <div class="mc-sub">${UI.esc(en || year || '')}</div>
            <div class="mc-rating">${UI.starsHtml(rating)}<span class="mc-score">${UI.fmtRating(rating)}</span></div>
          </div>
        </article>`;
    },

    bindCardActions(scope) {
      scope.querySelectorAll('.movie-card').forEach(card => {
        const id = card.dataset.id;
        const detailBtn = card.querySelector('[data-act="detail"]');
        const rateBtn = card.querySelector('[data-act="quickrate"]');
        card.addEventListener('click', e => {
          if (e.target.closest('[data-act]')) return;
          location.hash = '#/movie/' + id;
        });
        if (detailBtn) detailBtn.addEventListener('click', () => { location.hash = '#/movie/' + id; });
        if (rateBtn) rateBtn.addEventListener('click', e => {
          e.stopPropagation();
          this.openQuickRate(id, rateBtn);
        });
      });
    },

    railHtml(title, sub, trackId) {
      return `
        <section class="rail">
          <div class="rail-head">
            <h2 class="rail-title">${UI.esc(title)}</h2>
            <div class="rail-tools">
              <span class="rail-pager" id="${trackId}-pager"><b>1</b> / 1</span>
              <button type="button" class="rail-arrow" data-dir="-1" aria-label="上一屏">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 5-7 7 7 7"/></svg>
              </button>
              <button type="button" class="rail-arrow" data-dir="1" aria-label="下一屏">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 5 7 7-7 7"/></svg>
              </button>
            </div>
          </div>
          <div class="rail-track" id="${trackId}"></div>
        </section>`;
    },

    fillRail(trackId, movies, title) {
      const track = document.getElementById(trackId);
      if (!track) return;
      if (!movies || !movies.length) {
        track.innerHTML = '<div class="rail-empty">暂无影片数据</div>';
        return;
      }
      track.innerHTML = movies.map((m, i) => this.movieCard(m, {})).join('');
      this.bindCardActions(track);
      const pager = document.getElementById(trackId + '-pager');
      const arrows = track.closest('.rail').querySelectorAll('.rail-arrow');
      UI.bindRailPager(track, pager, arrows[0], arrows[1]);
      arrows.forEach(a => a.addEventListener('click', () => UI.slideRail(track, Number(a.dataset.dir))));
    },

    /* ---- 模块 C：电影推荐滑轨 ---- */
    async loadRailMain() {
      const mount = document.getElementById('railMainMount');
      const cat = this.state.homeCat;
      mount.innerHTML = this.railHtml(cat ? cat.cn + ' · 精选影片' : '电影推荐', '', 'railMain');
      const track = document.getElementById('railMain');
      track.innerHTML = UI.skeletonCards(CFG.RAIL_PER_PAGE);
      try {
        const res = await Api.movies({ category_id: cat ? cat.id : null, sort_by: 'rating', order: 'desc', page: 1, page_size: 30 });
        const movies = res.data.items || [];
        if (movies.length < 8 && !cat && Net.mode === 'mock') {
          this.fillRail('railMain', window.MOCK_MOVIES.slice(0, 24), '');
          return;
        }
        this.fillRail('railMain', movies, '');
      } catch (e) {
        document.getElementById('railMain').innerHTML = `<div class="rail-empty">${UI.esc(e.detail || '加载失败')}</div>`;
      }
    },

    async loadRailNew() {
      const mount = document.getElementById('railNewMount');
      mount.innerHTML = this.railHtml('新片热映', '', 'railNew');
      const track = document.getElementById('railNew');
      track.innerHTML = UI.skeletonCards(CFG.RAIL_PER_PAGE);
      try {
        const res = await Api.movies({ sort_by: 'release_time', order: 'desc', page: 1, page_size: 24 });
        this.fillRail('railNew', res.data.items || [], '');
      } catch (e) {
        document.getElementById('railNew').innerHTML = `<div class="rail-empty">${UI.esc(e.detail || '加载失败')}</div>`;
      }
    },

    async loadRailGuess() {
      const mount = document.getElementById('railGuessMount');
      mount.innerHTML = this.railHtml('为你精选 · 冷启动候选', '', 'railGuess');
      const track = document.getElementById('railGuess');
      track.innerHTML = UI.skeletonCards(CFG.RAIL_PER_PAGE);
      try {
        const res = await Api.randomMovies();
        const items = (res.data || []).slice(0, 12);
        this.fillRail('railGuess', items, '');
      } catch (e) {
        document.getElementById('railGuess').innerHTML = `<div class="rail-empty">${UI.esc(e.detail || '加载失败')}</div>`;
      }
    },

    /* ---- 一周口碑榜 ---- */
    async loadTop10() {
      const mount = document.getElementById('topMount');
      mount.innerHTML = `
        <div class="side-card top-card">
          <div class="side-card-head">
            <h3 class="side-card-title">🏆 一周口碑榜</h3>
            <a href="#/top" class="side-card-more">更多榜单 »</a>
          </div>
          <ol class="top-list" id="topList">${'<li class="sk-li"></li>'.repeat(6)}</ol>
        </div>`;
      const list = document.getElementById('topList');
      try {
        const res = await Api.movies({ sort_by: 'rating', order: 'desc', page: 1, page_size: 10 });
        const items = (res.data.items || []).slice(0, 10);
        list.innerHTML = items.map((m, i) => {
          const zh = m.name_zh || m.moviename;
          const genres = UI.parseGenres(m.typelist).slice(0, 2).map(g => UI.genreCn(g)).join(' / ');
          return `
            <li class="top-item" data-id="${m.movieid}">
              <span class="top-rank ${i < 3 ? 'top3' : ''}">${i + 1}</span>
              <div class="top-info">
                <div class="top-name">${UI.esc(zh)}</div>
                <div class="top-genre">${UI.esc(genres || UI.fmtYear(m.releasetime))}</div>
              </div>
              <span class="top-score">${UI.fmtRating(m.averating)}<i>分</i></span>
              <span class="top-hover-poster">${UI.posterImg(m.picture, zh, '')}</span>
            </li>`;
        }).join('');
        list.querySelectorAll('.top-item').forEach(li => li.addEventListener('click', () => {
          location.hash = '#/movie/' + li.dataset.id;
        }));
      } catch (e) {
        list.innerHTML = `<li class="top-empty">${UI.esc(e.detail || '加载失败')}</li>`;
      }
    },

    /* ---- 模块 D：热门影评精选 ---- */
    reviewCard(r, full) {
      const m = r.movie || {};
      const zh = m.name_zh || m.moviename || '';
      return `
        <article class="review-card ${full ? 'full' : ''}" data-movie="${m.movieid || ''}">
          <div class="review-poster">${m.picture ? UI.posterImg(m.picture, zh, '') : ''}</div>
          <div class="review-body">
            <h4 class="review-title">${UI.esc(r.title)}${r.spoiler ? '<span class="review-spoiler">剧透提醒</span>' : ''}</h4>
            <div class="review-meta">
              <span class="review-user">${UI.esc(r.username)}</span>
              <span>评论《${UI.esc(zh)}》</span>
              <span class="review-stars">${UI.stars5Html(r.rating)}</span>
              <span class="review-likes">👍 ${UI.fmtNum(r.likes)}</span>
            </div>
            <p class="review-content ${full ? '' : 'clamp'}">${UI.esc(r.content)}</p>
            <div class="review-actions">
              ${full ? '' : `<button type="button" class="review-link" data-act="full">（全文）</button>`}
              ${full ? `<button type="button" class="review-link" data-act="movie">查看《${UI.esc(zh)}》详情 »</button>` : ''}
            </div>
          </div>
        </article>`;
    },

    bindReviewActions(scope) {
      scope.querySelectorAll('.review-card').forEach(c => {
        c.querySelectorAll('[data-act]').forEach(b => b.addEventListener('click', e => {
          e.stopPropagation();
          const act = b.dataset.act;
          if (act === 'movie' && c.dataset.movie) location.hash = '#/movie/' + c.dataset.movie;
          if (act === 'full' && c.dataset.movie) location.hash = '#/reviews';
        }));
      });
    },

    async loadHomeReviews() {
      const mount = document.getElementById('reviewMount');
      mount.innerHTML = `
        <div class="side-card review-side-card">
          <div class="side-card-head">
            <h3 class="side-card-title">💬 热门影评精选</h3>
            <a href="#/reviews" class="side-card-more">更多 »</a>
          </div>
          <div id="homeReviews">${'<div class="sk-line w80"></div><div class="sk-line w60"></div><div class="sk-line w90"></div>'.repeat(2)}</div>
        </div>`;
      const box = document.getElementById('homeReviews');
      try {
        const reviews = await Api.reviews();
        box.innerHTML = reviews.slice(0, 3).map(r => this.reviewCard(r, false)).join('');
        this.bindReviewActions(box);
      } catch (e) {
        box.innerHTML = `<div class="rail-empty">${UI.esc(e.detail || '加载失败')}</div>`;
      }
    },

    /* ================= 搜索页 ================= */
    async loadSearch() {
      const view = document.getElementById('view');
      const q = this.state.search.q || '';
      const cat = this.state.filterCat;
      view.innerHTML = `
        <section class="page">
          <div class="page-head">
            <h1 class="page-title">搜索<span class="page-title-sub">${q ? '“' + UI.esc(q) + '”' : '全部影片'}${cat ? ' · ' + UI.esc(cat.cn) : ''}</span></h1>
            <div class="sort-tabs" id="sortTabs">
              <button type="button" class="sort-tab ${this.state.search.sort === 'rating' ? 'active' : ''}" data-sort="rating">评分最高</button>
              <button type="button" class="sort-tab ${this.state.search.sort === 'popularity' ? 'active' : ''}" data-sort="popularity">热度最高</button>
              <button type="button" class="sort-tab ${this.state.search.sort === 'release_time' ? 'active' : ''}" data-sort="release_time">最新上映</button>
            </div>
          </div>
          <div id="searchGrid" class="movie-grid">${UI.skeletonCards(12)}</div>
          <div id="searchPager" class="pager"></div>
        </section>`;

      document.getElementById('sortTabs').querySelectorAll('.sort-tab').forEach(t => t.addEventListener('click', () => {
        this.state.search.sort = t.dataset.sort;
        this.state.search.page = 1;
        this.loadSearch();
      }));

      const grid = document.getElementById('searchGrid');
      try {
        const res = await Api.movies({
          q: q || null, category_id: cat ? cat.id : null,
          sort_by: this.state.search.sort, order: 'desc',
          page: this.state.search.page, page_size: 24
        });
        const items = res.data.items || [];
        const total = res.data.total || 0;
        grid.innerHTML = items.length ? items.map(m => this.movieCard(m, {})).join('')
          : `<div class="state-box"><div class="state-ico">🔍</div><div class="state-title">没有找到相关影片</div><div class="state-sub">试试更换关键词或分类筛选</div></div>`;
        this.bindCardActions(grid);
        this.renderPager('searchPager', total, 24, this.state.search.page, page => {
          this.state.search.page = page;
          this.loadSearch();
        });
      } catch (e) {
        grid.innerHTML = `<div class="state-box"><div class="state-ico">⚠️</div><div class="state-title">搜索失败</div><div class="state-sub">${UI.esc(e.detail || '')}</div></div>`;
      }
    },

    renderPager(id, total, pageSize, current, onPage) {
      const el = document.getElementById(id);
      if (!el) return;
      const pages = Math.max(1, Math.ceil(total / pageSize));
      if (pages <= 1) { el.innerHTML = ''; return; }
      let html = `<button type="button" class="pager-btn" data-p="${current - 1}" ${current <= 1 ? 'disabled' : ''}>‹ 上一页</button>`;
      const start = Math.max(1, Math.min(current - 2, pages - 4));
      for (let p = start; p <= Math.min(pages, start + 4); p++) {
        html += `<button type="button" class="pager-num ${p === current ? 'active' : ''}" data-p="${p}">${p}</button>`;
      }
      html += `<button type="button" class="pager-btn" data-p="${current + 1}" ${current >= pages ? 'disabled' : ''}>下一页 ›</button>`;
      el.innerHTML = `<span class="pager-total">共 ${total} 部</span>` + html;
      el.querySelectorAll('[data-p]').forEach(b => b.addEventListener('click', () => {
        const p = Number(b.dataset.p);
        if (p >= 1 && p <= pages && p !== current) onPage(p);
      }));
    },

    /* ================= 电影详情页 ================= */
    async loadDetail(movieid) {
      const view = document.getElementById('view');
      view.innerHTML = '<div class="page"><div class="detail-skeleton">' + UI.skeletonCards(4) + '</div></div>';
      let movie;
      try {
        const res = await Api.movieDetail(movieid);
        movie = res.data;
      } catch (e) {
        view.innerHTML = `
          <div class="state-box">
            <div class="state-ico">🎬</div>
            <div class="state-title">电影不存在或已删除</div>
            <div class="state-sub">${UI.esc(e.detail || '')}</div>
            <button class="btn-primary" onclick="location.hash='#/'">返回首页</button>
          </div>`;
        return;
      }
      if (!movie) return;

      const zh = movie.name_zh || movie.moviename || '';
      const en = (movie.name_zh && movie.moviename && movie.moviename !== movie.name_zh) ? movie.moviename : '';
      const year = UI.fmtYear(movie.releasetime);
      const genres = UI.parseGenres(movie.typelist);
      const rating = Number(movie.averating);
      const myRatings = await this.getMyRatingsMap();
      const myScore = myRatings[Number(movie.movieid)] || 0;
      const dist = window.MockSvc.ratingDistribution(movie);
      const better = Math.min(97, Math.round(45 + (isNaN(rating) ? 7 : rating) * 5));

      view.innerHTML = `
        <section class="page detail-page">
          <div class="detail-top">
            <div class="honor-badges">
              <span class="honor-badge gold">✦ 入选高分电影榜单</span>
              <span class="honor-badge">Spark ALS 协同过滤候选影片</span>
            </div>
            <div class="detail-title-row">
              <h1 class="detail-title">${UI.esc(zh)}${en ? ' <span class="detail-title-en">' + UI.esc(en) + '</span>' : ''}${year ? ' <span class="detail-year">(' + year + ')</span>' : ''}</h1>
              <div class="detail-title-actions">
                <button type="button" class="share-btn" id="shareBtn" title="复制链接">↗ 分享</button>
              </div>
            </div>
          </div>

          <div class="detail-core">
            <div class="detail-poster-col">
              <div class="detail-poster">
                ${UI.posterImg(movie.picture, zh, '')}
                <button type="button" class="poster-zoom" id="posterZoom" title="查看大图">🔍 放大预览</button>
              </div>
            </div>

            <div class="detail-meta-col">
              <dl class="meta-list">
                <div class="meta-row"><dt>导演</dt><dd>${UI.esc(movie.director || '未知')}</dd></div>
                <div class="meta-row"><dt>主演</dt><dd>${UI.esc(movie.leadactors || '未知')}</dd></div>
                <div class="meta-row"><dt>类型</dt><dd>${genres.length ? genres.map(g => {
                  const gi = CFG.GENRES.findIndex(x => x.key === g);
                  return gi >= 0
                    ? `<a class="genre-link" href="#/search?cat=${gi + 1}">${UI.esc(UI.genreCn(g))}</a>`
                    : `<a class="genre-link" href="#/search?q=${encodeURIComponent(g)}">${UI.esc(UI.genreCn(g))}</a>`;
                }).join(' ') : '未知'}</dd></div>
                <div class="meta-row"><dt>上映日期</dt><dd>${UI.esc(UI.fmtDate(movie.releasetime) || '未知')}</dd></div>
                <div class="meta-row"><dt>电影编号</dt><dd>ID: ${UI.esc(movie.movieid)}</dd></div>
              </dl>
            </div>

            <div class="detail-rating-col">
              <div class="rating-board">
                <div class="rb-head">系统综合评分</div>
                <div class="rb-main">
                  <div class="rb-score">${UI.fmtRating(rating)}</div>
                  <div class="rb-right">
                    <div class="rb-stars">${UI.starsHtml(rating, { size: 22 })}</div>
                    <div class="rb-count">${UI.fmtNum(movie.numrating)} 人评价</div>
                  </div>
                </div>
                <div class="rb-dist">
                  ${dist.map(d => `
                    <div class="dist-row">
                      <span class="dist-label">${d.star}星</span>
                      <span class="dist-bar"><i style="width:${d.pct}%"></i></span>
                      <span class="dist-pct">${d.pct.toFixed(1)}%</span>
                    </div>`).join('')}
                </div>
                <div class="rb-compare">好于 <b>${better}%</b> 同类型片</div>
              </div>
            </div>
          </div>

          <div class="rate-bar" id="rateBar">
            <div class="rate-bar-left">
              <span class="rate-bar-label">我的评分与推荐定制</span>
              <div class="fav-pills" id="favPills">
                <button type="button" class="fav-pill" data-status="want_to_watch">＋ 想看</button>
                <button type="button" class="fav-pill" data-status="watched">✓ 看过</button>
              </div>
            </div>
            <div class="rate-bar-mid">
              <span class="rate-bar-tip">评价：</span>
              <div id="detailStars" class="stars-input-lg"></div>
              <span class="rate-word" id="rateWord"></span>
            </div>
            <div class="rate-bar-right">
              <button type="button" class="btn-primary" id="submitScoreBtn">提交评分</button>
            </div>
          </div>
          <div id="rateResult" class="rate-result" hidden></div>

          <div class="quick-strip-wrap">
            <div class="rail-head">
              <h2 class="rail-title">猜你可能看过 · 顺手再评几部让推荐更精准</h2>
              <button type="button" class="btn-ghost sm" id="batchSubmitBtn" disabled>批量提交评分 (0)</button>
            </div>
            <div class="rail-track quick-track" id="quickTrack"></div>
          </div>

          <section class="detail-section">
            <h2 class="section-title">《${UI.esc(zh)}》的剧情简介 · · · · · ·</h2>
            <div class="plot-text">${UI.esc(movie.description || '暂无简介')}</div>
          </section>

          <section class="detail-section">
            <div class="rail-head">
              <h2 class="section-title">喜欢这部电影的人也喜欢</h2>
              <div class="rail-tools">
                <span class="rail-pager" id="simRail-pager"><b>1</b> / 1</span>
                <button type="button" class="rail-arrow" data-dir="-1"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 5-7 7 7 7"/></svg></button>
                <button type="button" class="rail-arrow" data-dir="1"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 5 7 7-7 7"/></svg></button>
              </div>
            </div>
            <div class="rail-track" id="simRail"></div>
          </section>

          <section class="detail-section">
            <h2 class="section-title">热门影评</h2>
            <div class="comment-box">
              <input type="text" id="commentInput" placeholder="写短评…（演示功能，仅保存在本地）" maxlength="500">
              <button type="button" class="btn-primary sm" id="commentSend">写短评</button>
            </div>
            <div id="detailReviews"></div>
          </section>
        </section>`;

      /* 海报放大 */
      document.getElementById('posterZoom').addEventListener('click', () => this.openLightbox(movie.picture));
      document.querySelector('.detail-poster img').addEventListener('click', () => this.openLightbox(movie.picture));
      document.getElementById('shareBtn').addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(location.href);
          UI.toast('链接已复制，快去分享给朋友吧');
        } catch (e) {
          UI.toast('复制失败，请手动复制地址栏链接', 'warn');
        }
      });

      /* 收藏状态 */
      this.favCache = null;
      const renderFavState = () => {
        let status = null;
        if (Net.mode === 'mock') status = window.MockSvc.myFavoriteStatus(Number(movie.movieid));
        else if (this.favCache) {
          const f = this.favCache.find(x => Number(x.movieid) === Number(movie.movieid));
          status = f ? f.status : null;
        }
        document.querySelectorAll('#favPills .fav-pill').forEach(p => {
          p.classList.toggle('active', status === p.dataset.status);
        });
        return status;
      };
      renderFavState();
      if (Net.isLoggedIn() && Net.mode === 'real') {
        try {
          const res = await Api.myFavorites({ page: 1, page_size: 100 });
          this.favCache = res.data.items || [];
          renderFavState();
        } catch (e) { /* 忽略 */ }
      }
      document.querySelectorAll('#favPills .fav-pill').forEach(p => p.addEventListener('click', async () => {
        if (!this.requireAuth()) return;
        p.disabled = true;
        try {
          const res = await Api.toggleFavorite(Number(movie.movieid), p.dataset.status);
          UI.toast(res.action === 'remove' ? '已取消收藏' : (res.action === 'update' ? '收藏状态已更新' : '收藏成功：' + (p.dataset.status === 'watched' ? '已看' : '想看')), 'ok');
          if (Net.mode === 'mock') { this.favCache = null; renderFavState(); }
          else {
            try { const f = await Api.myFavorites({ page: 1, page_size: 100 }); this.favCache = f.data.items || []; } catch (e) { /* noop */ }
            renderFavState();
          }
        } catch (e) {
          UI.toast(e.detail || '操作失败', 'warn');
          try { const f = await Api.myFavorites({ page: 1, page_size: 100 }); this.favCache = f.data.items || []; renderFavState(); } catch (e2) { /* noop */ }
        }
        p.disabled = false;
      }));

      /* 详情页内嵌星级打分 */
      let myScoreSel = myScore;
      const starWidget = this.buildStarsInput(myScore, value => {
        myScoreSel = value;
        document.getElementById('rateWord').textContent = value ? value + '分 · ' + this.scoreWord(value) : '';
      }, true);
      document.getElementById('detailStars').appendChild(starWidget);
      document.getElementById('rateWord').textContent = myScoreSel ? myScoreSel + '分 · ' + this.scoreWord(myScoreSel) : '';

      document.getElementById('submitScoreBtn').addEventListener('click', async () => {
        if (!this.requireAuth()) return;
        if (!myScoreSel) { UI.toast('请先点亮星星选择评分', 'warn'); return; }
        const btn = document.getElementById('submitScoreBtn');
        btn.disabled = true;
        try {
          await Api.submitRatings([Number(movie.movieid)], [myScoreSel]);
          const user = Net.currentUser();
          const box = document.getElementById('rateResult');
          box.hidden = false;
          box.innerHTML = `
            <div class="rate-success">
              <div class="rate-success-emoji">🎉</div>
              <div>
                <div class="rate-success-title">亲爱的用户：${UI.esc(user ? user.username : '')}，祝贺评分成功！</div>
                <div class="rate-success-sub">您的偏好已记入数据库（personalratings）</div>
              </div>
              <button type="button" class="btn-gold" id="goRecommendBtn">✨ 点击这里为您推荐电影</button>
            </div>`;
          document.getElementById('goRecommendBtn').addEventListener('click', () => {
            location.hash = '#/recommend';
          });
          UI.toast('评分提交成功 🎉', 'ok');
        } catch (e) {
          UI.toast(e.detail || '评分提交失败', 'warn');
        }
        btn.disabled = false;
      });

      /* 快速连评 */
      await this.loadQuickStrip(Number(movie.movieid));

      /* 相似影片 */
      await this.loadSimilarRail(Number(movie.movieid));

      /* 影评 */
      const reviewsBox = document.getElementById('detailReviews');
      try {
        const reviews = await Api.reviews(Number(movie.movieid));
        reviewsBox.innerHTML = reviews.length
          ? reviews.map(r => this.reviewCard(r, true)).join('')
          : '<div class="rail-empty">暂无影评</div>';
        this.bindReviewActions(reviewsBox);
      } catch (e) {
        reviewsBox.innerHTML = `<div class="rail-empty">${UI.esc(e.detail || '加载失败')}</div>`;
      }

      /* 写短评（演示，本地保存） */
      document.getElementById('commentSend').addEventListener('click', () => {
        const input = document.getElementById('commentInput');
        const v = input.value.trim();
        if (!v) { UI.toast('请先写点内容', 'warn'); return; }
        if (!this.requireAuth()) return;
        let local = [];
        try { local = JSON.parse(localStorage.getItem('mrz_mycomments') || '[]'); } catch (e) { local = []; }
        local.unshift({ movieid: Number(movie.movieid), text: v, at: new Date().toISOString() });
        localStorage.setItem('mrz_mycomments', JSON.stringify(local));
        input.value = '';
        UI.toast('短评已发布（本地演示）', 'ok');
        const u = Net.currentUser();
        reviewsBox.insertAdjacentHTML('afterbegin', `
          <article class="review-card full mine">
            <div class="review-poster">${UI.posterImg(movie.picture, zh, '')}</div>
            <div class="review-body">
              <h4 class="review-title">我的短评</h4>
              <div class="review-meta"><span class="review-user">${UI.esc(u ? u.username : '我')}</span><span>评论《${UI.esc(zh)}》</span></div>
              <p class="review-content">${UI.esc(v)}</p>
            </div>
          </article>`);
      });
    },

    scoreWord(v) {
      return ({ 2: '很差', 4: '较差', 6: '还行', 8: '推荐', 10: '力荐' })[v] || '';
    },

    /* 构建交互式 5 星打分组件（映射 1-10 分） */
    buildStarsInput(initial, onChange, showBig) {
      const wrap = document.createElement('div');
      wrap.className = 'stars-input' + (showBig ? ' big' : '');
      let val = initial || 0;
      const labels = { 2: '很差', 4: '较差', 6: '还行', 8: '推荐', 10: '力荐' };
      const paint = (hover) => {
        wrap.querySelectorAll('.si-star').forEach(s => {
          const sv = Number(s.dataset.v);
          s.classList.toggle('on', hover ? sv <= hover : sv <= val);
        });
      };
      for (let i = 1; i <= 5; i++) {
        const star = document.createElement('button');
        star.type = 'button';
        star.className = 'si-star' + (i * 2 <= val ? ' on' : '');
        star.dataset.v = i * 2;
        star.title = labels[i * 2] + '（' + i * 2 + ' 分）';
        star.innerHTML = `<svg viewBox="0 0 24 24" width="30" height="30"><path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.9l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9Z"/></svg>`;
        star.addEventListener('mouseenter', () => paint(i * 2));
        star.addEventListener('mouseleave', () => paint(null));
        star.addEventListener('click', () => {
          val = val === i * 2 ? 0 : i * 2;
          paint(null);
          if (onChange) onChange(val);
        });
        wrap.appendChild(star);
      }
      return wrap;
    },

    async getMyRatingsMap() {
      if (!Net.isLoggedIn()) return {};
      try {
        const res = await Api.myRatings({ page: 1, page_size: 100 });
        const map = {};
        (res.data.items || []).forEach(r => { map[Number(r.movieid)] = Number(r.rating); });
        return map;
      } catch (e) {
        return {};
      }
    },

    /* 快速连评横滑条 */
    async loadQuickStrip(currentId) {
      const track = document.getElementById('quickTrack');
      track.innerHTML = UI.skeletonCards(5);
      let items = [];
      try {
        if (Net.mode === 'mock') items = await Api.ratingCandidates(10);
        else {
          const res = await Api.randomMovies();
          items = (res.data || []).filter(m => Number(m.movieid) !== currentId).slice(0, 10);
        }
      } catch (e) { items = []; }
      items = items.filter(m => Number(m.movieid) !== currentId);

      this.quickSelections = {};
      const renderStrip = () => {
        track.innerHTML = items.map(m => {
          const sel = this.quickSelections[m.movieid] || 0;
          const zh = m.name_zh || m.moviename;
          return `
            <div class="quick-card" data-id="${m.movieid}">
              ${UI.posterImg(m.picture, zh, 'quick-poster')}
              <div class="quick-name">${UI.esc(zh)}</div>
              <div class="quick-stars" data-movie="${m.movieid}">${'<button type="button" class="qs-star" data-v="2">★</button><button type="button" class="qs-star" data-v="4">★</button><button type="button" class="qs-star" data-v="6">★</button><button type="button" class="qs-star" data-v="8">★</button><button type="button" class="qs-star" data-v="10">★</button>'}</div>
            </div>`;
        }).join('');
        track.querySelectorAll('.quick-card').forEach(card => {
          const id = Number(card.dataset.id);
          const stars = card.querySelectorAll('.qs-star');
          const paint = () => stars.forEach(s => s.classList.toggle('on', Number(s.dataset.v) <= (this.quickSelections[id] || 0)));
          paint();
          stars.forEach(s => s.addEventListener('click', () => {
            const v = Number(s.dataset.v);
            this.quickSelections[id] = this.quickSelections[id] === v ? 0 : v;
            paint();
            this.updateBatchBtn();
          }));
          card.querySelector('.quick-poster').addEventListener('click', () => {
            location.hash = '#/movie/' + id;
          });
        });
      };
      renderStrip();
      UI.bindRailPager(track, document.getElementById('simRail-pager') && null, null, null);

      const btn = document.getElementById('batchSubmitBtn');
      this.updateBatchBtn = () => {
        const n = Object.values(this.quickSelections).filter(Boolean).length;
        btn.textContent = '批量提交评分 (' + n + ')';
        btn.disabled = n === 0;
      };
      btn.addEventListener('click', async () => {
        if (!this.requireAuth()) return;
        const ids = [], scores = [];
        Object.keys(this.quickSelections).forEach(id => {
          if (this.quickSelections[id]) { ids.push(Number(id)); scores.push(this.quickSelections[id]); }
        });
        if (!ids.length) return;
        btn.disabled = true;
        try {
          const res = await Api.submitRatings(ids, scores);
          UI.toast('批量评分成功，共 ' + res.count + ' 部 🎉', 'ok');
          this.quickSelections = {};
          renderStrip();
          this.updateBatchBtn();
        } catch (e) {
          UI.toast(e.detail || '批量提交失败', 'warn');
        }
        btn.disabled = false;
      });
    },

    async loadSimilarRail(movieid) {
      const track = document.getElementById('simRail');
      if (!track) return;
      track.innerHTML = UI.skeletonCards(5);
      try {
        const items = await Api.similarMovies(movieid);
        if (!items.length) {
          track.innerHTML = '<div class="rail-empty">暂无相似影片</div>';
          return;
        }
        track.innerHTML = items.map(m => this.movieCard(m, {})).join('');
        this.bindCardActions(track);
        const arrows = track.closest('.detail-section').querySelectorAll('.rail-arrow');
        UI.bindRailPager(track, document.getElementById('simRail-pager'), arrows[0], arrows[1]);
        arrows.forEach(a => a.addEventListener('click', () => UI.slideRail(track, Number(a.dataset.dir))));
      } catch (e) {
        track.innerHTML = `<div class="rail-empty">${UI.esc(e.detail || '加载失败')}</div>`;
      }
    },

    /* ================= 个性打分（冷启动） ================= */
    async loadRate() {
      const view = document.getElementById('view');
      const user = Net.currentUser();
      view.innerHTML = `
        <section class="page rate-page">
          <div class="rate-hero-banner">
            <div class="rate-banner-emoji">⭐</div>
            <div>
              <h1 class="page-title">热烈欢迎用户：<b>${UI.esc(user ? user.username : '')}</b>，请您为以下电影打分：</h1>
              <div class="page-sub">您的评分将写入 personalratings 表，并作为 Spark ALS 协同过滤模型的冷启动输入</div>
            </div>
            <button type="button" class="btn-ghost" id="ratedListBtn">🎞️ 已评清单</button>
            <button type="button" class="btn-ghost" id="reshuffleBtn">🔄 换一批</button>
          </div>
          <div id="rateGrid" class="rate-grid">${UI.skeletonCards(10)}</div>
          <div class="rate-footer">
            <div class="rate-progress">
              <span class="rate-progress-label">已评分 <b id="rateCount">0</b> / 10</span>
              <span class="rate-progress-bar"><i id="rateProgressBar" style="width:0%"></i></span>
            </div>
            <button type="button" class="btn-primary lg" id="submitAllBtn" disabled>提交评分</button>
          </div>
        </section>`;

      this.rateSelections = {};
      const self = this;

      async function loadCandidates() {
        const grid = document.getElementById('rateGrid');
        grid.innerHTML = UI.skeletonCards(10);
        let items = [];
        try {
          if (Net.mode === 'mock') items = await Api.ratingCandidates(10);
          else {
            const res = await Api.randomMovies();
            items = (res.data || []).slice(0, 10);
          }
        } catch (e) { /* noop */ }
        self.rateSelections = {};
        if (!items.length) {
          grid.innerHTML = '<div class="state-box"><div class="state-ico">🎬</div><div class="state-title">暂无影片数据</div></div>';
          return;
        }
        grid.innerHTML = items.map((m, i) => {
          const zh = m.name_zh || m.moviename;
          return `
            <div class="rate-card" data-id="${m.movieid}">
              <div class="rate-card-index">${i + 1}</div>
              ${UI.posterImg(m.picture, zh, 'rate-card-poster')}
              <div class="rate-card-name">${UI.esc(zh)}</div>
              <div class="rate-card-sub">${UI.esc(UI.fmtYear(m.releasetime) || '')}${m.averating ? ' · 均分 ' + UI.fmtRating(m.averating) : ''}</div>
              <div class="rate-card-stars">${'<button type="button" class="rc-star" data-v="2">★</button><button type="button" class="rc-star" data-v="4">★</button><button type="button" class="rc-star" data-v="6">★</button><button type="button" class="rc-star" data-v="8">★</button><button type="button" class="rc-star" data-v="10">★</button>'}</div>
              <div class="rate-card-word"></div>
            </div>`;
        }).join('');

        const words = { 2: '很差', 4: '较差', 6: '还行', 8: '推荐', 10: '力荐' };
        grid.querySelectorAll('.rate-card').forEach(card => {
          const id = Number(card.dataset.id);
          const stars = card.querySelectorAll('.rc-star');
          const wordEl = card.querySelector('.rate-card-word');
          const paint = () => {
            const v = self.rateSelections[id] || 0;
            stars.forEach(s => s.classList.toggle('on', Number(s.dataset.v) <= v));
            wordEl.textContent = v ? v + '分 · ' + words[v] : '';
          };
          stars.forEach(s => s.addEventListener('click', () => {
            const v = Number(s.dataset.v);
            self.rateSelections[id] = self.rateSelections[id] === v ? 0 : v;
            paint();
            updateProgress();
          }));
        });

        function updateProgress() {
          const n = Object.values(self.rateSelections).filter(Boolean).length;
          document.getElementById('rateCount').textContent = n;
          document.getElementById('rateProgressBar').style.width = (n / 10 * 100) + '%';
          document.getElementById('submitAllBtn').disabled = n < 10;
        }
        updateProgress();
      }

      await loadCandidates();
      document.getElementById('reshuffleBtn').addEventListener('click', loadCandidates);
      document.getElementById('ratedListBtn').addEventListener('click', () => this.openMyRatingsDrawer());

      document.getElementById('submitAllBtn').addEventListener('click', async () => {
        if (!this.requireAuth()) return;
        const ids = [], scores = [];
        Object.keys(this.rateSelections).forEach(id => {
          if (this.rateSelections[id]) { ids.push(Number(id)); scores.push(this.rateSelections[id]); }
        });
        if (ids.length < 10) { UI.toast('请为全部 10 部电影打分', 'warn'); return; }
        const btn = document.getElementById('submitAllBtn');
        btn.disabled = true;
        btn.textContent = '提交中…';
        try {
          await Api.submitRatings(ids, scores);
          const box = document.createElement('div');
          box.className = 'rate-success-panel';
          box.innerHTML = `
            <div class="rate-success-panel-emoji">🎉</div>
            <h2>亲爱的用户：${UI.esc(user.username)}，祝贺评分成功！</h2>
            <p>您的偏好已记入数据库 personalratings 表，共 ${ids.length} 部电影</p>
            <button type="button" class="btn-gold lg" id="goRecFromRate">✨ 点击这里为您推荐电影</button>
            <div class="rate-success-panel-note">即将调用 Spark ALS 协同过滤引擎计算您的专属片单</div>`;
          view.querySelector('.rate-footer').insertAdjacentElement('afterend', box);
          box.scrollIntoView({ behavior: 'smooth', block: 'center' });
          document.getElementById('goRecFromRate').addEventListener('click', () => { location.hash = '#/recommend'; });
        } catch (e) {
          UI.toast(e.detail || '评分提交失败', 'warn');
        }
        btn.disabled = false;
        btn.textContent = '提交评分';
      });
    },

    /* ================= 猜你喜欢（推荐结果） ================= */
    async loadRecommend() {
      const view = document.getElementById('view');
      const user = Net.currentUser();
      view.innerHTML = `
        <section class="page rec-page">
          <div class="rec-banner">
            <div>
              <h1 class="page-title">🎯 亲爱的用户：<b>${UI.esc(user ? user.username : '')}</b>，猜您喜欢的电影</h1>
              <div class="rec-badges">
                <span class="alg-badge"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 2 4.5 13.5H11L10 22l8.5-11.5H12Z"/></svg>Spark ALS 协同过滤引擎已为您精准匹配 Top 10 佳片</span>
              </div>
            </div>
            <div class="rec-actions">
              <button type="button" class="btn-ghost" onclick="location.hash='#/rate'">🔄 重新打分微调口味</button>
              <button type="button" class="btn-ghost" onclick="location.hash='#/'">← 返回首页</button>
            </div>
          </div>
          <div id="recBody">${UI.skeletonCards(6)}</div>
        </section>`;

      const body = document.getElementById('recBody');
      let bag = null;
      try {
        bag = await Api.recommendResult();
      } catch (e) {
        bag = null;
      }

      const items = bag && bag.items ? bag.items : [];
      this.recRequestId = bag ? bag.request_id : null;

      /* 真实接口的推荐项不含海报/简介，逐部补拉详情以还原卡片信息 */
      if (Net.mode === 'real' && items.length) {
        items.length = 0;
        const enriched = await Promise.all((bag.items || []).map(async it => {
          try {
            const d = await Api.movieDetail(it.movieid);
            const m = d.data;
            return Object.assign({}, it, {
              picture: m.picture, averating: m.averating, numrating: m.numrating,
              typelist: m.typelist, description: m.description, director: m.director,
              leadactors: m.leadactors, releasetime: m.releasetime
            });
          } catch (e) { return it; }
        }));
        items.push(...enriched);
      }

      if (!items.length) {
        body.innerHTML = `
          <div class="state-box rec-empty">
            <div class="state-ico">🎯</div>
            <div class="state-title">还没有为您生成的推荐结果</div>
            <div class="state-sub">${Net.mode === 'mock' ? '先参与打分，再触发 ALS 引擎为您生成专属片单' : '点击下方按钮触发 Spark ALS 推荐任务（生成后结果将保存在数据库）'}</div>
            <button type="button" class="btn-gold lg" id="recGenerateBtn">✨ 生成我的专属推荐</button>
          </div>`;
        document.getElementById('recGenerateBtn').addEventListener('click', () => this.runSparkFlow(body));
        return;
      }

      this.renderRecommendResult(body, items);
    },

    renderRecommendResult(body, items) {
      const fmtScore = v => (v === null || v === undefined || isNaN(Number(v)) ? '—' : Number(v).toFixed(2));
      const fmtPct = p => (p === null ? '—' : p + '%');
      const top3 = items.slice(0, 3);
      const rest = items.slice(3);
      const featSlides = top3.map((it, i) => {
        const movie = this.resolveRecMovie(it);
        const zh = it.name_zh || it.moviename || '';
        const score = Number(it.prediction_score);
        const pct = Api.matchPercent(score);
        const crew = movie && movie.director
          ? `<div class="feat-crew">导演：${UI.esc(movie.director)}${movie.leadactors ? ' · 主演：' + UI.esc(String(movie.leadactors).slice(0, 60)) : ''}</div>` : '';
        return `
          <div class="feat-slide ${i === 0 ? 'active' : ''}" data-i="${i}" data-id="${it.movieid}">
            <div class="feat-poster">${UI.posterImg(it.picture || (movie && movie.picture), zh, '')}</div>
            <div class="feat-info">
              <div class="feat-badges"><span class="feat-rank">TOP ${it.position}</span><span class="feat-alg">Spark ALS</span></div>
              <h3 class="feat-name">${UI.esc(zh)}</h3>
              <div class="feat-en">${UI.esc(it.moviename || '')}</div>
              ${crew}
              <div class="feat-scores">
                <span class="feat-score">推荐指数 <b>${fmtScore(score)}</b></span>
                <span class="feat-match">匹配度 <b>${fmtPct(pct)}</b></span>
              </div>
              <p class="feat-desc">${UI.esc(movie ? (movie.tagline || (movie.description ? String(movie.description).slice(0, 120) + '…' : '暂无简介')) : '暂无简介')}</p>
              <div class="feat-actions">
                <button type="button" class="btn-primary" data-act="detail" data-id="${it.movieid}">查看详情</button>
                <button type="button" class="btn-ghost" data-act="not" data-id="${it.movieid}">不感兴趣</button>
              </div>
            </div>
          </div>`;
      }).join('');

      body.innerHTML = `
        <div class="rec-featured">
          <div class="rec-featured-head">
            <h2 class="section-title">Top 推荐焦点 · 为您高亮呈现</h2>
            <div class="rail-tools">
              <span class="rail-pager" id="featPager"><b>1</b> / ${top3.length}</span>
              <button type="button" class="rail-arrow" id="featPrev"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 5-7 7 7 7"/></svg></button>
              <button type="button" class="rail-arrow" id="featNext"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 5 7 7-7 7"/></svg></button>
            </div>
          </div>
          <div class="feat-track" id="featTrack">${featSlides}</div>
        </div>
        <div class="rec-grid-head">
          <h2 class="section-title">完整 Top ${items.length} 推荐影片矩阵</h2>
          <button type="button" class="btn-ghost sm" id="recRegenBtn">🔄 重新生成</button>
        </div>
        <div class="rec-grid" id="recGrid">
          ${items.map(it => {
            const zh = it.name_zh || it.moviename;
            const score = Number(it.prediction_score);
            const pct = Api.matchPercent(score);
            return `
              <article class="rec-card" data-id="${it.movieid}" data-score="${isNaN(score) ? '' : score}">
                <div class="poster">
                  ${UI.posterImg(it.picture, zh, '')}
                  <span class="rank-badge r${Math.min(3, it.position)}">${it.position}</span>
                  <span class="rec-score-badge">${fmtScore(score)}<i>分</i></span>
                </div>
                <h3 class="mc-name">${UI.esc(zh)}</h3>
                <div class="mc-sub">${UI.esc(it.moviename || '')}</div>
                <div class="rec-match">匹配度 ${fmtPct(pct)}</div>
                <div class="rec-card-actions">
                  <button type="button" class="pa-btn primary" data-act="detail">查看详情</button>
                  <button type="button" class="pa-btn" data-act="not">不感兴趣</button>
                </div>
              </article>`;
          }).join('')}
        </div>`;

      /* 焦点走廊切换 */
      const featTrack = document.getElementById('featTrack');
      const featPager = document.getElementById('featPager');
      let fi = 0;
      const featGo = (i) => {
        fi = (i + top3.length) % top3.length;
        featTrack.querySelectorAll('.feat-slide').forEach((s, j) => s.classList.toggle('active', j === fi));
        featPager.innerHTML = `<b>${fi + 1}</b> / ${top3.length}`;
      };
      document.getElementById('featPrev').addEventListener('click', () => featGo(fi - 1));
      document.getElementById('featNext').addEventListener('click', () => featGo(fi + 1));

      /* 事件与交互 */
      body.querySelectorAll('[data-act="detail"]').forEach(b => b.addEventListener('click', e => {
        e.stopPropagation();
        this.trackRecEvent(b.dataset.id, 'click');
        location.hash = '#/movie/' + b.dataset.id;
      }));
      body.querySelectorAll('[data-act="not"]').forEach(b => b.addEventListener('click', e => {
        e.stopPropagation();
        const id = Number(b.dataset.id);
        this.trackRecEvent(id, 'not_interested');
        UI.toast('已记录“不感兴趣”，将优化您的推荐', 'ok');
        const card = b.closest('.rec-card') || b.closest('.feat-slide');
        if (card) card.style.display = 'none';
      }));
      body.querySelectorAll('.rec-card').forEach(c => c.addEventListener('click', e => {
        if (e.target.closest('[data-act]')) return;
        this.trackRecEvent(c.dataset.id, 'click');
        location.hash = '#/movie/' + c.dataset.id;
      }));

      document.getElementById('recRegenBtn').addEventListener('click', () => this.runSparkFlow(body, true));

      /* 曝光事件：进入可视区域后记录 */
      if (Net.mode === 'real' && this.recRequestId) {
        const obs = new IntersectionObserver(entries => {
          entries.forEach(en => {
            if (en.isIntersecting) {
              const id = Number(en.target.dataset.id);
              this.trackRecEvent(id, 'impression');
              obs.unobserve(en.target);
            }
          });
        }, { threshold: 0.4 });
        body.querySelectorAll('.rec-card').forEach(c => obs.observe(c));
        this.state.cleanup.push(() => obs.disconnect());
      }
    },

    resolveRecMovie(item) {
      if (window.MOCK_MOVIES) {
        const m = window.MOCK_MOVIES.find(x => x.movieid === Number(item.movieid));
        if (m) return m;
      }
      // 真实模式：推荐项已补拉详情（含 description/picture 字段）
      if (item && (item.description || item.picture || item.director)) return item;
      return null;
    },

    trackRecEvent(movieid, type) {
      if (!this.recRequestId) return;
      Api.recommendEvent(this.recRequestId, Number(movieid), type).catch(() => { /* 静默失败 */ });
    },

    /* Spark 三步加载动效 + 生成推荐 */
    async runSparkFlow(bodyEl, reload) {
      if (!this.requireAuth()) return;
      const layer = document.getElementById('sparkLayer');
      const steps = layer.querySelectorAll('.spark-step');
      const bar = document.getElementById('sparkProgressBar');
      layer.hidden = false;
      steps.forEach(s => s.classList.remove('done', 'active'));
      bar.style.width = '0%';

      const mark = (n, done) => {
        steps.forEach(s => {
          const k = Number(s.dataset.step);
          s.classList.toggle('active', k === n && !done);
          s.classList.toggle('done', k < n || done);
        });
      };
      mark(1, false);
      const t1 = 1400, t2 = 2000, t3 = 1400;
      const total = t1 + t2 + t3;
      const t0 = Date.now();
      const ticker = setInterval(() => {
        const el = Date.now() - t0;
        bar.style.width = Math.min(100, el / total * 100) + '%';
      }, 50);

      /* 真实模式：并行调用生成接口 */
      let genError = null;
      let genPromise = Promise.resolve();
      if (Net.mode === 'real') {
        genPromise = Api.generateRecommend().catch(e => { genError = e; });
      } else {
        genPromise = Api.generateRecommend().catch(e => { genError = e; });
      }

      setTimeout(() => mark(2, false), t1);
      setTimeout(() => mark(3, false), t1 + t2);
      const done = async () => {
        clearInterval(ticker);
        bar.style.width = '100%';
        mark(4, true);
        await genPromise;
        await new Promise(r => setTimeout(r, 700));
        layer.hidden = true;
        if (genError) {
          UI.toast(genError.detail || '推荐生成失败', 'warn');
          if (genError.status === 503) {
            UI.toast('推荐生成任务服务尚未配置（后端 Celery/Spark 未启用）', 'warn');
          }
        } else {
          UI.toast('Spark ALS 计算完成，正在为您呈现专属片单 ✨', 'ok');
        }
        if (bodyEl) {
          try {
            const bag = await Api.recommendResult();
            this.recRequestId = bag ? bag.request_id : null;
            const items = bag && bag.items ? bag.items : [];
            if (items.length) this.renderRecommendResult(bodyEl, items);
            else {
              bodyEl.innerHTML = `
                <div class="state-box">
                  <div class="state-ico">🎯</div>
                  <div class="state-title">推荐任务已提交</div>
                  <div class="state-sub">${Net.mode === 'real' ? '后端任务队列尚未产出结果，请稍后刷新页面查看（或演示模式下自动生成）' : '暂时没有可展示的推荐结果'}</div>
                  <button type="button" class="btn-primary" onclick="location.reload()">刷新查看</button>
                </div>`;
            }
          } catch (e) {
            UI.toast('读取推荐结果失败：' + (e.detail || ''), 'warn');
          }
        }
      };
      setTimeout(done, total + 200);
    },

    /* ================= 高分口碑榜 ================= */
    async loadTop() {
      const view = document.getElementById('view');
      view.innerHTML = `
        <section class="page">
          <div class="page-head">
            <h1 class="page-title">🏆 高分口碑榜</h1>
            <div class="page-sub">按系统综合评分排序 · 前 30 名</div>
          </div>
          <div id="topGrid" class="movie-grid">${UI.skeletonCards(12)}</div>
        </section>`;
      const grid = document.getElementById('topGrid');
      try {
        const res = await Api.movies({ sort_by: 'rating', order: 'desc', page: 1, page_size: 30 });
        const items = res.data.items || [];
        grid.innerHTML = items.map((m, i) => this.movieCard(m, { rank: i + 1 })).join('');
        this.bindCardActions(grid);
      } catch (e) {
        grid.innerHTML = `<div class="state-box"><div class="state-ico">⚠️</div><div class="state-title">加载失败</div><div class="state-sub">${UI.esc(e.detail || '')}</div></div>`;
      }
    },

    /* ================= 热门影评 ================= */
    async loadReviews() {
      const view = document.getElementById('view');
      view.innerHTML = `
        <section class="page">
          <div class="page-head">
            <h1 class="page-title">💬 热门影评</h1>
            <div class="page-sub">编辑部精选 · 深度影评与口碑社区</div>
          </div>
          <div id="reviewsList"></div>
        </section>`;
      const list = document.getElementById('reviewsList');
      list.innerHTML = '<div class="sk-line w80"></div><div class="sk-line w60"></div>'.repeat(3);
      try {
        const reviews = await Api.reviews();
        list.innerHTML = reviews.map(r => this.reviewCard(r, true)).join('');
        this.bindReviewActions(list);
      } catch (e) {
        list.innerHTML = `<div class="state-box"><div class="state-ico">⚠️</div><div class="state-title">加载失败</div><div class="state-sub">${UI.esc(e.detail || '')}</div></div>`;
      }
    },

    /* ================= 我的评分 ================= */
    async loadMyRatings() {
      const view = document.getElementById('view');
      view.innerHTML = `
        <section class="page">
          <div class="page-head">
            <h1 class="page-title">🎞️ 我的评分</h1>
            <div class="page-sub">这些评分将用于 Spark ALS 模型训练 · 点击星星可修改评分</div>
          </div>
          <div id="myRatingsList"></div>
          <div id="myRatingsPager" class="pager"></div>
        </section>`;
      const list = document.getElementById('myRatingsList');
      await this.loadMyRatingsPage(1, list);
    },

    async loadMyRatingsPage(page, list) {
      list.innerHTML = UI.skeletonCards(6);
      try {
        const res = await Api.myRatings({ page, page_size: 20 });
        const items = res.data.items || [];
        const total = res.data.total || 0;
        if (!items.length) {
          list.innerHTML = `
            <div class="state-box">
              <div class="state-ico">⭐</div>
              <div class="state-title">还没有评分记录</div>
              <div class="state-sub">去给喜欢的电影打分，开启您的专属推荐之旅</div>
              <button type="button" class="btn-primary" onclick="location.hash='#/rate'">立即参与打分</button>
            </div>`;
          return;
        }
        list.innerHTML = items.map(r => {
          const zh = r.name_zh || r.moviename || '';
          return `
            <div class="myrate-row" data-id="${r.movieid}">
              ${UI.posterImg(r.picture, zh, 'myrate-poster')}
              <div class="myrate-info">
                <div class="myrate-name">${UI.esc(zh)}</div>
                <div class="myrate-sub">评分于 ${UI.esc(UI.fmtTime(r.rated_at))} · 评分 ID ${UI.esc(r.ratingid)}</div>
              </div>
              <div class="myrate-stars"></div>
              <div class="myrate-score">${UI.fmtRating(r.rating)}<i>分</i></div>
              <button type="button" class="myrate-save btn-primary sm" data-id="${r.movieid}">更新评分</button>
            </div>`;
        }).join('');

        list.querySelectorAll('.myrate-row').forEach(row => {
          const id = Number(row.dataset.id);
          const item = items.find(x => Number(x.movieid) === id);
          const starsWrap = row.querySelector('.myrate-stars');
          let sel = Number(item.rating);
          const widget = this.buildStarsInput(sel, v => { sel = v; }, false);
          starsWrap.appendChild(widget);
          row.querySelector('.myrate-save').addEventListener('click', async () => {
            if (!sel) { UI.toast('请先选择评分', 'warn'); return; }
            try {
              await Api.submitRatings([id], [sel]);
              row.querySelector('.myrate-score').innerHTML = UI.fmtRating(sel) + '<i>分</i>';
              UI.toast('评分已更新', 'ok');
            } catch (e) {
              UI.toast(e.detail || '更新失败', 'warn');
            }
          });
        });
        this.renderPager('myRatingsPager', total, 20, page, p => {
          this.loadMyRatingsPage(p, list);
          UI.scrollTop('smooth');
        });
      } catch (e) {
        list.innerHTML = `<div class="state-box"><div class="state-ico">⚠️</div><div class="state-title">加载失败</div><div class="state-sub">${UI.esc(e.detail || '')}</div></div>`;
      }
    },

    /* ================= 我的收藏 ================= */
    async loadMyFavorites() {
      const view = document.getElementById('view');
      view.innerHTML = `
        <section class="page">
          <div class="page-head">
            <h1 class="page-title">❤️ 我的收藏</h1>
            <div class="sort-tabs" id="favTabs">
              <button type="button" class="sort-tab active" data-status="">全部</button>
              <button type="button" class="sort-tab" data-status="want_to_watch">想看</button>
              <button type="button" class="sort-tab" data-status="watched">已看</button>
            </div>
          </div>
          <div id="favGrid" class="movie-grid">${UI.skeletonCards(8)}</div>
        </section>`;

      let status = '';
      const grid = document.getElementById('favGrid');
      const self = this;
      const load = async () => {
        grid.innerHTML = UI.skeletonCards(8);
        try {
          const res = await Api.myFavorites({ status: status || undefined, page: 1, page_size: 50 });
          const items = res.data.items || [];
          if (!items.length) {
            grid.innerHTML = `
              <div class="state-box">
                <div class="state-ico">❤️</div>
                <div class="state-title">${status ? '该分类下暂无收藏' : '还没有收藏任何电影'}</div>
                <div class="state-sub">在电影详情页点击「想看」或「看过」即可收藏</div>
                <button type="button" class="btn-primary" onclick="location.hash='#/'">去逛逛首页</button>
              </div>`;
            return;
          }
          grid.innerHTML = items.map(f => {
            const zh = f.name_zh || f.moviename || '';
            const isWant = f.status === 'want_to_watch';
            return `
              <article class="movie-card" data-id="${f.movieid}">
                <div class="poster">
                  ${UI.posterImg(f.picture, zh, '')}
                  <span class="poster-badge ${isWant ? 'green' : 'gold'}">${isWant ? '想看' : '已看'}</span>
                  ${f.averating ? `<span class="poster-score">${UI.fmtRating(f.averating)}</span>` : ''}
                  <div class="poster-shade"></div>
                  <div class="poster-actions">
                    <button type="button" class="pa-btn primary" data-act="detail">查看详情</button>
                    <button type="button" class="pa-btn" data-act="toggle">${isWant ? '标记已看' : '标记想看'}</button>
                  </div>
                </div>
                <div class="mc-info">
                  <h3 class="mc-name">${UI.esc(zh)}</h3>
                  <div class="mc-sub">${UI.esc(UI.fmtTime(f.updated_at) || '')}</div>
                  <div class="mc-rating">${UI.starsHtml(f.averating)}<span class="mc-score">${UI.fmtRating(f.averating)}</span></div>
                </div>
              </article>`;
          }).join('');
          grid.querySelectorAll('.movie-card').forEach(card => {
            const id = Number(card.dataset.id);
            const item = items.find(x => Number(x.movieid) === id);
            card.addEventListener('click', e => {
              if (e.target.closest('[data-act]')) return;
              location.hash = '#/movie/' + id;
            });
            const dBtn = card.querySelector('[data-act="detail"]');
            if (dBtn) dBtn.addEventListener('click', () => { location.hash = '#/movie/' + id; });
            const tBtn = card.querySelector('[data-act="toggle"]');
            if (tBtn) tBtn.addEventListener('click', async () => {
              const next = item.status === 'want_to_watch' ? 'watched' : 'want_to_watch';
              try {
                const r = await Api.toggleFavorite(id, next);
                UI.toast(r.action === 'remove' ? '已取消收藏' : '已标记为「' + (next === 'watched' ? '已看' : '想看') + '」', 'ok');
                load();
              } catch (e) {
                UI.toast(e.detail || '操作失败', 'warn');
              }
            });
          });
        } catch (e) {
          grid.innerHTML = `<div class="state-box"><div class="state-ico">⚠️</div><div class="state-title">加载失败</div><div class="state-sub">${UI.esc(e.detail || '')}</div></div>`;
        }
      };

      document.getElementById('favTabs').querySelectorAll('.sort-tab').forEach(t => t.addEventListener('click', () => {
        document.querySelectorAll('#favTabs .sort-tab').forEach(x => x.classList.remove('active'));
        t.classList.add('active');
        status = t.dataset.status;
        load();
      }));
      await load();
    },

    /* ================= 登录 / 注册弹窗 ================= */
    openAuth(tab) {
      const modal = document.getElementById('authModal');
      modal.hidden = false;
      this.buildAuthWall();
      this.switchAuthTab(tab || 'login');
      document.getElementById('authClose').onclick = () => { modal.hidden = true; };
      modal.addEventListener('click', e => {
        if (e.target === modal) modal.hidden = true;
      });
    },

    buildAuthWall() {
      const wall = document.getElementById('authPosterWall');
      if (wall.dataset.built === '1') return;
      wall.dataset.built = '1';
      const picks = [318, 4993, 109487, 148478, 5618, 2324, 446, 79132, 98809];
      wall.innerHTML = picks.map(id => {
        const m = window.MOCK_MOVIES.find(x => x.movieid === id);
        return m ? `<div class="auth-poster-tile">${UI.posterImg(m.picture, m.name_zh, '')}</div>` : '';
      }).join('');
    },

    switchAuthTab(tab) {
      const tabs = document.querySelectorAll('.auth-tab');
      const loginForm = document.getElementById('loginForm');
      const regForm = document.getElementById('registerForm');
      const indicator = document.getElementById('authTabIndicator');
      tabs.forEach(t => t.classList.toggle('active', t.dataset.authtab === tab));
      loginForm.hidden = tab !== 'login';
      regForm.hidden = tab !== 'register';
      // 指示线滑动
      const activeTab = [...tabs].find(t => t.dataset.authtab === tab);
      if (activeTab && indicator) {
        indicator.style.left = activeTab.offsetLeft + 'px';
        indicator.style.width = activeTab.offsetWidth + 'px';
      }
    },

    bindAuthEvents() {
      // Tab 切换
      document.querySelectorAll('.auth-tab').forEach(t => t.addEventListener('click', () => this.switchAuthTab(t.dataset.authtab)));
      document.getElementById('goRegister').addEventListener('click', () => this.switchAuthTab('register'));
      document.getElementById('goLogin').addEventListener('click', () => this.switchAuthTab('login'));

      // 密码显隐
      document.querySelectorAll('[data-eye]').forEach(b => b.addEventListener('click', () => {
        const input = document.getElementById(b.dataset.eye);
        const show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        b.querySelector('.eye-open').hidden = show;
        b.querySelector('.eye-closed').hidden = !show;
      }));

      // 登录提交
      document.getElementById('loginForm').addEventListener('submit', async e => {
        e.preventDefault();
        const account = document.getElementById('loginAccount').value.trim();
        const pwd = document.getElementById('loginPwd').value;
        if (!account) { UI.toast('请输入账号（昵称/手机号/邮箱）', 'warn'); return; }
        if (!pwd) { UI.toast('请输入密码', 'warn'); return; }
        const btn = document.getElementById('loginBtn');
        btn.disabled = true; btn.textContent = '登录中…';
        try {
          const res = await Api.login(account, pwd);
          Net.setToken(res.access_token);
          Net.setCurrentUserId(res.userid);
          const meRes = await Api.me();
          Net.setCurrentUser(meRes.data);
          document.getElementById('authModal').hidden = true;
          this.renderTopbar();
          UI.toast('欢迎回来，' + meRes.data.username + '！', 'ok');
          this.route();
        } catch (err) {
          UI.toast(err.detail || '登录失败', 'warn');
        }
        btn.disabled = false; btn.textContent = '立即登录';
      });

      // 注册提交
      document.getElementById('registerForm').addEventListener('submit', async e => {
        e.preventDefault();
        const payload = {
          username: document.getElementById('regUsername').value.trim(),
          phone: document.getElementById('regPhone').value.trim(),
          email: document.getElementById('regEmail').value.trim(),
          password: document.getElementById('regPwd').value,
          confirm_password: document.getElementById('regPwd2').value
        };
        if (!payload.username) { UI.toast('请输入昵称', 'warn'); return; }
        if (!payload.phone) { UI.toast('请输入手机号', 'warn'); return; }
        if (!payload.email) { UI.toast('请输入邮箱', 'warn'); return; }
        const btn = document.getElementById('registerBtn');
        btn.disabled = true; btn.textContent = '注册中…';
        try {
          const res = await Api.register(payload);
          this.showRegisterSuccess(payload.username);
        } catch (err) {
          UI.toast(err.detail || '注册失败', 'warn');
        }
        btn.disabled = false; btn.textContent = '立即注册';
      });
    },

    showRegisterSuccess(username) {
      const formArea = document.querySelector('.auth-form');
      const body = document.getElementById('registerForm');
      const regBtn = document.getElementById('registerBtn');
      // 保留表单，插入成功卡片
      const box = document.createElement('div');
      box.className = 'reg-success';
      box.innerHTML = `
        <div class="reg-success-emoji">🎉</div>
        <h3>热烈欢迎用户：${UI.esc(username)}<br>账号注册成功！</h3>
        <button type="button" class="auth-submit" id="regGoLogin">请点击这里登录</button>
        <div class="reg-success-count">3 秒后自动跳转登录…</div>`;
      body.parentNode.insertBefore(box, body.nextSibling);
      box.scrollIntoView({ behavior: 'smooth', block: 'center' });
      document.getElementById('regGoLogin').addEventListener('click', () => {
        box.remove();
        this.switchAuthTab('login');
        document.getElementById('loginAccount').value = username;
        document.getElementById('regUsername').value = '';
        document.getElementById('regPhone').value = '';
        document.getElementById('regEmail').value = '';
        document.getElementById('regPwd').value = '';
        document.getElementById('regPwd2').value = '';
      });
      let n = 3;
      const timer = setInterval(() => {
        n -= 1;
        const el = box.querySelector('.reg-success-count');
        if (el) el.textContent = n + ' 秒后自动跳转登录…';
        if (n <= 0) {
          clearInterval(timer);
          box.remove();
          this.switchAuthTab('login');
          document.getElementById('loginAccount').value = username;
        }
      }, 1000);
    },

    /* ================= 我的资料 ================= */
    openProfile() {
      const user = Net.currentUser();
      if (!user) return;
      this.openGeneric(`
        <h3 class="g-title">👤 我的资料</h3>
        <form id="profileForm" class="g-form">
          <label class="g-field"><span>昵称</span><input type="text" id="pfUsername" value="${UI.esc(user.username)}"></label>
          <label class="g-field"><span>邮箱</span><input type="email" id="pfEmail" value="${UI.esc(user.email || '')}"></label>
          <label class="g-field"><span>手机号</span><input type="tel" id="pfPhone" value="${UI.esc(user.phone || '')}"></label>
          <label class="g-field"><span>头像 URL</span><input type="text" id="pfAvatar" value="${UI.esc(user.avatar || '')}" placeholder="可留空，留空则使用昵称首字头像"></label>
          <div class="g-actions">
            <button type="button" class="btn-ghost" id="pfCancel">取消</button>
            <button type="submit" class="btn-primary">保存修改</button>
          </div>
        </form>`);
      document.getElementById('pfCancel').addEventListener('click', () => this.closeGeneric());
      document.getElementById('profileForm').addEventListener('submit', async e => {
        e.preventDefault();
        const payload = {
          username: document.getElementById('pfUsername').value.trim(),
          email: document.getElementById('pfEmail').value.trim(),
          phone: document.getElementById('pfPhone').value.trim(),
          avatar: document.getElementById('pfAvatar').value.trim() || null
        };
        try {
          await Api.updateMe(payload);
          Net.setCurrentUser(Object.assign({}, Net.currentUser(), payload));
          this.renderTopbar();
          this.closeGeneric();
          UI.toast('资料修改成功', 'ok');
        } catch (err) {
          UI.toast(err.detail || '保存失败', 'warn');
        }
      });
    },

    /* ================= 修改密码 ================= */
    openPassword() {
      this.openGeneric(`
        <h3 class="g-title">🔒 修改密码</h3>
        <form id="pwdForm" class="g-form">
          <label class="g-field"><span>原密码</span><input type="password" id="pwOld" autocomplete="current-password"></label>
          <label class="g-field"><span>新密码</span><input type="password" id="pwNew" autocomplete="new-password" placeholder="8 位以上，含字母和数字"></label>
          <label class="g-field"><span>确认新密码</span><input type="password" id="pwNew2" autocomplete="new-password"></label>
          <div class="g-actions">
            <button type="button" class="btn-ghost" id="pwCancel">取消</button>
            <button type="submit" class="btn-primary">确认修改</button>
          </div>
        </form>`);
      document.getElementById('pwCancel').addEventListener('click', () => this.closeGeneric());
      document.getElementById('pwdForm').addEventListener('submit', async e => {
        e.preventDefault();
        const oldP = document.getElementById('pwOld').value;
        const newP = document.getElementById('pwNew').value;
        const newP2 = document.getElementById('pwNew2').value;
        if (newP !== newP2) { UI.toast('两次输入的新密码不一致', 'warn'); return; }
        try {
          await Api.changePassword(oldP, newP);
          this.closeGeneric();
          UI.toast('密码修改成功', 'ok');
        } catch (err) {
          UI.toast(err.detail || '修改失败', 'warn');
        }
      });
    },

    openGeneric(html) {
      const modal = document.getElementById('genericModal');
      document.getElementById('genericCard').innerHTML = html;
      modal.hidden = false;
      modal.onclick = e => { if (e.target === modal) this.closeGeneric(); };
    },
    closeGeneric() {
      document.getElementById('genericModal').hidden = true;
    },

    /* ================= 快速评分悬浮组件 ================= */
    openQuickRate(movieid, anchorBtn) {
      const old = document.querySelector('.quickrate-pop');
      if (old) old.remove();
      const pop = document.createElement('div');
      pop.className = 'quickrate-pop';
      const m = window.MOCK_MOVIES.find(x => x.movieid === Number(movieid)) || null;
      const zh = m ? (m.name_zh || m.moviename) : '电影 #' + movieid;
      pop.innerHTML = `
        <div class="qr-head">快速评分 · ${UI.esc(zh)}</div>
        <div class="qr-stars"></div>
        <div class="qr-word"></div>
        <div class="qr-actions">
          <button type="button" class="btn-ghost sm" data-act="cancel">取消</button>
          <button type="button" class="btn-primary sm" data-act="submit">提交评分</button>
        </div>`;
      document.body.appendChild(pop);
      let sel = 0;
      const widget = this.buildStarsInput(0, v => {
        sel = v;
        pop.querySelector('.qr-word').textContent = v ? v + '分 · ' + this.scoreWord(v) : '';
      }, true);
      pop.querySelector('.qr-stars').appendChild(widget);
      const rect = anchorBtn.getBoundingClientRect();
      pop.style.left = Math.min(rect.left, window.innerWidth - 300) + 'px';
      pop.style.top = (rect.bottom + 8) + 'px';
      const close = () => pop.remove();
      pop.addEventListener('click', async e => {
        const act = e.target.closest('[data-act]');
        if (!act) return;
        if (act.dataset.act === 'cancel') { close(); return; }
        if (!this.requireAuth()) { close(); return; }
        if (!sel) { UI.toast('请先点亮星星', 'warn'); return; }
        try {
          await Api.submitRatings([Number(movieid)], [sel]);
          UI.toast('评分成功 🎉 已记入 personalratings', 'ok');
        } catch (err) {
          UI.toast(err.detail || '评分失败', 'warn');
        }
        close();
      });
      document.addEventListener('click', function handler(e) {
        if (!pop.contains(e.target) && !anchorBtn.contains(e.target)) {
          document.removeEventListener('click', handler);
          pop.remove();
        }
      });
    },

    /* ================= 抽屉：已评清单 ================= */
    async openMyRatingsDrawer() {
      const layer = document.getElementById('drawerLayer');
      document.getElementById('drawerTitle').textContent = '🎞️ 我的已评清单';
      const body = document.getElementById('drawerBody');
      body.innerHTML = '<div class="sk-line w80"></div><div class="sk-line w60"></div>'.repeat(4);
      layer.hidden = false;
      try {
        const res = await Api.myRatings({ page: 1, page_size: 100 });
        const items = res.data.items || [];
        body.innerHTML = items.length ? items.map(r => {
          const zh = r.name_zh || r.moviename || '';
          return `
            <div class="drawer-rate-row" data-id="${r.movieid}">
              ${UI.posterImg(r.picture, zh, 'drawer-poster')}
              <div class="drawer-rate-info">
                <div class="drawer-rate-name">${UI.esc(zh)}</div>
                <div class="drawer-rate-time">${UI.esc(UI.fmtTime(r.rated_at))}</div>
              </div>
              <span class="drawer-rate-score">${UI.fmtRating(r.rating)} 分</span>
            </div>`;
        }).join('') : '<div class="rail-empty">还没有评分记录，快去打分吧</div>';
        body.querySelectorAll('.drawer-rate-row').forEach(row => row.addEventListener('click', () => {
          this.closeDrawer();
          location.hash = '#/movie/' + row.dataset.id;
        }));
      } catch (e) {
        body.innerHTML = `<div class="rail-empty">${UI.esc(e.detail || '加载失败')}</div>`;
      }
    },
    closeDrawer() {
      document.getElementById('drawerLayer').hidden = true;
    },

    /* ================= 海报放大 ================= */
    openLightbox(src) {
      const lb = document.getElementById('lightbox');
      const img = document.getElementById('lightboxImg');
      lb.hidden = false;
      img.src = src || '';
      img.onerror = () => { img.src = UI.fallbackSvg('海报预览'); };
    },

    /* ================= 启动 ================= */
    init() {
      this.bindAuthEvents();
      document.getElementById('authClose').addEventListener('click', () => {
        document.getElementById('authModal').hidden = true;
      });
      document.getElementById('authModal').addEventListener('click', e => {
        if (e.target === e.currentTarget) e.currentTarget.hidden = true;
      });
      // 已评清单快捷入口（放在打分页）
      this.boot();
    }
  };

  window.App = App;
  document.addEventListener('DOMContentLoaded', () => App.init());
})();



