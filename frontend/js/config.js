/* ============================================================
 * 智影 · 大数据电影推荐系统 —— 全局配置
 * 修改本文件即可完成与真实后端的对接配置
 * ============================================================ */
window.APP_CONFIG = {
  /* FastAPI 后端地址（Base URL），部署时改为实际地址 */
  API_BASE_URL: 'http://127.0.0.1:8000',

  /* 数据模式：
   *   'auto'  —— 自动探测：后端可达则走真实接口，不可达自动切换内置 Mock（默认，推荐）
   *   'real'  —— 强制真实接口
   *   'mock'  —— 强制演示模式（不请求后端）
   */
  DATA_MODE: 'auto',

  /* 探测后端健康检查的超时时间（毫秒） */
  PROBE_TIMEOUT: 2500,

  /* 演示模式下模拟的网络延迟区间（毫秒） */
  MOCK_LATENCY: [180, 460],

  /* 标准 MovieLens 18 大电影分类（顺序即真实后端的 category_id 顺序，
   * 若数据库 categoryid 顺序不同，请调整本数组顺序） */
  GENRES: [
    { key: 'Action',        cn: '动作',      en: 'Action' },
    { key: 'Adventure',     cn: '冒险',      en: 'Adventure' },
    { key: 'Animation',     cn: '动画',      en: 'Animation' },
    { key: "Children's",    cn: '儿童',      en: "Children's" },
    { key: 'Comedy',        cn: '喜剧',      en: 'Comedy' },
    { key: 'Crime',         cn: '犯罪',      en: 'Crime' },
    { key: 'Documentary',   cn: '纪录片',    en: 'Documentary' },
    { key: 'Drama',         cn: '剧情',      en: 'Drama' },
    { key: 'Fantasy',       cn: '奇幻',      en: 'Fantasy' },
    { key: 'Film-Noir',     cn: '黑色电影',  en: 'Film-Noir' },
    { key: 'Horror',        cn: '恐怖',      en: 'Horror' },
    { key: 'Musical',       cn: '音乐/歌舞', en: 'Musical' },
    { key: 'Mystery',       cn: '悬疑',      en: 'Mystery' },
    { key: 'Romance',       cn: '爱情',      en: 'Romance' },
    { key: 'Sci-Fi',        cn: '科幻',      en: 'Sci-Fi' },
    { key: 'Thriller',      cn: '惊悚',      en: 'Thriller' },
    { key: 'War',           cn: '战争',      en: 'War' },
    { key: 'Western',       cn: '西部',      en: 'Western' }
  ],

  /* 首页巨幕轮播自动切换间隔（毫秒） */
  HERO_INTERVAL: 5000,

  /* 每屏海报数量基准（横滑轨道） */
  RAIL_PER_PAGE: 6
};

/* 类型别名 → 标准 18 分类（用于 typelist 归一化） */
window.GENRE_ALIASES = {
  'Science Fiction': 'Sci-Fi',
  'SciFi': 'Sci-Fi',
  'Childrens': "Children's",
  'Children': "Children's",
  'Film Noir': 'Film-Noir',
  'FilmNoir': 'Film-Noir',
  'Music': 'Musical'
};

/* ============================================================
 * 真实数据库（movierecommend_test.sql 导出）中的分类表内容
 * categoryid 1-22；演示模式（Mock）直接镜像这 22 个分类
 * ============================================================ */
window.REAL_CATEGORIES = [
  { categoryid: 1, name: 'Animation' },
  { categoryid: 2, name: 'Comedy' },
  { categoryid: 3, name: 'Family' },
  { categoryid: 4, name: 'Adventure' },
  { categoryid: 5, name: 'Fantasy' },
  { categoryid: 6, name: 'Romance' },
  { categoryid: 7, name: 'Drama' },
  { categoryid: 8, name: 'Action' },
  { categoryid: 9, name: 'Crime' },
  { categoryid: 10, name: 'Thriller' },
  { categoryid: 11, name: 'Horror' },
  { categoryid: 12, name: 'Science Fiction' },
  { categoryid: 13, name: 'Mystery' },
  { categoryid: 14, name: 'History' },
  { categoryid: 15, name: 'War' },
  { categoryid: 16, name: 'Foreign' },
  { categoryid: 17, name: 'Music' },
  { categoryid: 18, name: 'Documentary' },
  { categoryid: 19, name: 'Western' },
  { categoryid: 20, name: 'TV Movie' },
  { categoryid: 21, name: 'Neo-noir' },
  { categoryid: 22, name: 'Indie' }
];

/* typelist 常见写法 → 真实分类名（用于演示模式映射与兜底） */
window.GENRE_TO_REAL = {
  'Animation': 'Animation', 'Comedy': 'Comedy', 'Family': 'Family',
  'Adventure': 'Adventure', 'Fantasy': 'Fantasy', 'Romance': 'Romance',
  'Drama': 'Drama', 'Action': 'Action', 'Crime': 'Crime',
  'Thriller': 'Thriller', 'Horror': 'Horror',
  'Science Fiction': 'Science Fiction', 'Sci-Fi': 'Science Fiction', 'SciFi': 'Science Fiction',
  'Mystery': 'Mystery', 'History': 'History', 'War': 'War',
  'Foreign': 'Foreign', 'Music': 'Music', 'Musical': 'Music',
  'Documentary': 'Documentary', 'Western': 'Western',
  'TV Movie': 'TV Movie', 'TVMovie': 'TV Movie',
  'Neo-noir': 'Neo-noir', 'Film-Noir': 'Neo-noir', 'FilmNoir': 'Neo-noir', 'Noir': 'Neo-noir',
  'Indie': 'Indie',
  "Children's": 'Family', 'Childrens': 'Family', 'Children': 'Family'
};
