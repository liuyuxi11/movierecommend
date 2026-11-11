# 电影推荐系统

## 项目简介

电影推荐系统是一个大数据项目，采用前后端分离设计，面向游客、注册用户和后台管理员，提供电影浏览、搜索、评分、评论、收藏、举报处理、个性化推荐和基础数据分析等功能。PySpark 用于离线数据处理与分析；在线业务接口由后端服务承载。

仓库包含 FastAPI/Tortoise ORM 后端、静态 JavaScript 前端、Celery 推荐任务、PySpark ALS 离线作业、MySQL 迁移和本地演示配置；生产部署配置仍需按目标环境补充。

## 技术栈与架构

- 后端：Python、FastAPI、Tortoise ORM；依赖版本见 `requirements.txt` 和 `backend/pyproject.toml`。
- 前端：原生 JavaScript 静态页面，无 Vue 构建步骤；运行说明见 `frontend/README.md`。
- 大数据与异步任务：PySpark/Spark MLlib ALS 用于离线协同过滤模型训练和批量候选生成；Celery 用于异步任务编排，Redis 用作消息代理和短期推荐缓存。运行版本及部署模式由目标环境配置。
- 数据库：输入 SQL 文件 `movierecommend.sql` 的导出元数据标注为 MySQL 8.0.42。实际部署版本及字符集迁移计划待补充。
- 架构：静态前端通过 HTTP API 与 FastAPI 后端交互；后端通过 Tortoise ORM 访问 MySQL。离线运行 PySpark ALS 作业并发布共享 JSONL 用户候选；Celery Worker 负责在线候选重排、`recommendationitem` 发布和 Redis 缓存更新。Redis 同时承担 Celery 消息代理和短期推荐缓存；MySQL 是推荐结果持久化来源。用户评分提交后通过 Celery 异步刷新推荐列表。

前端与后端部署地址、跨域配置和生产部署方式待补充。

## 角色与核心业务流程

### 游客

- 注册账号：填写唯一昵称、手机号、邮箱、密码和头像。手机号、邮箱均必填；密码至少 8 位且包含字母和数字；确认密码需与密码一致。
- 浏览电影：按分类浏览，支持分页，并可按评分、热度、上映时间排序。
- 搜索电影：按电影名、导演、演员或类型关键词模糊搜索，结果分页。
- 查看电影详情和评论；可查看详情页相似电影推荐。

### 注册用户

- 使用手机号、邮箱或昵称登录；JWT 及退出登录流程按接口设计实现，细节待补充。
- 修改昵称、头像、密码及联系方式；昵称不区分大小写且唯一，手机号和邮箱均必填且唯一。修改密码需验证原密码。
- 对电影评分：评分范围为 1–5 分，每位用户对每部电影一条评分记录，可修改。
- 发布评论：评论发布后直接展示，不允许修改。评论被举报后仍展示，同时进入后台审核队列。
- 点赞和取消点赞评论；操作允许反复切换，并记录每次操作。
- 收藏电影，状态限于“想看”和“已看”。取消收藏采用软删除；再次收藏恢复原记录并更新时间。
- 举报评论：同一用户对同一评论只能举报一次。原因包括恶意攻击、侮辱性言论、传播不良信息、过度商业推广、广告和其他；选择其他时必须填写说明。
- 查看个人评分、评论和收藏记录；获取个性化推荐。

### 后台管理员

- 普通管理员维护电影、分类和评论，并处理举报及评论审核。
- 超级管理员管理管理员账号和用户账号；用户禁用可恢复，用户及电影按软删除处理。
- 管理员账号与普通用户账号分表存储。关键后台操作写入管理员操作日志。

评论举报审核结论为 `pending`、`accepted`、`rejected`。`accepted` 后评论设为 `hidden`；`rejected` 后评论恢复为 `published`。举报后、结案前，评论保持展示并处于待审核队列。

## 功能需求清单

| 模块 | 功能 | 说明 |
|---|---|---|
| 账号 | 注册、登录、退出、资料维护、找回密码 | 找回密码方式待补充；账号密码应安全哈希存储 |
| 电影 | 列表、详情、搜索、排序、分类管理 | 电影采用软删除；电影名模糊搜索 |
| 评分 | 新增和修改评分 | 1–5 分；用户与电影联合唯一 |
| 评论 | 发布、查看、软删除、点赞/取消、举报审核 | 评论不可修改；发布不预审，举报后进入审核队列 |
| 收藏 | 想看、已看、取消收藏、再次收藏 | 取消软删除；恢复时更新时间 |
| 推荐 | 个性化推荐、详情页相似电影、行为反馈 | 仅面向登录用户；记录曝光、点击、不感兴趣 |
| 管理后台 | 电影、分类、评论、用户和管理员管理 | 管理员与普通用户账号分离 |
| 审计 | 管理员操作日志、点赞操作历史 | 日志长期保留，不设置自动清理期限 |
| 数据分析 | 用户、电影、评论、评分、举报、推荐指标 | 指标口径见“数据分析模块” |

