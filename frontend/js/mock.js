/* ============================================================
 * 智影 · Mock 服务层（演示模式）
 * 完整仿真 api_contract.md 中全部 16 个接口，
 * 数据来自 movierecommend.sql 真实电影数据（js/mock-data.js）
 * ============================================================ */
(function () {
  'use strict';

  const LATENCY = (window.APP_CONFIG.MOCK_LATENCY || [180, 460]);
  const delay = () => new Promise(r => setTimeout(r, LATENCY[0] + Math.random() * (LATENCY[1] - LATENCY[0])));
  const uid = () => 'mock-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);

  const LS = {
    get(key, dflt) { try { const v = localStorage.getItem('mrz_' + key); return v ? JSON.parse(v) : dflt; } catch (e) { return dflt; } },
    set(key, val) { try { localStorage.setItem('mrz_' + key, JSON.stringify(val)); } catch (e) { /* ignore */ } }
  };

  /* ---------- 内部数据 ---------- */
  const ALL_MOVIES = window.MOCK_MOVIES || [];

  const genreOf = function (m) {
    return window.UI.parseGenres(m.typelist);
  };

  const normalize = function (m) {
    return {
      movieid: m.movieid,
      moviename: m.moviename,
      name_zh: m.name_zh,
      tagline: m.tagline,
      releasetime: m.releasetime,
      director: m.director,
      leadactors: m.leadactors,
      picture: m.picture,
      averating: m.averating,
      numrating: m.numrating,
      description: m.description,
      typelist: m.typelist
    };
  };

  const listItem = function (m) {
    return {
      movieid: m.movieid,
      moviename: m.moviename,
      name_zh: m.name_zh,
      tagline: m.tagline,
      picture: m.picture,
      averating: m.averating,
      numrating: m.numrating,
      releasetime: m.releasetime,
      typelist: m.typelist
    };
  };

  /* ---------- 用户 ---------- */
  let users = LS.get('users', null);
  if (!users || !users.length) {
    users = [
      { userid: 1, username: 'hadoop', password: 'Movie1234', email: 'hadoop@example.com', phone: '13800138000', avatar: null },
      { userid: 2, username: 'film_fan', password: 'Movie1234', email: 'fan@example.com', phone: '13900139000', avatar: null }
    ];
    LS.set('users', users);
  }
  const saveUsers = () => LS.set('users', users);

  const publicUser = function (u) {
    return { userid: u.userid, username: u.username, email: u.email, phone: u.phone, avatar: u.avatar };
  };

  const findUserByAccount = function (account) {
    const a = String(account || '').trim().toLowerCase();
    if (!a) return null;
    return users.find(u => u.username.toLowerCase() === a || u.email.toLowerCase() === a || String(u.phone) === a) || null;
  };

  /* ---------- 评分 / 收藏 / 推荐 状态 ---------- */
  const ratingsOf = (userId) => LS.get('ratings', []).filter(r => r.userid === userId);
  const favoritesOf = (userId) => LS.get('favorites', []).filter(f => f.userid === userId && !f.deleted);
  const recsOf = (userId) => LS.get('recommendations', {});

  /* ---------- 影评（精选） ---------- */
  const REVIEWS = [
    {
      reviewid: 1, movieid: 109487, moviekey: 'interstellar',
      username: '光影流浪者', title: '这部跨越时代的科幻神作，看完久久不能平静',
      rating: 5, spoiler: false, likes: 2864, date: '2026-09-18',
      content: '诺兰把「爱」写进了物理公式。五维空间的父亲与书架后的女儿隔着引力对话，人类最柔软的情感成了唯一能穿越时空维度的存在。汉斯·季默的管风琴一响，鸡皮疙瘩就没下去过。'
    },
    {
      reviewid: 2, movieid: 446, moviekey: 'bawangbieji',
      username: '戏如人生', title: '不疯魔不成活——华语电影再也拍不出的绝唱',
      rating: 5, spoiler: false, likes: 2157, date: '2026-09-02',
      content: '张国荣的程蝶衣，是华语银幕上最蚀骨的悲剧。从“我本是男儿郎”到“我本是女娇娥”，一句话错了一辈子。时代更迭、戏台坍塌，蝶衣终以虞姬的方式死在了霸王怀里。'
    },
    {
      reviewid: 3, movieid: 318, moviekey: 'shawshank',
      username: '越过高墙的人', title: '有些鸟是关不住的，希望是唯一的自由',
      rating: 5, spoiler: true, likes: 1948, date: '2026-08-26',
      content: '二十年的凿壁，换来一场暴雨中的重生。安迪爬过五百码的污水管，在雨夜里张开双臂——那是电影史上最伟大的自由镜头。瑞德最后那句“I hope”，让多少人泪流满面。'
    },
    {
      reviewid: 4, movieid: 5618, moviekey: 'spirited',
      username: '千与千寻', title: '成长是一场不能回头的旅行',
      rating: 5, spoiler: false, likes: 1732, date: '2026-08-11',
      content: '白龙说“千万别回头”。长大就是这样，我们走出隧道，再也回不去那个夏天。宫崎骏把成人世界的贪婪、孤独与温柔，全画进了神明汤屋的一夜。'
    },
    {
      reviewid: 5, movieid: 2324, moviekey: 'lifebeautiful',
      username: 'Buongiorno', title: '他用一场游戏，守护了儿子的一生',
      rating: 5, spoiler: true, likes: 1506, date: '2026-07-30',
      content: '集中营的灰暗里，圭多把一切苦难都包装成积分游戏。清晨广播里的那句“早安，公主”，是黑暗岁月里最亮的光。直到最后枪声响起，孩子还以为自己赢了一辆坦克。'
    },
    {
      reviewid: 6, movieid: 79132, moviekey: 'inception',
      username: '陀螺还在转', title: '你分得清梦与现实的边界吗？',
      rating: 5, spoiler: true, likes: 1389, date: '2026-07-15',
      content: '层层梦境嵌套成一部烧脑神作。柯布最终回到孩子身边，而桌上的陀螺将倒未倒——诺兰把答案永远留给了观众。十年过去，我们仍在争论那个结尾。'
    }
  ];

  /* ---------- 电影查询引擎（仿真 /api/movies） ---------- */
  const queryMovies = function (params) {
    const q = (params.q || '').trim().toLowerCase();
    const categoryId = params.category_id ? Number(params.category_id) : null;
    const sortBy = params.sort_by || 'rating';
    const order = (params.order || 'desc') === 'asc' ? 1 : -1;
    const page = Math.max(1, Number(params.page || 1));
    const pageSize = Math.min(100, Math.max(1, Number(params.page_size || 20)));

    const GENRES = window.APP_CONFIG.GENRES;
    let list = ALL_MOVIES.slice();

    if (categoryId !== null && categoryId >= 1 && categoryId <= GENRES.length) {
      const gkey = GENRES[categoryId - 1].key;
      list = list.filter(m => genreOf(m).indexOf(gkey) >= 0);
    }
    if (q) {
      list = list.filter(m => {
        const hay = ((m.moviename || '') + ' ' + (m.name_zh || '') + ' ' + (m.director || '') + ' ' + (m.leadactors || '') + ' ' + (m.typelist || '')).toLowerCase();
        return hay.indexOf(q) >= 0;
      });
    }

    list.sort((a, b) => {
      if (sortBy === 'popularity') return ((a.numrating || 0) - (b.numrating || 0)) * order;
      if (sortBy === 'release_time') {
        const t = String(a.releasetime || '').localeCompare(String(b.releasetime || '')) * order;
        return t || ((b.numrating || 0) - (a.numrating || 0));
      }
      return ((a.averating || 0) - (b.averating || 0)) * order || ((b.numrating || 0) - (a.numrating || 0));
    });

    const total = list.length;
    const items = list.slice((page - 1) * pageSize, page * pageSize).map(listItem);
    return { items, total, page, page_size: pageSize };
  };

  /* ---------- 随机推荐生成（仿真 ALS 引擎） ---------- */
  const hashStr = function (s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return Math.abs(h);
  };

  const generateRecs = function (userId) {
    const myRatings = ratingsOf(userId);
    const ratedIds = myRatings.map(r => r.movieid);
    const likedGenres = {};
    myRatings.forEach(r => {
      const m = ALL_MOVIES.find(x => x.movieid === r.movieid);
      if (!m) return;
      const boost = (r.rating - 6) / 10; // 高分电影的类型偏好权重
      genreOf(m).forEach(g => { likedGenres[g] = (likedGenres[g] || 0) + Math.max(0, boost); });
    });

    const candidates = ALL_MOVIES.filter(m => ratedIds.indexOf(m.movieid) < 0).map(m => {
      const h = hashStr(userId + '#' + m.movieid) % 1000 / 1000;
      let score = (m.averating || 6) * 0.72 + h * 1.15;
      const gs = genreOf(m);
      let affinity = 0;
      gs.forEach(g => { affinity += (likedGenres[g] || 0); });
      score += Math.min(1.2, affinity * 1.4);
      return { movie: m, score };
    });

    candidates.sort((a, b) => b.score - a.score);
    const top = candidates.slice(0, 10).map((c, i) => ({
      movieid: c.movie.movieid,
      moviename: c.movie.moviename,
      name_zh: c.movie.name_zh,
      picture: c.movie.picture,
      position: i + 1,
      prediction_score: Math.round(Math.min(4.99, Math.max(3.2, c.score * 0.98)) * 100) / 100,
      score: c.score
    }));

    const requestId = 'req-' + userId + '-' + Date.now().toString(36);
    const recs = LS.get('recommendations', {});
    recs[userId] = { request_id: requestId, generated_at: new Date().toISOString(), items: top };
    LS.set('recommendations', recs);
    return recs[userId];
  };

  const matchPercent = function (score) {
    if (score === null || score === undefined || isNaN(Number(score))) return null;
    return Math.min(99, Math.max(70, Math.round(score * 20)));
  };

  /* ---------- 对外服务 ---------- */
  window.MockSvc = {
    /* GET / */
    health: async function () {
      await delay();
      return { message: '后端启动成功，数据库已连接！（演示模式）' };
    },

    /* 认证 */
    register: async function (payload) {
      await delay();
      const username = String(payload.username || '').trim();
      const password = String(payload.password || '');
      const email = String(payload.email || '').trim().toLowerCase();
      const phone = String(payload.phone || '').trim();
      if (username.length < 2 || username.length > 50) throw { status: 422, detail: '昵称长度需为 2–50 字符' };
      if (!/^(?=.*[A-Za-z])(?=.*\d).{8,255}$/.test(password)) throw { status: 422, detail: '密码至少 8 位，且必须包含英文字母和数字' };
      if (payload.confirm_password !== password) throw { status: 422, detail: '两次输入的密码不一致' };
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || email.length > 254) throw { status: 422, detail: '请输入有效的邮箱地址' };
      if (!/^\d{1,32}$/.test(phone)) throw { status: 422, detail: '手机号必须为 1–32 位数字' };
      if (findUserByAccount(username)) throw { status: 409, detail: '该昵称已被注册，请更换' };
      if (findUserByAccount(email)) throw { status: 409, detail: '该邮箱已被注册' };
      if (findUserByAccount(phone)) throw { status: 409, detail: '该手机号已被注册' };
      const nu = {
        userid: Math.max(0, ...users.map(u => u.userid)) + 1,
        username, password, email, phone,
        avatar: typeof payload.avatar === 'string' && payload.avatar ? payload.avatar : null
      };
      users.push(nu); saveUsers();
      return { code: 201, msg: '注册成功', userid: nu.userid };
    },

    login: async function (account, password) {
      await delay();
      const u = findUserByAccount(account);
      if (!u || u.password !== password) throw { status: 401, detail: '账号或密码错误' };
      return {
        code: 200, msg: '登录成功',
        access_token: 'mock.jwt.' + btoa(JSON.stringify({ sub: u.userid, exp: Date.now() + 7200000 })),
        token_type: 'bearer', userid: u.userid
      };
    },

    me: async function () {
      await delay();
      const u = users.find(x => x.userid === window.Net.currentUserId());
      if (!u) throw { status: 401, detail: '登录已失效，请重新登录' };
      return { code: 200, data: publicUser(u) };
    },

    updateMe: async function (payload) {
      await delay();
      const u = users.find(x => x.userid === window.Net.currentUserId());
      if (!u) throw { status: 401, detail: '登录已失效' };
      if (payload.username !== undefined) {
        if (payload.username === null) throw { status: 422, detail: '昵称不能为空' };
        const v = String(payload.username).trim();
        if (v.length < 2 || v.length > 50) throw { status: 422, detail: '昵称长度需为 2–50 字符' };
        const dup = findUserByAccount(v);
        if (dup && dup.userid !== u.userid) throw { status: 409, detail: '该昵称已被其他账号使用' };
        u.username = v;
      }
      if (payload.email !== undefined) {
        if (payload.email === null) throw { status: 422, detail: '邮箱不能为空' };
        const v = String(payload.email).trim().toLowerCase();
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) throw { status: 422, detail: '邮箱格式不正确' };
        const dup = findUserByAccount(v);
        if (dup && dup.userid !== u.userid) throw { status: 409, detail: '该邮箱已被其他账号使用' };
        u.email = v;
      }
      if (payload.phone !== undefined) {
        if (payload.phone === null) throw { status: 422, detail: '手机号不能为空' };
        const v = String(payload.phone).trim();
        if (!/^\d{1,32}$/.test(v)) throw { status: 422, detail: '手机号必须为 1–32 位数字' };
        const dup = findUserByAccount(v);
        if (dup && dup.userid !== u.userid) throw { status: 409, detail: '该手机号已被其他账号使用' };
        u.phone = v;
      }
      if (payload.avatar !== undefined) u.avatar = payload.avatar;
      saveUsers();
      return { code: 200, msg: '资料修改成功' };
    },

    changePassword: async function (oldPassword, newPassword) {
      await delay();
      const u = users.find(x => x.userid === window.Net.currentUserId());
      if (!u) throw { status: 401, detail: '登录已失效' };
      if (u.password !== oldPassword) throw { status: 400, detail: '原密码错误' };
      if (!/^(?=.*[A-Za-z])(?=.*\d).{8,255}$/.test(newPassword)) throw { status: 422, detail: '新密码至少 8 位，且必须包含英文字母和数字' };
      u.password = newPassword; saveUsers();
      return { code: 200, msg: '密码修改成功' };
    },

    /* 电影 */
    randomMovies: async function () {
      await delay();
      const pool = ALL_MOVIES.slice().sort((a, b) => Math.random() - 0.5);
      return { code: 200, data: pool.slice(0, 10).map(m => ({ movieid: m.movieid, moviename: m.moviename, name_zh: m.name_zh, picture: m.picture, averating: m.averating })) };
    },

    movies: async function (params) {
      await delay();
      return { code: 200, data: queryMovies(params || {}) };
    },

    movieDetail: async function (movieid) {
      await delay();
      const m = ALL_MOVIES.find(x => x.movieid === Number(movieid));
      if (!m) throw { status: 404, detail: '电影不存在或已删除' };
      return { code: 200, data: normalize(m) };
    },

    /* 评分 */
    submitRatings: async function (movieids, ratings) {
      await delay();
      if (!movieids.length || movieids.length !== ratings.length) throw { status: 422, detail: '评分数据不完整' };
      const uniq = new Set(movieids);
      if (uniq.size !== movieids.length) throw { status: 422, detail: '同一批次中电影不可重复' };
      movieids.forEach((id, i) => {
        if (!Number.isInteger(id) || id <= 0) throw { status: 422, detail: '电影 ID 必须为正整数' };
        const r = ratings[i];
        if (!Number.isInteger(r) || r < 1 || r > 10) throw { status: 422, detail: '评分必须为 1–10 的整数' };
        if (!ALL_MOVIES.find(x => x.movieid === id)) throw { status: 404, detail: { message: '电影不存在或已删除', movieids: [id] } };
      });
      const all = LS.get('ratings', []);
      const uid = window.Net.currentUserId();
      movieids.forEach((id, i) => {
        const idx = all.findIndex(r => r.userid === uid && r.movieid === id);
        const rec = { userid: uid, movieid: id, rating: ratings[i], rated_at: new Date().toISOString(), timestamp: String(Date.now()).slice(0, 10) };
        if (idx >= 0) all[idx] = rec; else all.push(rec);
      });
      LS.set('ratings', all);
      return { code: 200, msg: '评分提交成功', count: movieids.length };
    },

    myRatings: async function (params) {
      await delay();
      const page = Math.max(1, Number(params.page || 1));
      const pageSize = Math.min(100, Math.max(1, Number(params.page_size || 20)));
      const mine = ratingsOf(window.Net.currentUserId())
        .slice().sort((a, b) => String(b.rated_at).localeCompare(String(a.rated_at)));
      const items = mine.map(r => {
        const m = ALL_MOVIES.find(x => x.movieid === r.movieid);
        return {
          ratingid: r.userid + '-' + r.movieid, movieid: r.movieid,
          moviename: m ? m.moviename : null, name_zh: m ? m.name_zh : null,
          picture: m ? m.picture : null, rating: r.rating, rated_at: r.rated_at
        };
      });
      const total = items.length;
      return { code: 200, data: { items: items.slice((page - 1) * pageSize, page * pageSize), total, page, page_size: pageSize } };
    },

    /* 收藏 */
    toggleFavorite: async function (movieid, status) {
      await delay();
      if (!Number.isInteger(movieid) || movieid <= 0) throw { status: 422, detail: '电影 ID 必须为正整数' };
      if (['want_to_watch', 'watched'].indexOf(status) < 0) throw { status: 422, detail: '收藏状态不合法' };
      if (!ALL_MOVIES.find(x => x.movieid === movieid)) throw { status: 404, detail: '电影不存在或已删除' };
      const all = LS.get('favorites', []);
      const uid = window.Net.currentUserId();
      const idx = all.findIndex(f => f.userid === uid && f.movieid === movieid);
      if (idx < 0 || all[idx].deleted) {
        if (idx >= 0) { all[idx].deleted = false; all[idx].status = status; all[idx].updated_at = new Date().toISOString(); }
        else all.push({ userid: uid, movieid, status, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), deleted: false });
        LS.set('favorites', all);
        return { code: 200, msg: '收藏成功', action: idx >= 0 ? 'add' : 'add' };
      }
      if (all[idx].status === status) {
        all[idx].deleted = true; all[idx].updated_at = new Date().toISOString();
        LS.set('favorites', all);
        return { code: 200, msg: '已取消收藏', action: 'remove' };
      }
      all[idx].status = status; all[idx].updated_at = new Date().toISOString();
      LS.set('favorites', all);
      return { code: 200, msg: '收藏状态已更新', action: 'update' };
    },

    myFavorites: async function (params) {
      await delay();
      const page = Math.max(1, Number(params.page || 1));
      const pageSize = Math.min(100, Math.max(1, Number(params.page_size || 20)));
      let list = favoritesOf(window.Net.currentUserId());
      if (params.status && ['want_to_watch', 'watched'].indexOf(params.status) >= 0) list = list.filter(f => f.status === params.status);
      list = list.slice().sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
      const items = list.map(f => {
        const m = ALL_MOVIES.find(x => x.movieid === f.movieid);
        return {
          movieid: f.movieid, moviename: m ? m.moviename : null, name_zh: m ? m.name_zh : null,
          picture: m ? m.picture : null, averating: m ? m.averating : null,
          status: f.status, created_at: f.created_at, updated_at: f.updated_at
        };
      });
      const total = items.length;
      return { code: 200, data: { items: items.slice((page - 1) * pageSize, page * pageSize), total, page, page_size: pageSize } };
    },

    myFavoriteStatus: function (movieid) {
      const f = favoritesOf(window.Net.currentUserId()).find(x => x.movieid === movieid);
      return f ? f.status : null;
    },

    /* 推荐 */
    generateRecommend: async function () {
      await delay();
      const userId = window.Net.currentUserId();
      if (ratingsOf(userId).length === 0) throw { status: 400, detail: '您还没有任何评分记录，请先参与打分' };
      // 演示模式：直接完成 ALS 计算（前端以加载动效模拟耗时）
      generateRecs(userId);
      return { code: 202, msg: '推荐任务已生成', request_id: 'req-' + userId + '-' + Date.now().toString(36) };
    },

    recommendResult: async function () {
      await delay();
      const uid = window.Net.currentUserId();
      const recs = recsOf(uid);
      const bag = recs && recs[uid] ? recs[uid] : null;
      if (!bag) return { code: 200, request_id: null, items: [] };
      const items = bag.items.map(it => ({
        movieid: it.movieid, moviename: it.moviename, name_zh: it.name_zh,
        picture: it.picture, position: it.position, prediction_score: it.prediction_score
      }));
      return { code: 200, request_id: bag.request_id, items };
    },

    recommendEvent: async function (payload) {
      await delay();
      if (['impression', 'click', 'not_interested'].indexOf(payload.event_type) < 0) throw { status: 422, detail: '事件类型不合法' };
      return { code: 200, msg: '事件已记录' };
    },

    /* 评分分布（仿真） */
    ratingDistribution: function (movie) {
      const avg = (movie.averating || 7) / 2; // 5 星制均值
      const n = movie.numrating || 500;
      // 围绕均值构造近似正态的 5 星分布
      const weights = [1, 2, 3, 4, 5].map(s => Math.exp(-Math.pow(s - avg, 2) / 1.1));
      const sum = weights.reduce((a, b) => a + b, 0);
      return weights.map((w, i) => ({ star: 5 - i, pct: Math.round((w / sum) * 1000) / 10 }));
    },

    /* 影评 */
    reviews: async function (movieid) {
      await delay();
      let list = REVIEWS;
      if (movieid) list = list.filter(r => r.movieid === Number(movieid));
      return list.map(r => {
        const m = ALL_MOVIES.find(x => x.movieid === r.movieid);
        return Object.assign({}, r, { movie: m ? { movieid: m.movieid, moviename: m.moviename, name_zh: m.name_zh, picture: m.picture } : null });
      });
    },

    /* 相似电影（喜欢这部电影的人也喜欢） */
    similarMovies: async function (movieid) {
      await delay();
      const m = ALL_MOVIES.find(x => x.movieid === Number(movieid));
      if (!m) return [];
      const gs = genreOf(m);
      const scored = ALL_MOVIES.filter(x => x.movieid !== m.movieid).map(x => {
        const xg = genreOf(x);
        const overlap = gs.filter(g => xg.indexOf(g) >= 0).length;
        return { x, overlap };
      }).filter(o => o.overlap > 0)
        .sort((a, b) => (b.overlap - a.overlap) || ((b.x.averating || 0) - (a.x.averating || 0)) || ((b.x.numrating || 0) - (a.x.numrating || 0)));
      return scored.slice(0, 12).map(o => listItem(o.x));
    },

    /* 冷启动随机候选（评分页用） */
    ratingCandidates: async function (n) {
      await delay();
      const pool = ALL_MOVIES.slice().sort((a, b) => Math.random() - 0.5);
      return pool.slice(0, n || 10).map(listItem);
    },

    /* 口碑榜 */
    topRated: async function (n) {
      await delay();
      return ALL_MOVIES.slice().sort((a, b) => (b.averating || 0) - (a.averating || 0)).slice(0, n || 10).map(listItem);
    },

    /* 工具 */
    matchPercent,
    allMovies: ALL_MOVIES
  };
})();
