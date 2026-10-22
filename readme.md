# 电影推荐系统

这是一个前后端分离的电影推荐系统项目。当前仓库包含 FastAPI 后端、静态前端演示页面、Tortoise ORM 数据模型、MySQL 迁移脚本、原始数据集和数据库导出文件。

## 当前实现

- 后端：Python、FastAPI、Tortoise ORM、MySQL（`asyncmy`）和 JWT 认证。
- 前端：`frontend/` 下的静态 HTML、CSS 和原生 JavaScript，无 Node.js、npm 或构建步骤。
- 推荐接口：`POST /api/recommend/generate` 当前按接口约定返回 `503`，推荐任务服务尚未接入。
- 数据分析：`backend/app/analytics.py` 提供评分、评论、收藏和推荐事件聚合查询。

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用入口
│   │   ├── database.py          # 数据库初始化和关闭
│   │   ├── models.py            # Tortoise ORM 模型
│   │   ├── schemas.py           # Pydantic 请求模型和校验
│   │   ├── auth.py              # JWT 和密码哈希
│   │   ├── analytics.py         # 聚合分析查询
│   │   └── api/                 # 用户、电影、评分、收藏、推荐路由
│   ├── migrations/              # SQL 和 Aerich 迁移文件
│   └── pyproject.toml           # Aerich/Tortoise 配置
├── frontend/
│   ├── index.html               # 前端页面入口
│   ├── css/style.css            # 页面样式
│   ├── js/app.js                # 页面和业务交互
│   ├── js/api.js                # 后端 API 客户端
│   ├── js/config.js             # API 地址和演示模式配置
│   ├── js/mock.js               # Mock API 实现
│   └── tests/smoke_test.js      # 前端冒烟测试脚本
├── data/raw/                    # 原始电影和评分数据
├── database/dumps/              # MySQL 数据库导出文件
├── docs/                        # 数据库文档和需求分析文档
├── requirements.txt             # Python 依赖
├── .env.example                 # 环境变量模板
└── .env                         # 本地环境变量，不提交到 Git
```

## 环境要求

- Windows PowerShell 或 CMD
- Python 3.12+
- MySQL 8.x，且已创建 `movierecommend` 数据库
- 已安装并可访问的 Python 虚拟环境

## 配置环境变量

复制 `.env.example` 为根目录 `.env`，并填写数据库地址和 JWT 密钥：

```env
DATABASE_URL=mysql://root:123456@localhost:3306/movierecommend
SECRET_KEY=请替换为随机且足够长的密钥
CORS_ORIGINS=http://127.0.0.1:8001,http://localhost:8001
```

`SECRET_KEY` 用于 JWT 签名，生产环境必须使用随机值。`.env` 已被 Git 忽略，不应提交真实密钥。

## 安装后端依赖

在项目根目录执行。已有 `.venv_new` 时可直接跳过创建步骤。

PowerShell：

```powershell
python -m venv .venv_new
.\.venv_new\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

CMD：

```cmd
python -m venv .venv_new
.venv_new\Scripts\activate.bat
python -m pip install -r requirements.txt
```

## 启动后端

从项目根目录启动，`--app-dir backend` 用于让 Python 找到 `backend/app` 包：

```powershell
.\.venv_new\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

如果已经激活虚拟环境，也可以执行：

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

启动成功后访问：

- 服务首页：http://127.0.0.1:8000/
- Swagger 文档：http://127.0.0.1:8000/docs
- OpenAPI JSON：http://127.0.0.1:8000/openapi.json

启动阶段会连接 `DATABASE_URL` 指定的 MySQL。若出现数据库连接错误，请先确认 MySQL 服务、数据库名称、用户名和密码。

## 启动前端

前端是静态文件，不需要 npm。另开一个终端，在项目根目录执行：

```powershell
python -m http.server 8001 --directory frontend
```

浏览器访问 http://127.0.0.1:8001/。

前端 API 地址和数据模式在 `frontend/js/config.js` 中配置：

- `API_BASE_URL`：后端地址，真实接口模式使用 `http://127.0.0.1:8000`。
- `DATA_MODE`：`auto` 自动探测后端，或显式设置为 `real`、`mock`。

前端运行在 8001 端口时，`.env` 中的 `CORS_ORIGINS` 应包含 `http://127.0.0.1:8001` 和 `http://localhost:8001`。

## API 概览

接口详细请求体、认证方式和响应结构见 [backend/app/api/api_contract.md](backend/app/api/api_contract.md)。

- 认证：`POST /api/auth/register`、`POST /api/auth/login`、`GET/PUT /api/auth/me`、`PUT /api/auth/me/password`
- 电影：`GET /api/movies/random`、`GET /api/movies`、`GET /api/movies/{movieid}`
- 评分：`POST /api/ratings/submit`、`GET /api/ratings/me`
- 收藏：`GET /api/favorites/me`、`POST /api/favorites/toggle`
- 推荐：`POST /api/recommend/generate`、`GET /api/recommend/result`、`POST /api/recommend/event`

除注册接口外，受保护接口需要添加请求头：

```text
Authorization: Bearer <access_token>
```

## 数据库迁移

业务升级 SQL 位于 `backend/migrations/0001_schema_upgrade.sql`，执行前请备份数据库并确认目标库。Aerich 配置位于 `backend/pyproject.toml`；执行 Aerich 命令时建议将工作目录切换到 `backend/`，以使用相对迁移路径。

## 停止服务

在运行后端或前端服务的终端按 `Ctrl+C`。退出虚拟环境执行：

```powershell
deactivate
```
