# 智影 · 大数据电影推荐系统（前端）

基于 **Spark ALS 协同过滤 + Node.js/FastAPI + MySQL** 的电影推荐系统前端页面。零依赖、纯静态，直接对接仓库 [ttteating/movierecommend](https://github.com/ttteating/movierecommend.git) 的 FastAPI 后端（`api_contract.md` 全部 16 个接口），内置来自 `movierecommend.sql` 真实电影数据的 Mock 演示模式，未启动后端也能完整演示全部业务流程。

## ✨ 功能一览

| 模块 | 功能 |
|---|---|
| 首页精选 | 65vh 巨幕轮播（缩略图联动 + 5s 自动轮播 + 渐晕遮罩）、18 大标准分类胶囊过滤、横向滑动海报轨（scroll-snap + 页码指示器 1/5 + 左右箭头）、一周口碑榜 Top 10（悬停海报预览）、热门影评精选 |
| 登录 / 注册 | 双栏品质卡片（左视觉拼贴墙 + 右表单区）、账号密码登录 / 新用户注册 Tab 平滑切换、密码显隐、协议提示、注册成功 🎉 动效卡片 + 3 秒自动跳转登录 |
| 电影详情 | 豆瓣式三栏布局（海报放大预览 / 导演·主演·类型·上映日期·ID 元数据 / 系统综合评分 + 五星星级 + 5星~1星分布条形图 + 好于 X% 同类型片）、想看/看过收藏胶囊、内嵌五星打分器（很差/较差/还行/推荐/力荐）、快速连评横滑条（批量数组提交）、剧情简介、相似影片、"写短评" |
| 个性打分（冷启动） | 随机 10 部电影五星打分、进度条、换一批、批量写入 personalratings、评分成功 🎉 面板 + ✨点击这里为您推荐电影 |
| 猜你喜欢（AI 推荐） | Spark 三步加载动效（读取评分 → ALS 矩阵分解 → Top 10 匹配）、Top 3 焦点横滑走廊（推荐指数/匹配度）、完整 Top 10 推荐矩阵（TOP 1-10 渐变排名勋章）、曝光/点击/不感兴趣事件上报、重新生成 |
| 个人中心 | 我的资料、修改密码、我的评分（可改分）、我的收藏（想看/已看/全部） |
| 搜索 | 顶部胶囊搜索 + 分类筛选、评分/热度/上映时间排序、分页 |
| 其他 | 头像徽章 + 欢迎您，{username}、所有海报 onerror 优雅降级占位、顶部毛玻璃顶栏滚动渐变、在线/演示双模式自动探测 |

## 📁 目录结构

```text
web/
├── index.html          # 页面骨架（侧边栏/顶栏/弹窗/抽屉/灯箱/Spark 动效层）
├── css/
│   └── style.css       # 全部样式（曜石黑 #0F1014 + 琥珀橙 #FF5C38 + 流光金 #F5C518）
├── js/
│   ├── config.js       # ★ 全局配置：后端地址、数据模式、18 大分类顺序
│   ├── mock-data.js    # 内置 Mock 数据：69 部经典电影（取自 movierecommend.sql 真实数据）
│   ├── ui.js           # UI 工具库（星级渲染、海报降级、Toast、横滑分页器等）
│   ├── mock.js         # Mock 服务层（完整仿真 16 个接口 + ALS 推荐仿真）
│   ├── api.js          # API 客户端（真实 FastAPI / Mock 双模式无缝切换）
│   └── app.js          # 主逻辑（路由、视图、轮播、评分、推荐全流程）
└── README.md
```

## 🚀 快速开始

### 方式一：纯静态演示（无需后端）

```bash
cd web
# Windows PowerShell
python -m http.server 8001
# 或使用任意静态服务器 / 直接双击 index.html
```

浏览器打开 `http://127.0.0.1:8001`。页面会自动检测后端不可达并进入**演示模式**，登录用内置账号：

- 账号 `hadoop` / 密码 `Movie1234`
- 账号 `film_fan` / 密码 `Movie1234`

（演示模式下注册的账号保存在浏览器 localStorage，评分/收藏/推荐结果均本地持久化。）

### 方式二：对接真实 FastAPI 后端

1. 确认后端已按 `api_contract.md` 启动（例如 `http://127.0.0.1:8000`），并允许跨域（`CORS_ORIGINS` 加入本前端地址，或前端与后端同源部署）。
2. 打开 `js/config.js`，确认 `API_BASE_URL` 为后端地址。`DATA_MODE: 'auto'` 会自动探测：后端可达走真实接口，不可达自动切 Mock；也可强制 `'real'` / `'mock'`。
3. 刷新页面，侧边栏底部引擎徽章显示「在线模式 · 已连接 API」即对接成功。

## ⚙️ 配置说明（js/config.js）

| 配置项 | 说明 |
|---|---|
| `API_BASE_URL` | FastAPI Base URL，部署时改成实际地址 |
| `DATA_MODE` | `auto`（默认，自动探测）/ `real`（强制真实接口）/ `mock`（强制演示） |
| `GENRES` | 标准 MovieLens 18 大分类数组。**真实模式下数组顺序即 `category_id`**（Action=1 … Western=18）。若数据库 `category` 表的 ID 顺序不同，调整数组顺序即可；当前后端没有分类枚举接口，此映射为前后端约定 |
| `HERO_INTERVAL` | 巨幕自动轮播间隔（默认 5s） |

## 🔌 接口对齐说明

前端严格按 `api_contract.md` 16 个方法/路径组合实现：

`GET /` · `POST /api/auth/register` · `POST /api/auth/login` · `GET /api/auth/me` · `PUT /api/auth/me` · `PUT /api/auth/me/password` · `GET /api/movies/random` · `GET /api/movies` · `GET /api/movies/{movieid}` · `POST /api/ratings/submit` · `GET /api/ratings/me` · `GET /api/favorites/me` · `POST /api/favorites/toggle` · `POST /api/recommend/generate` · `GET /api/recommend/result` · `POST /api/recommend/event`

要点：

- 认证使用 `Authorization: Bearer <JWT>`，Token 与用户信息保存在 localStorage，401 自动登出并弹登录框。
- **评分采用接口契约的 1–10 分制**；界面上的豆瓣式 5 星组件按 1 星 = 2 分映射（2/4/6/8/10 分 ↔ 很差/较差/还行/推荐/力荐），与数据库 `personalratings.rating`（CHECK 1–10）严格一致。
- `POST /api/recommend/generate` 当前固定返回 503（Celery/Spark 未配置）：前端会正常展示提示并保留已有推荐；后端配置好后无需改前端即可自动走通「生成 → 读取结果 → 曝光/点击/不感兴趣事件」闭环。
- 评论/影评接口尚未提供（契约 §9）：详情页与首页影评展示内置的编辑部精选内容，写短评为本地演示功能。

## 🧪 内置 Mock 说明

`js/mock-data.js` 中 69 部电影（海报图、评分、导演、主演、简介、类型）全部解析自仓库 `movierecommend.sql` 的真实 `movieinfo` 记录（如肖申克的救赎、霸王别姬、盗梦空间、星际穿越、大圣归来、魔戒、千与千寻、教父等），评分已按 10 分制换算，演示模式下的「猜你喜欢」按 类型亲和度 + 评分 的 ALS 风格打分生成确定性 Top 10。

核心逻辑附带冒烟测试（24 项断言，覆盖查询/排序/筛选/注册登录/评分/收藏/推荐/影评）：

```bash
node tests/smoke_test.js
```

## 🔗 部署到 GitHub 仓库

```bash
# 在仓库根目录（或任意合适位置）
git add web/          # 本前端目录
git commit -m "feat: 电影推荐系统前端页面（对接 FastAPI 接口契约）"
git push origin ttteating
```

纯静态文件无需构建；若需与后端同源，把 `web/` 内容作为静态目录挂载到 FastAPI（如 `app.mount("/", StaticFiles(directory="web", html=True))`），并把 `API_BASE_URL` 置空字符串以使用同源接口。

## 🛠 技术栈

HTML5 · 现代 CSS3（CSS 变量、Scroll Snap、backdrop-filter、aspect-ratio）· 原生 ES6 JavaScript（零依赖、无构建、无第三方库）

## 📝 设计规范落实

- 曜石黑 `#0F1014` / 炭灰 `#181920` 主背景 + 流光金 `#F5C518` / 琥珀橙 `#FF5C38` 强调色
- 海报容器严格 2:3，`object-fit: cover` + `border-radius: 8px` + 悬停 `scale(1.04)` 与暗角遮罩
- 字体栈 `-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif`
- 左侧 200px 固定导航（选中项橙红指示条）+ 顶部 68px 毛玻璃顶栏（滚动时 `rgba(15,16,20,0.88) + blur(12px)`）
- 无蓝紫渐变、无霓虹描边、无默认下拉框/表格——全部为自绘组件
