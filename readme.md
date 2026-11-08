# 电影推荐系统

这是一个前后端分离的电影推荐系统项目。当前仓库包含 FastAPI 后端、静态前端演示页面、Tortoise ORM 数据模型、MySQL 迁移脚本、原始数据集和数据库导出文件。

## 当前实现

- 后端：Python、FastAPI、Tortoise ORM、MySQL（`asyncmy`）和 JWT 认证。
- 前端：`frontend/` 下的静态 HTML、CSS 和原生 JavaScript，无 Node.js、npm 或构建步骤。

## 功能概述

- **注册、登录与令牌**：用户可以通过 JSON 注册，也可以使用单独的头像注册接口上传图片；登录支持用户名、手机号或邮箱。密码以哈希形式保存。认证接口提供访问令牌签发、刷新和退出登录；退出或账号状态变化后，旧令牌可按后端的令牌校验逻辑失效。忘记密码时，用户可申请邮箱验证码，并提交验证码和新密码完成重置。
- **个人资料与密码**：登录用户可以查看自己的账号资料，更新可编辑的个人信息和头像，并通过验证旧密码修改密码。个人接口以当前登录身份为操作对象，不能通过请求参数指定其他用户。
- **电影查询**：未登录用户可获取随机电影、分页浏览电影列表、按电影名称搜索、按分类筛选，并选择支持的排序方式；电影详情接口返回电影信息及关联分类。分类列表也可公开查询。
- **电影与分类维护**：管理员可以新增、编辑和软删除电影，维护电影基础信息及分类关联；也可以新增、编辑和软删除分类。管理写操作需要管理员身份，普通管理员与超级管理员的权限按接口依赖控制。
- **评分**：登录用户可以批量提交多部电影的评分，也可以分页查看自己的评分。对同一部电影再次提交时，接口用于更新该用户已有的评分。
- **收藏**：登录用户可以分页查看自己的收藏，并通过切换接口添加收藏、改变“想看/看过”等状态或取消收藏。取消后的记录按后端软删除逻辑处理，重复操作可根据现有记录恢复或更新收藏状态。
- **评论、点赞与举报**：用户可查看电影评论、发布评论、分页查看自己的评论，并软删除自己的评论；登录用户可切换评论点赞状态、提交评论举报。管理员可查看举报列表、更新举报处理状态，并从管理接口删除评论。
- **管理员与审计**：管理员使用独立的登录、令牌刷新、退出和个人信息接口。管理后台提供操作日志、点赞事件记录、用户列表及用户状态管理等接口。超级管理员可以软删除用户，并创建、编辑和软删除管理员账号；首次创建管理员账号使用带引导令牌保护的注册接口。
- **推荐业务接口**：登录用户可以请求生成自己的推荐内容、查询推荐结果、查询指定电影的相似电影，并记录推荐曝光、点击或不感兴趣等反馈事件。推荐结果的具体计算方式由推荐模块实现，接口以统一的请求和响应格式向前端提供结果。

以上按当前后端 HTTP 接口说明业务能力，不代表所有部署环境均已完成端到端验证。具体路径、请求参数、响应和权限以 Swagger 与 [API 契约](backend/app/api/api_contract.md) 为准。

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
│   │   ├── analytics.py         # 尚未挂载为 HTTP 路由的聚合查询
│   │   ├── email_service.py     # SMTP 邮件发送
│   │   ├── avatar_storage.py    # 头像文件保存
│   │   └── api/                 # 认证、电影、评分、收藏、评论、推荐、管理路由
│   ├── migrations/              # SQL 和 Aerich 迁移文件
│   └── pyproject.toml           # Aerich/Tortoise 配置
├── database/seed/               # 数据生成与校验脚本
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

复制 `.env.example` 为项目根目录 `.env`，填写数据库密码、JWT 密钥和其他需要的配置。不要提交真实 `.env` 或密钥。

```env
DATABASE_URL=mysql://root:123456@localhost:3306/movierecommend
SECRET_KEY=请替换为随机且足够长的密钥
ADMIN_BOOTSTRAP_TOKEN=generate-a-separate-random-bootstrap-token
CORS_ORIGINS=http://127.0.0.1:8001,http://localhost:8001
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your-mailbox@qq.com
SMTP_PASSWORD=your-mailbox-authorization-code
SMTP_FROM=your-mailbox@qq.com
SMTP_USE_SSL=true
SMTP_TIMEOUT=15
```

`SECRET_KEY` 用于 JWT 签名，生产环境必须使用独立随机值。邮件找回密码还需配置 SMTP；管理员首次注入需配置 `ADMIN_BOOTSTRAP_TOKEN`。`.env.example` 列出了完整变量模板。

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

- 认证与账号：注册、登录、刷新/退出、个人资料/密码、邮箱找回密码；头像上传使用 `POST /api/auth/register-with-avatar`。
- 电影与分类：随机、搜索/筛选/排序、详情、分类查询，以及管理员电影/分类维护。
- 用户互动：评分、收藏、评论、点赞和举报；管理端包含用户/管理员账号管理、审计日志及评论举报处理。
- 推荐：生成请求、结果查询、相似电影和推荐事件记录。

除注册接口外，受保护接口需要添加请求头：

```text
Authorization: Bearer <access_token>
```

## 数据库迁移

SQL 升级脚本位于 `backend/migrations/`：`0001_schema_upgrade.sql` 升级基础业务表结构，`0002_delivery_indexes_and_legacy_recommend.sql` 补充索引及旧推荐表字段，`0003_auth_token_version.sql` 为用户和管理员表添加 JWT 失效控制字段。它们不是 API 启动时执行的自动迁移；在已有数据库上手动执行前，先备份并核对目标库及脚本影响。


## 停止服务

在运行后端或前端服务的终端按 `Ctrl+C`。退出虚拟环境执行：

```powershell
deactivate
```