## 数据分析模块

推荐算法使用 Spark MLlib 显式 ALS：训练源仅为 `personalratings(userid,movieid,rating,rated_at)`，评分范围 1–5；过滤软删除用户和电影，不按用户启用状态过滤，也不使用 `userfavorite`。离线作业负责训练、验证/测试评估、选取混合权重并发布共享 JSONL 候选。Celery Worker 根据离线候选、当前评分产生的类型偏好、近期点击/不感兴趣事件和热门榜重排最多 20 部电影，写入 `recommendationitem`，随后更新 Redis。用户提交评分后，评分事务成功才异步投递单用户刷新任务；API 请求本身不启动 Spark。

ALS 参数和评估口径见 `docs/als-recommendation.md`。Worker 的在线排序权重可通过 `RECOMMENDATION_OFFLINE_RANK_WEIGHT`、`RECOMMENDATION_POPULARITY_RANK_WEIGHT`、`RECOMMENDATION_PROFILE_RANK_WEIGHT` 配置，默认分别为 0.75、0.10、0.15；离线候选次序本身已含 ALS/热门混合信号，因此在线热门权重较低以减少重复计入。权重是初始实验值，须通过固定快照的 Top-K 实验验证后才能作为效果结论。评分触发的刷新复用当前离线 JSONL 候选，不会立即重训 ALS 或更新用户因子；新增评分会影响已评分过滤、类型偏好重排和后续离线训练。

初期指标由明细表聚合，不预建统计快照表。若后续需要缓存周期性分析结果，应先确认分析结果的存储位置、刷新频率和查询接口，再评估增加汇总表或文件存储。

| 指标 | 数据来源 | 统计说明 |
|---|---|---|
| 用户总数、启用数、禁用数 | `user.created_at`、`user.status`、`user.deleted_at` | 默认排除软删除用户；软删除后昵称、手机号和邮箱可以重新注册 |
| 有效电影数 | `movieinfo.movieid`、`movieinfo.deleted_at` | 默认排除软删除电影 |
| 评分分布、电影平均分、评分人数 | `personalratings.rating`、`movieid`、`rated_at` | 评分范围 1–5；用户修改评分后按当前评分统计 |
| 评论总数、待审核数、隐藏数 | `moviecomment.moderation_status`、`created_at`、`deleted_at` | 待审核评论仍展示；隐藏及软删除评论不计入前台可见评论数 |
| 当前点赞数、点赞和取消次数 | `commentlike.is_active`、`commentlike_event.action` | 当前状态与操作历史分开统计 |
| 举报量、待处理量、处理时长 | `commentreport.status`、`created_at`、`handled_at` | 状态为 `pending`、`accepted`、`rejected` |
| 想看数、已看数 | `userfavorite.status`、`deleted_at` | 排除已取消收藏记录 |
| 推荐曝光量、点击率、不感兴趣率 | `recommendationevent.event_type` | 事件包括 `impression`、`click`、`not_interested`；曝光应在推荐项实际进入可视区域后记录 |
| 管理员操作量 | `adminoperationlog.adminid`、`action`、`created_at` | 按管理员、操作类型和时间范围聚合；日志长期保留 |

推荐只面向登录用户。推荐结果明细保存请求批次、电影、位置、算法版本及排序分；事件表保存曝光及后续行为。`recommendationitem.prediction_score` 在当前 Worker 中承载 0–1 的本次候选列表排序分，不是 1–5 电影评分、ALS 原始预测值或匹配概率。前端同时显示“ALS 个性化”或“热门补位”来源；排序分仅用于解释该列表内的次序，不宜跨用户、批次或算法版本比较。旧 `recommendresult.rating` 仍表示电影评分。

曝光、点击和“不感兴趣”事件会写入 `recommendationevent`。Worker 使用近 90 天点击信号对该电影排序分最多增加 0.10，并过滤近 90 天标记为“不感兴趣”的电影；曝光仅参与统计，不直接影响排序。评分写入会触发单用户刷新，但不会即时重训 ALS 因子。

管理员分析接口 `GET /api/analytics/overview` 汇总用户、电影、评分、评论、举报、收藏、点赞历史、推荐项和管理员操作量；同时返回时间窗内推荐曝光、点击、不感兴趣事件数。CTR 定义为点击事件数/曝光事件数，不感兴趣率定义为不感兴趣事件数/曝光事件数，均按事件计数而非去重用户或去重推荐项；无曝光时比率为 `null`。

## 数据库表结构概览

