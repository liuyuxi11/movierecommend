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
const sessionStorage = localStorage;
const documentStub = {
  addEventListener() {},
  getElementById() { return null; },
  querySelectorAll() { return []; }
};
const sandbox = {
  console,
  localStorage,
  sessionStorage,
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
  assert(sandbox.MOCK_MOVIES.every(m => m.averating == null || m.averating <= 5), 'Mock 评分为 0-5 分制');

  // UI 工具
  const stars = UI.starsHtml(4.4);
  assert(stars.includes('star-fill'), '星级渲染含填充（5 分制）');
  const gens = UI.parseGenres('Sci-Fi,Drama,Action');
  assert(gens.join(',') === 'Sci-Fi,Drama,Action', '类型解析');
  assert(UI.fallbackSvg('肖申克').startsWith('data:image/svg+xml'), '兜底图生成');

  // 电影查询
  let r = await MockSvc.movies({ sort_by: 'rating', order: 'desc', page: 1, page_size: 5 });
  assert(r.data.items.length === 5 && r.data.total >= 60, '电影分页查询');
  const first = r.data.items[0];
  assert(first.averating >= r.data.items[4].averating, '评分降序排序');
  r = await MockSvc.movies({ category_id: 12, page: 1, page_size: 10 }); // Science Fiction（真实库 id=12）
  assert(r.data.items.every(m => UI.parseGenres(m.typelist).includes('Sci-Fi')), '分类筛选（科幻 id=12）');
  r = await MockSvc.movies({ q: 'shawshank' });
  assert(r.data.items.some(m => /shawshank/i.test(m.moviename)), '关键词搜索');

  // 分类接口（镜像真实库 22 类）
  const cats = await Api.categories();
  assert(cats.data.length === 22 && cats.data[0].categoryid === 1, '分类列表 22 项（真实库镜像）');
  assert(cats.data.some(c => c.categoryid === 12 && c.name === 'Science Fiction'), 'Science Fiction 分类 id=12');

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
  assert(!!login.access_token, '登录返回 access_token');
  assert(!!login.refresh_token && login.expires_in === 900 && login.refresh_expires_in === 604800, '登录返回 refresh_token 及有效期');
  const refreshed = await Api.refresh();
  assert(!!refreshed.data.access_token && !!refreshed.data.refresh_token, '刷新令牌返回新令牌对');

  // 忘记密码（演示模式验证码 123456）
  const fgr = await MockSvc.forgotPasswordRequest('t1@example.com');
  assert(fgr.code === 200, '申请重置验证码');
  await MockSvc.forgotPasswordConfirm('t1@example.com', '123456', 'Abcd1234');
  const relogin = await Api.login('test_u1', 'Abcd1234');
  assert(!!relogin.access_token, '重置密码后可用新密码登录');
  await MockSvc.forgotPasswordConfirm('t1@example.com', '123456', 'Abc12345'); // 恢复原密码

  // 评分（1-5 分制，超范围拒绝）
  let rejected = false;
  try { await MockSvc.submitRatings([318], [6]); } catch (e) { rejected = e.status === 422; }
  assert(rejected, '评分 >5 被拒绝（1-5 分制）');
  const ids = [318, 446, 109487];
  let sr = await Api.submitRatings(ids, [5, 4, 3]);
  assert(sr.count === 3, '批量评分 3 部');
  assert(sr.recommendation_refresh_queued === true && !!sr.recommendation_request_id, '评分后返回推荐刷新请求 ID');
  const my = await Api.myRatings({ page: 1, page_size: 10 });
  assert(my.data.total === 3, '我的评分列表 3 条');
  sr = await Api.submitRatings([318], [4]);
  const my2 = await Api.myRatings({ page: 1, page_size: 10 });
  const updated = my2.data.items.find(x => x.movieid === 318);
  assert(updated.rating === 4, '重复评分覆盖为 4 分');

  // 收藏
  let fav = await Api.toggleFavorite(318, 'want_to_watch');
  assert(fav.action === 'add', '收藏新增');
  fav = await Api.toggleFavorite(318, 'watched');
  assert(fav.action === 'update', '收藏状态更新');
  fav = await Api.toggleFavorite(318, 'watched');
  assert(fav.action === 'remove', '再次同状态取消收藏');
  const favs = await Api.myFavorites({ page: 1, page_size: 10 });
  assert(favs.data.total === 0, '取消后收藏列表为空');

  // 评论
  const posted = await Api.postComment(109487, '测试评论：诺兰的时空诗篇');
  assert(posted.code === 201 && posted.data.commentid > 0, '发布评论 201');
  const cl = await Api.comments(109487, { page: 1, page_size: 20 });
  assert(cl.data.total >= 2 && cl.data.items[0].commentid === posted.data.commentid, '评论列表包含新评论（按时间倒序）');
  const liked = await Api.toggleCommentLike(posted.data.commentid);
  assert(liked.data.liked === true, '点赞评论');
  const unliked = await Api.toggleCommentLike(posted.data.commentid);
  assert(unliked.data.liked === false, '取消点赞');
  const rep = await Api.reportComment(1, { reason_code: 'advertisement' });
  assert(rep.code === 201, '举报评论');
  let dupReport = false;
  try { await Api.reportComment(1, { reason_code: 'advertisement' }); } catch (e) { dupReport = e.status === 409; }
  assert(dupReport, '重复举报 409');
  const del = await Api.deleteComment(posted.data.commentid);
  assert(del.code === 200, '删除自己的评论');
  const cl2 = await Api.comments(109487, { page: 1, page_size: 20 });
  assert(!cl2.data.items.some(c => c.commentid === posted.data.commentid), '删除后列表不再包含该评论');

  // 推荐
  const gen = await Api.generateRecommend();
  assert(gen.code === 202 && !!gen.request_id && !!gen.task_id, '生成推荐返回 202 + request_id + task_id');
  const task = await Api.recommendTask(gen.task_id);
  assert(task.state === 'SUCCESS', '任务状态查询 SUCCESS');
  const rec = await Api.recommendResult();
  assert(rec.items.length === 20, '推荐结果 Top-20');
  assert(rec.items[0].position === 1, '推荐位置从 1 开始');
  assert(!ids.includes(rec.items[0].movieid), '推荐不包含已评分电影');
  assert(rec.items.every(item => item.prediction_score == null || (item.prediction_score >= 0 && item.prediction_score <= 1)), '排序分位于 0-1');
  assert(rec.items.every(item => ['als_rerank', 'popular_fallback', 'legacy'].includes(item.recommendation_source)), '推荐来源字段合法');

  // 影评（编辑部精选）/ 相似 / 详情含分类
  const reviews = await Api.reviews(109487);
  assert(reviews.length >= 1 && reviews[0].movie, '星际穿越影评');
  const sim = await Api.similarMovies(318);
  assert(sim.length > 0 && sim.every(m => m.movieid !== 318), '相似影片不包含自身');
  const detail = await Api.movieDetail(318);
  assert(Array.isArray(detail.data.categories) && detail.data.categories.length > 0, '电影详情含分类关联');

  // 退出登录
  const lg = await Api.logout();
  assert(lg.code === 200, '退出登录');

  console.log(process.exitCode ? '\n有失败项' : '\n全部通过 ✔');
})();
