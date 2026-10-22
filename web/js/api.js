/* ============================================================
 * 智影 · API 客户端层
 * 严格对齐 api_contract.md：16 个方法/路径组合
 * 支持 真实 FastAPI / 内置 Mock 双模式无缝切换
 * ============================================================ */
(function () {
  'use strict';

  const CFG = window.APP_CONFIG;

  /* ---------- 基础网络 ---------- */
  const Net = {
    _token: null,
    mode: 'mock',        // 'real' | 'mock'
    probing: false,

    token() { return this._token || localStorage.getItem('mrz_token') || null; },
    setToken(t) {
      this._token = t;
      if (t) localStorage.setItem('mrz_token', t);
      else localStorage.removeItem('mrz_token');
    },
    currentUserId() {
      try { return Number(localStorage.getItem('mrz_userid') || 0); } catch (e) { return 0; }
    },
    setCurrentUserId(id) { localStorage.setItem('mrz_userid', String(id || '')); },
    currentUser() {
      try { return JSON.parse(localStorage.getItem('mrz_user') || 'null'); } catch (e) { return null; }
    },
    setCurrentUser(u) { localStorage.setItem('mrz_user', JSON.stringify(u || null)); },

    isLoggedIn() { return !!this.token(); },

    /* 请求基元 */
    async raw(path, opts) {
      opts = opts || {};
      const headers = Object.assign({}, opts.headers || {});
      if (opts.body && typeof opts.body !== 'string') {
        headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(opts.body);
      }
      if (this.token()) headers['Authorization'] = 'Bearer ' + this.token();

      const url = CFG.API_BASE_URL.replace(/\/+$/, '') + path;
      let res;
      try {
        res = await fetch(url, {
          method: opts.method || 'GET',
          headers,
          body: opts.body
        });
      } catch (e) {
        const err = new Error('无法连接后端服务');
        err.network = true;
        throw err;
      }

      let data = null;
      try { data = await res.json(); } catch (e) { data = null; }

      if (!res.ok) {
        const err = new Error('HTTP ' + res.status);
        err.status = res.status;
        err.data = data;
        err.detail = extractDetail(data, res.status);
        throw err;
      }
      return data;
    },

    get(path) { return this.raw(path); },
    post(path, body) { return this.raw(path, { method: 'POST', body }); },
    put(path, body) { return this.raw(path, { method: 'PUT', body }); },

    /* 探测后端是否可达 → 决定模式 */
    async probe() {
      if (this.probing) return;
      this.probing = true;
      const want = CFG.DATA_MODE;
      if (want === 'mock') { this.mode = 'mock'; this.probing = false; return; }
      if (want === 'real') { this.mode = 'real'; this.probing = false; return; }

      // auto：尝试健康检查
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), CFG.PROBE_TIMEOUT);
        const res = await fetch(CFG.API_BASE_URL.replace(/\/+$/, '') + '/', { signal: ctrl.signal });
        clearTimeout(t);
        this.mode = res.ok ? 'real' : 'mock';
      } catch (e) {
        this.mode = 'mock';
      }
      this.probing = false;
    }
  };

  function extractDetail(data, status) {
    if (!data) return '请求失败（HTTP ' + status + '）';
    if (typeof data.detail === 'string') return data.detail;
    if (data.detail && Array.isArray(data.detail)) {
      // FastAPI 422
      const first = data.detail[0];
      if (first) return (first.msg || '参数校验失败') + (first.loc && first.loc.length ? '：' + first.loc.join('.') : '');
      return '参数校验失败';
    }
    if (data.detail && data.detail.message) return data.detail.message;
    if (data.msg) return data.msg;
    if (data.message) return data.message;
    return '请求失败（HTTP ' + status + '）';
  }

  /* ---------- 错误映射（中文提示） ---------- */
  function friendlyError(err) {
    if (err.friendly) return err;
    if (err.network) { err.friendly = true; err.detail = '无法连接后端服务，已自动切换到演示模式'; return err; }
    switch (err.status) {
      case 400: err.detail = err.detail || '原密码错误'; break;
      case 401: err.detail = err.detail || '登录凭据错误，或登录已过期'; break;
      case 403: err.detail = err.detail || '无权访问：请求中的 userid 与当前登录用户不一致'; break;
      case 404: err.detail = err.detail || '资源不存在或已删除'; break;
      case 409: err.detail = err.detail || '资料冲突或并发冲突'; break;
      case 422: err.detail = err.detail || '请求参数未通过校验'; break;
      case 503: err.detail = err.detail || '推荐生成任务服务尚未配置'; break;
      default: err.detail = err.detail || ('请求失败（HTTP ' + err.status + '）');
    }
    return err;
  }

  /* ---------- 服务门面：按模式分发 ---------- */
  const Api = {
    mode: () => Net.mode,

    async call(realFn, mockFn) {
      if (Net.mode === 'real') {
        try {
          return await realFn();
        } catch (err) {
          if (err && err.status === 401 && Net.isLoggedIn()) {
            Net.setToken(null);
            Net.setCurrentUser(null);
            Net.setCurrentUserId(0);
            if (window.App && App.onSessionExpired) App.onSessionExpired();
          }
          throw friendlyError(err);
        }
      }
      return mockFn();
    },

    /* GET / 服务状态 */
    health: function () {
      return this.call(() => Net.get('/'), () => window.MockSvc.health());
    },

    /* ---------- 认证 ---------- */
    register: function (payload) {
      return this.call(() => Net.post('/api/auth/register', payload), () => window.MockSvc.register(payload));
    },
    login: function (account, password) {
      return this.call(() => Net.post('/api/auth/login', { account, password }), () => window.MockSvc.login(account, password));
    },
    me: function () {
      return this.call(() => Net.get('/api/auth/me'), () => window.MockSvc.me());
    },
    updateMe: function (payload) {
      return this.call(() => Net.put('/api/auth/me', payload), () => window.MockSvc.updateMe(payload));
    },
    changePassword: function (oldPassword, newPassword) {
      return this.call(() => Net.put('/api/auth/me/password', { old_password: oldPassword, new_password: newPassword }),
        () => window.MockSvc.changePassword(oldPassword, newPassword));
    },

    /* ---------- 电影 ---------- */
    randomMovies: function () {
      return this.call(() => Net.get('/api/movies/random'), () => window.MockSvc.randomMovies());
    },
    movies: function (params) {
      const qs = new URLSearchParams();
      if (params.q) qs.set('q', params.q);
      if (params.category_id) qs.set('category_id', params.category_id);
      if (params.sort_by) qs.set('sort_by', params.sort_by);
      if (params.order) qs.set('order', params.order);
      if (params.page) qs.set('page', params.page);
      if (params.page_size) qs.set('page_size', params.page_size);
      return this.call(() => Net.get('/api/movies?' + qs.toString()), () => window.MockSvc.movies(params));
    },
    movieDetail: function (movieid) {
      return this.call(() => Net.get('/api/movies/' + encodeURIComponent(movieid)), () => window.MockSvc.movieDetail(movieid));
    },

    /* ---------- 评分 ---------- */
    submitRatings: function (movieids, ratings) {
      return this.call(() => Net.post('/api/ratings/submit', { movieids, ratings }), () => window.MockSvc.submitRatings(movieids, ratings));
    },
    myRatings: function (params) {
      const qs = new URLSearchParams();
      if (params && params.page) qs.set('page', params.page);
      if (params && params.page_size) qs.set('page_size', params.page_size);
      return this.call(() => Net.get('/api/ratings/me?' + qs.toString()), () => window.MockSvc.myRatings(params || {}));
    },

    /* ---------- 收藏 ---------- */
    toggleFavorite: function (movieid, status) {
      return this.call(() => Net.post('/api/favorites/toggle', { movieid, status }), () => window.MockSvc.toggleFavorite(movieid, status));
    },
    myFavorites: function (params) {
      const qs = new URLSearchParams();
      if (params && params.status) qs.set('status', params.status);
      if (params && params.page) qs.set('page', params.page);
      if (params && params.page_size) qs.set('page_size', params.page_size);
      return this.call(() => Net.get('/api/favorites/me?' + qs.toString()), () => window.MockSvc.myFavorites(params || {}));
    },

    /* ---------- 推荐 ---------- */
    generateRecommend: function () {
      return this.call(() => Net.post('/api/recommend/generate', {}), () => window.MockSvc.generateRecommend());
    },
    recommendResult: function () {
      return this.call(() => Net.get('/api/recommend/result'), () => window.MockSvc.recommendResult());
    },
    recommendEvent: function (requestId, movieid, eventType) {
      const payload = { request_id: requestId, movieid, event_type: eventType };
      return this.call(() => Net.post('/api/recommend/event', payload), () => window.MockSvc.recommendEvent(payload));
    },

    /* ---------- 演示辅助（仅 Mock） ---------- */
    reviews: function (movieid) { return window.MockSvc.reviews(movieid); },
    similarMovies: function (movieid) { return window.MockSvc.similarMovies(movieid); },
    ratingCandidates: function (n) { return window.MockSvc.ratingCandidates(n); },
    topRated: function (n) { return window.MockSvc.topRated(n); },
    matchPercent: function (score) { return window.MockSvc.matchPercent(score); },
    favoriteStatus: function (movieid) {
      if (Net.mode === 'mock') return window.MockSvc.myFavoriteStatus(movieid);
      return null;
    }
  };

  window.Net = Net;
  window.Api = Api;
})();