以下为 ORM 目标结构。`movierecommend.sql` 是升级前基线；新增模型与升级 SQL 位于 `app/models.py` 和 `migrations/0001_schema_upgrade.sql`。

| 表 | 用途与关键关系 |
|---|---|
| `user` | 普通用户账号；包含头像 `avatar` 字段；昵称、手机号、邮箱必填，未删除账号唯一且昵称大小写不敏感；软删除后可重新注册 |
| `adminuser` | 独立管理员账号，区分普通管理员和超级管理员 |
| `movieinfo` | 电影基础信息；包含评分、热度及旧字段 `typelist`；软删除 |
| `category` | 电影分类；软删除 |
| `moviecategory` | 电影与分类的多对多关联 |
| `personalratings` | 用户评分；`ratingid` 单列主键，`(userid, movieid)` 联合唯一，分值范围 1–5，时间按 UTC 处理 |
| `trainingdataset` | 离线训练数据集元信息及原始评分范围 |
| `trainingrating` | 离线数据集评分；外部用户 ID 与应用用户 ID 分开，避免 ID 冲突 |
| `moviecomment` | 电影评论；不可修改，支持审核状态及软删除 |
| `commentlike` | 用户对评论的当前点赞状态；允许反复点赞和取消 |
| `commentlike_event` | 每次点赞或取消的历史操作记录 |
| `commentreport` | 评论举报；同一用户对同一评论唯一，记录原因和处理结论 |
| `userfavorite` | 用户电影收藏；想看/已看，取消软删除，重新收藏恢复记录 |
| `adminoperationlog` | 管理员关键操作日志，长期保留 |
| `recommendationitem` | 面向登录用户生成的推荐项，记录请求、电影、位置、电影评分快照、列表排序分、算法版本及生成时间 |
| `recommendationevent` | 推荐项的曝光、点击和不感兴趣事件 |
| `recommendresult` | 现有兼容表；其中 `rating` 表示电影评分，不是推荐预测分。迁移和退役计划待补充 |

主要关系：用户和电影分别与评分、评论、收藏及推荐明细建立一对多关系；电影与分类通过 `moviecategory` 多对多关联；用户与评论通过 `commentlike` 建立当前点赞关系，并由 `commentlike_event` 保存历史操作；举报关联评论及举报用户；管理员通过 `adminoperationlog` 保留审计记录。

现有 `movierecommend.sql` 中只有 `movieinfo`、`personalratings`、`recommendresult`、`user` 四张表，未声明外键、普通索引或评分联合唯一约束；该导出中的 `user` 和 `recommendresult` 没有记录，而 `personalratings` 存在找不到用户记录的评分。升级 SQL 会清理孤立、非法和重复的应用评分；外部数据应导入 `trainingrating`，不可伪造应用用户。旧 `recommendresult.rating` 是电影评分；由于旧表没有批次、推荐位置、曝光时间和反馈信息，不能据此还原历史推荐曝光或用户反馈。

## 仓库目录

当前仓库已发现文件如下：

```text
.
├── movierecommend.sql
├── MovieRecommendDatabase.sql
├── requirement.txt
├── pyproject.toml
├── app/
│   ├── database.py
│   ├── models.py
│   └── analytics.py
├── migrations/
│   ├── 0001_schema_upgrade.sql
│   └── aerich/
├── 电影推荐系统需求分析.docx
└── movie_recommend/
    ├── movies.dat
    ├── personalRatings.dat
    └── ratings.dat
```

- `movierecommend.sql`：当前表结构及数据导出，是本项目方案分析使用的 SQL 文件。
- `MovieRecommendDatabase.sql`：仓库中的另一份数据库导出；与主 SQL 文件的版本关系和用途待补充。
- `movie_recommend/movies.dat`、`personalRatings.dat`、`ratings.dat`：电影和评分数据文件；数据集来源、许可及导入脚本待补充。
- `backend/jobs/als_recommender.py`：离线训练、评估和 JSONL 发布作业。
- `backend/app/recommendation_tasks.py`：Celery 在线候选重排与结果发布任务。
- `backend/app/api/ratings.py`：评分事务提交后投递单用户推荐刷新。
- `电影推荐系统需求分析.docx`：功能需求文档。

## 环境与启动

### 环境要求

- Python 版本：本地虚拟环境使用 Python 3.12.5。
- FastAPI、Tortoise ORM、Aerich、PySpark、Celery 及数据库驱动的直接依赖版本见 `requirement.txt`。
- PySpark 4.0.4 使用 Java 21 的本地配置；实际部署的 Spark 模式和资源参数按运行环境确认。
- Celery、Redis 和 MySQL 版本及部署参数需按目标运行环境记录；输入 SQL 导出元数据标注 MySQL 8.0.42。
- 数据库连接配置、JWT 密钥及其他环境变量：待补充。敏感配置应通过环境变量或本地配置管理，不应提交密钥。

