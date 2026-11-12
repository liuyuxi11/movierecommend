/* ============================================================
 * 智影 · API 客户端层
 * 严格对齐 backend/app/api/api_contract.md（53 个操作中前端用到的全部接口）
 * 支持 真实 FastAPI / 内置 Mock 双模式无缝切换
 * 内置 access_token 过期自动用 refresh_token 续期并重试
 * ============================================================ */
(function () {
  'use strict';

  const CFG = window.APP_CONFIG;

  /* ---------- 基础网络 ---------- */
  const Net = {
    _token: null,
    _refreshToken: null,
    mode: 'mock',        // 'real' | 'mock'
    probing: false,

    baseUrl() { return CFG.API_BASE_URL.replace(/\/+$/, ''); },

    token() { return this._token || localStorage.getItem('mrz_token') || null; },
    setToken(t) {
      this._token = t;
      if (t) localStorage.setItem('mrz_token', t);
      else localStorage.removeItem('mrz_token');
    },
    refreshToken() { return this._refreshToken || localStorage.getItem('mrz_refresh_token') || null; },
    setRefreshToken(t) {
      this._refreshToken = t;
      if (t) localStorage.setItem('mrz_refresh_token', t);
      else localStorage.removeItem('mrz_refresh_token');
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

    /* 清空本地会话（退出/失效） */
    clearSession() {
      this.setToken(null);
      this.setRefreshToken(null);
      this.setCurrentUser(null);
      this.setCurrentUserId(0);
    },

    /* 请求基元：401 时用 refresh_token 续期并重试一次 */
    async raw(path, opts, allowRefresh) {
      opts = opts || {};
      const headers = Object.assign({}, opts.headers || {});
      if (opts.body && typeof opts.body !== 'string') {
        headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(opts.body);
      }
      if (this.token()) headers['Authorization'] = 'Bearer ' + this.token();

      const url = this.baseUrl() + path;
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
        /* access_token 过期 → 尝试刷新令牌并重试一次 */
        if (res.status === 401 && allowRefresh !== false && this.refreshToken() && this.token()) {
          const refreshed = await this.tryRefresh();
          if (refreshed) return this.raw(path, opts, false);
        }
        const err = new Error('HTTP ' + res.status);
        err.status = res.status;
        err.data = data;
        err.detail = extractDetail(data, res.status);
        if (res.status === 401 && this.token()) err.sessionExpired = true;
        throw err;
      }
      return data;
    },

    /* 刷新令牌（POST /api/auth/refresh） */
    async tryRefresh() {
      try {
        const res = await fetch(this.baseUrl() + '/api/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: this.refreshToken() })
        });
        if (!res.ok) return false;
        const d = await res.json();
        const tokens = d && d.data ? d.data : d;
        if (tokens && tokens.access_token) {
          this.setToken(tokens.access_token);
          if (tokens.refresh_token) this.setRefreshToken(tokens.refresh_token);
          return true;
        }
        return false;
      } catch (e) {
        return false;
      }
    },

    get(path) { return this.raw(path); },
    post(path, body) { return this.raw(path, { method: 'POST', body }); },
    put(path, body) { return this.raw(path, { method: 'PUT', body }); },
    del(path) { return this.raw(path, { method: 'DELETE' }); },

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
        const res = await fetch(this.baseUrl() + '/', { signal: ctrl.signal });
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
    if (err.network) { err.friendly = true; err.detail = '无法连接后端服务'; return err; }
    switch (err.status) {
      case 400: err.detail = err.detail || '业务操作失败（原密码错误等）'; break;
      case 401: err.detail = err.detail || '登录凭据错误，或登录已过期'; break;
      case 403: err.detail = err.detail || '无权访问：请求中的 userid 与当前登录用户不一致'; break;
      case 404: err.detail = err.detail || '资源不存在或已删除'; break;
      case 409: err.detail = err.detail || '资料冲突或并发冲突'; break;
      case 413: err.detail = err.detail || '头像文件超过 5 MiB 限制'; break;
      case 415: err.detail = err.detail || '头像文件类型不支持'; break;
      case 422: err.detail = err.detail || '请求参数未通过校验'; break;
      case 429: err.detail = err.detail || '操作过于频繁，请稍后再试'; break;
      case 502: err.detail = err.detail || '邮件发送失败，请检查 SMTP 配置'; break;
      case 503: err.detail = err.detail || '相关服务尚未配置或不可用（Redis/Celery/SMTP）'; break;
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
          if (err && err.sessionExpired && Net.isLoggedIn()) {
            Net.clearSession();
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

    /* ---------- 认证与账号 ---------- */
    register: function (payload) {
      return this.call(() => Net.post('/api/auth/register', payload), () => window.MockSvc.register(payload));
    },
    login: function (account, password) {
      return this.call(() => Net.post('/api/auth/login', { account, password }), () => window.MockSvc.login(account, password));
    },
    refresh: function () {
      return this.call(() => Net.post('/api/auth/refresh', { refresh_token: Net.refreshToken() }), () => window.MockSvc.refresh());
    },
    logout: function () {
      return this.call(() => Net.post('/api/auth/logout', {}), () => window.MockSvc.logout());
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
    forgotPasswordRequest: function (email) {
      return this.call(() => Net.post('/api/auth/forgot-password/request', { email }), () => window.MockSvc.forgotPasswordRequest(email));
    },
    forgotPasswordConfirm: function (email, code, newPassword) {
      return this.call(() => Net.post('/api/auth/forgot-password/confirm', { email, code, new_password: newPassword }),
        () => window.MockSvc.forgotPasswordConfirm(email, code, newPassword));
    },

    /* ---------- 电影与分类 ---------- */
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
    /* 分类列表：真实接口 GET /api/movies/categories；演示模式用内置 18 类 */
    categories: function () {
      return this.call(() => Net.get('/api/movies/categories'), () => window.MockSvc.categories());
    },

    /* ---------- 评分（1-5 分制） ---------- */
    submitRatings: function (movieids, ratings) {
      return this.call(() => Net.post('/api/ratings/submit', { movieids, ratings }), () => window.MockSvc.submitRatings(movieids, ratings))
        .then(result => {
          if (Net.mode === 'real' && result && result.recommendation_request_id) {
            sessionStorage.setItem('recommendation_refresh_request_id', result.recommendation_request_id);
          }
          return result;
        });
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

    /* ---------- 评论 ---------- */
    comments: function (movieid, params) {
      const qs = new URLSearchParams();
      if (params && params.page) qs.set('page', params.page);
      if (params && params.page_size) qs.set('page_size', params.page_size);
      return this.call(() => Net.get('/api/comments/movies/' + encodeURIComponent(movieid) + '/comments?' + qs.toString()),
        () => window.MockSvc.comments(movieid, params || {}));
    },
    postComment: function (movieid, content) {
      return this.call(() => Net.post('/api/comments', { movieid, content }), () => window.MockSvc.postComment(movieid, content));
    },
    deleteComment: function (commentid) {
      return this.call(() => Net.del('/api/comments/' + encodeURIComponent(commentid)), () => window.MockSvc.deleteComment(commentid));
    },
    toggleCommentLike: function (commentid) {
      return this.call(() => Net.post('/api/comments/' + encodeURIComponent(commentid) + '/like', {}), () => window.MockSvc.toggleCommentLike(commentid));
    },
    reportComment: function (commentid, payload) {
      return this.call(() => Net.post('/api/comments/' + encodeURIComponent(commentid) + '/reports', payload), () => window.MockSvc.reportComment(commentid, payload));
    },

    /* ---------- 推荐 ---------- */
    generateRecommend: function () {
      return this.call(() => Net.post('/api/recommend/generate', {}), () => window.MockSvc.generateRecommend());
    },
    recommendResult: function () {
      return this.call(() => Net.get('/api/recommend/result'), () => window.MockSvc.recommendResult());
    },
    recommendTask: function (taskId) {
      return this.call(() => Net.get('/api/recommend/task/' + encodeURIComponent(taskId)), () => window.MockSvc.recommendTask(taskId));
    },
    similarMovies: function (movieid, limit) {
      const qs = 'limit=' + (limit || 12);
      return this.call(
        async () => {
          const res = await Net.get('/api/recommend/similar/' + encodeURIComponent(movieid) + '?' + qs);
          return (res && res.data) || [];
        },
        () => window.MockSvc.similarMovies(movieid)
      );
    },
    recommendEvent: function (requestId, movieid, eventType) {
      const payload = { request_id: requestId, movieid, event_type: eventType };
      return this.call(() => Net.post('/api/recommend/event', payload), () => window.MockSvc.recommendEvent(payload));
    },

    /* ---------- 演示辅助（仅 Mock / 内置内容） ---------- */
    reviews: function (movieid) { return window.MockSvc.reviews(movieid); },
    ratingCandidates: function (n) { return window.MockSvc.ratingCandidates(n); },
    topRated: function (n) { return window.MockSvc.topRated(n); },
    favoriteStatus: function (movieid) {
      if (Net.mode === 'mock') return window.MockSvc.myFavoriteStatus(movieid);
      return null;
    }
  };

  window.Net = Net;
  window.Api = Api;
})();
