/* 冒烟测试：以最小 DOM 桩加载前端脚本，验证核心逻辑
 * 运行：node tests/smoke_test.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const base = path.join(__dirname, '..', 'js');

// ---- 环境桩 ----
const store = new Map();
const localStorage = {
  getItem: k => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: k => store.delete(k)
};
const documentStub = {
  addEventListener() {},
  getElementById() { return null; },
  querySelectorAll() { return []; }
};
const sandbox = {
  console,
  localStorage,
  document: documentStub,
  btoa: s => Buffer.from(s, 'binary').toString('base64'),
  atob: s => Buffer.from(s, 'base64').toString('binary'),
  setTimeout, clearTimeout, setInterval, clearInterval,
  URLSearchParams, AbortController, fetch: global.fetch,
  navigator: { clipboard: { writeText: async () => {} } },
  location: { hash: '', href: 'http://localhost/' }
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

function load(file) {
  const code = fs.readFileSync(path.join(base, file), 'utf8');
  vm.runInContext(code, sandbox, { filename: file });
}
load('config.js');
load('mock-data.js');
load('ui.js');
load('mock.js');
load('api.js');
load('app.js');

const assert = (cond, msg) => {
  if (!cond) { console.error('✗ FAIL:', msg); process.exitCode = 1; }
  else console.log('✓', msg);
};

(async () => {
  const UI = sandbox.UI, MockSvc = sandbox.MockSvc, Api = sandbox.Api, Net = sandbox.Net, CFG = sandbox.APP_CONFIG;

  assert(sandbox.MOCK_MOVIES.length >= 60, `Mock 电影数量 >= 60（实际 ${sandbox.MOCK_MOVIES.length}）`);
  assert(CFG.GENRES.length === 18, '18 大分类');

  // UI 工具
  const stars = UI.starsHtml(8.7);
  assert(stars.includes('star-fill'), '星级渲染含填充');
  const gens = UI.parseGenres('Sci-Fi,Drama,Action');
  assert(gens.join(',') === 'Sci-Fi,Drama,Action', '类型解析');
  assert(UI.fallbackSvg('肖申克').startsWith('data:image/svg+xml'), '兜底图生成');

  // 电影查询
  let r = await MockSvc.movies({ sort_by: 'rating', order: 'desc', page: 1, page_size: 5 });
  assert(r.data.items.length === 5 && r.data.total >= 60, '电影分页查询');
  const first = r.data.items[0];
  assert(first.averating >= r.data.items[4].averating, '评分降序排序');
  r = await MockSvc.movies({ category_id: 15, page: 1, page_size: 10 }); // Sci-Fi
  assert(r.data.items.every(m => UI.parseGenres(m.typelist).includes('Sci-Fi')), '分类筛选（科幻）');
  r = await MockSvc.movies({ q: 'shawshank' });
  assert(r.data.items.some(m => /shawshank/i.test(m.moviename)), '关键词搜索');

  // 注册 / 登录
  try { await MockSvc.register({ username: 'test_u1', password: 'Abc12345', confirm_password: 'Abc12345', email: 't1@example.com', phone: '13100000001' }); }
  catch (e) { assert(false, '注册失败: ' + e.detail); }
  assert(true, '新用户注册');
  let dup = false;
  try { await MockSvc.register({ username: 'test_u1', password: 'Abc12345', confirm_password: 'Abc12345', email: 't2@example.com', phone: '13100000002' }); }
  catch (e) { dup = e.status === 409; }
  assert(dup, '重复昵称 409');

  Net.mode = 'mock';
  Net.setToken('x'); Net.setCurrentUserId(3); Net.setCurrentUser({ userid: 3, username: 'test_u1' });
  const login = await Api.login('test_u1', 'Abc12345');
  assert(!!login.access_token, '登录返回 token');

  // 评分
  const ids = [318, 446, 109487];
  let sr = await Api.submitRatings(ids, [10, 8, 9]);
  assert(sr.count === 3, '批量评分 3 部');
  const my = await Api.myRatings({ page: 1, page_size: 10 });
  assert(my.data.total === 3, '我的评分列表 3 条');
  sr = await Api.submitRatings([318], [6]);
  const my2 = await Api.myRatings({ page: 1, page_size: 10 });
  const updated = my2.data.items.find(x => x.movieid === 318);
  assert(updated.rating === 6, '重复评分覆盖为 6 分');

  // 收藏
  let fav = await Api.toggleFavorite(318, 'want_to_watch');
  assert(fav.action === 'add', '收藏新增');
  fav = await Api.toggleFavorite(318, 'watched');
  assert(fav.action === 'update', '收藏状态更新');
  fav = await Api.toggleFavorite(318, 'watched');
  assert(fav.action === 'remove', '再次同状态取消收藏');
  const favs = await Api.myFavorites({ page: 1, page_size: 10 });
  assert(favs.data.total === 0, '取消后收藏列表为空');

  // 推荐
  await Api.generateRecommend();
  const rec = await Api.recommendResult();
  assert(rec.items.length === 10, '推荐结果 10 部');
  assert(rec.items[0].position === 1, '推荐位置从 1 开始');
  assert(!ids.includes(rec.items[0].movieid), '推荐不包含已评分电影');
  assert(Api.matchPercent(4.9) >= 90, '匹配度换算');

  // 影评 / 相似
  const reviews = await Api.reviews(109487);
  assert(reviews.length >= 1 && reviews[0].movie, '星际穿越影评');
  const sim = await Api.similarMovies(318);
  assert(sim.length > 0 && sim.every(m => m.movieid !== 318), '相似影片不包含自身');

  console.log(process.exitCode ? '\n有失败项' : '\n全部通过 ✔');
})();