### 启动方式

创建虚拟环境并安装 Python 依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Tortoise 配置读取 `DATABASE_URL`；数据库、Redis、Celery 和 ALS 共享路径通过环境变量配置。FastAPI 应用入口、前端静态页面、PySpark 作业及 Celery worker 代码已存在；各环境的服务启动命令需按本地部署设置确认。

升级数据库前先备份，并在确认目标库后执行 `migrations/0001_schema_upgrade.sql`。该脚本清理 `personalratings` 中无法关联应用用户/电影、评分越界、时间戳非法及重复的记录；给定 SQL 导出中的 `user` 表为空，因此其中现有评分会作为孤立记录清理。脚本不会连接或自动执行。

部署说明还应补充：

1. 数据库创建、迁移及初始数据导入步骤。
2. Python 依赖安装和 FastAPI 服务启动命令。
3. 静态前端服务的部署地址及 FastAPI CORS 配置。
4. Redis 启动与连接配置，以及 Celery worker 和 Celery Beat 的启动命令。
5. PySpark ALS 作业提交命令、运行模式、配置入口及模型/结果存储位置。Beat 默认每 7 天触发 `recommendation.train_als`；通过 `ALS_TRAIN_INTERVAL_SECONDS` 配置间隔，需单独启动 Beat 进程。
6. 完整应用所需环境变量及本地开发配置示例。

在 `backend` 目录启动在线 Worker 和离线训练调度器：

```powershell
celery -A app.celery_app:celery_app worker --loglevel=INFO --pool=solo
celery -A app.celery_app:celery_app beat --loglevel=INFO
```

Beat 的计划任务只负责投递 `recommendation.train_als`；Spark 作业超时可用 `ALS_TRAIN_TIMEOUT_SECONDS` 配置。Windows 下 Worker 使用 `--pool=solo`，Spark/Java/JDBC 环境仍需单独通过 ALS 检查脚本。

## 接口与数据流概要

API 路径、请求/响应 schema、分页格式和错误码见 `backend/app/api/api_contract.md`。核心数据流如下：

1. 用户通过 FastAPI 注册或登录；账号数据写入 `user`，登录成功后由后端签发 JWT。
2. 电影浏览、搜索和分类查询读取未软删除的 `movieinfo`，分类关联由 `moviecategory` 提供。
3. 用户评分写入或更新 `personalratings`；评论、点赞、收藏和举报写入对应行为表。
4. 举报创建时，评论进入 `review_pending` 但继续展示；管理员结案后按结果设置为 `hidden` 或恢复为 `published`，后台操作写入 `adminoperationlog`。
5. 用户提交推荐请求时，FastAPI 返回 HTTP 202 和请求/任务 ID；Celery Worker 读取最新离线 JSONL，结合当前用户评分、有效电影和热门候选生成最多 20 项。
6. Worker 在 MySQL 事务提交 `recommendationitem` 后主动写 Redis。API 读取时优先 Redis，未命中回源 MySQL 并回填缓存。
7. 评分提交事务成功后，FastAPI 尽力投递 `recommendation.refresh_user`；Worker 完成后产生新的请求批次并覆盖该用户最新缓存。队列不可用不撤销已经保存的评分，响应会报告是否成功投递刷新任务。
8. 刷新复用离线 ALS JSONL 中的用户候选顺序，不在线启动 Spark；它会根据当前评分更新类型偏好重排，并以热门榜补足。ALS 因子只在下一次离线训练后更新。
9. 用户实际看到推荐项时记录曝光，点击和不感兴趣反馈关联对应推荐项；数据分析查询聚合推荐指标及其他用户行为指标。

## 待补充事项

- 目标部署环境的服务启动方式、MySQL 版本和 Spark/Celery/Redis 部署参数。
- PySpark 作业调度频率、输入快照刷新周期及离线批次发布策略。
- 在线重排权重需使用固定快照和相同候选集做离线对照实验；当前默认值是待验证配置。
- 评分提交后的刷新是事件触发的在线列表更新，不是实时 ALS 训练。若需让新评分立即影响 ALS 因子，需另外设计因子更新或按用户重训并测量延迟。
- 两份 SQL 导出文件的版本关系，以及 `recommendresult` 是否在运行环境中有数据或被现有接口使用。
- 数据集来源、导入流程和使用许可。
- 推荐算法版本的命名规则、推荐请求 ID 生成规则及分析指标去重口径。
- 管理员权限明细及上线环境的令牌密钥轮换流程。Refresh token 当前按 Redis `jti` 单次轮换；上线此版本后，旧格式 refresh token 需重新登录。
