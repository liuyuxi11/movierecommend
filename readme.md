# 电影推荐系统

## 项目简介

电影推荐系统是一个大数据项目，采用前后端分离设计，面向游客、注册用户和后台管理员，提供电影浏览、搜索、评分、评论、收藏、举报处理、个性化推荐和基础数据分析等功能。PySpark 用于离线数据处理与分析；在线业务接口由后端服务承载。

仓库现包含 FastAPI/Tortoise ORM 数据模型、分析查询、MySQL 升级 SQL、依赖清单和虚拟环境配置。完整 FastAPI API、Vue3 前端、Celery 任务实现、PySpark ALS 作业及生产部署配置仍待补充。

## 技术栈与架构

- 后端：Python、FastAPI、Tortoise ORM；具体版本待补充。
- 前端：Vue3；具体版本、构建工具和目录待补充。
- 大数据与异步任务：PySpark/Spark MLlib ALS 用于离线协同过滤模型训练和批量生成候选结果；Celery 用于异步作业编排，Redis 用作 Celery 消息代理及可选的短期任务结果后端。Spark/PySpark、Celery、Redis 版本及部署模式待补充。
- 数据库：输入 SQL 文件 `movierecommend.sql` 的导出元数据标注为 MySQL 8.0.42。实际部署版本及字符集迁移计划待补充。
- 架构：Vue3 前端通过 HTTP API 与 FastAPI 后端交互；后端通过 Tortoise ORM 访问 MySQL。FastAPI 将模型训练或批量推荐任务投递给 Celery；Celery worker 负责作业编排并提交/调用 PySpark ALS 作业。Redis 承担任务消息传递，可选保存短期任务状态；模型、训练数据快照和推荐结果应由持久化存储保存，不以 Redis 作为长期数据源。认证方式按需求为 JWT，令牌签发、刷新和失效策略待补充。

前端与后端部署地址、跨域配置和生产部署方式待补充。

## 角色与核心业务流程

### 游客

- 注册账号：填写唯一昵称、手机号、邮箱、密码和头像。手机号、邮箱均必填；密码至少 8 位且包含字母和数字；确认密码需与密码一致。
- 浏览电影：按分类浏览，支持分页，并可按评分、热度、上映时间排序。
- 搜索电影：按电影名关键词模糊搜索，结果分页；导演、演员和类型搜索范围待补充。
- 查看电影详情和评论；可查看详情页相似电影推荐。

### 注册用户

- 使用手机号、邮箱或昵称登录；JWT 及退出登录流程按接口设计实现，细节待补充。
- 修改昵称、头像、密码及联系方式；昵称不区分大小写且唯一，手机号和邮箱均必填且唯一。修改密码需验证原密码。
- 对电影评分：评分范围为 1–10 分，每位用户对每部电影一条评分记录，可修改。
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
| 评分 | 新增和修改评分 | 1–10 分；用户与电影联合唯一 |
| 评论 | 发布、查看、软删除、点赞/取消、举报审核 | 评论不可修改；发布不预审，举报后进入审核队列 |
| 收藏 | 想看、已看、取消收藏、再次收藏 | 取消软删除；恢复时更新时间 |
| 推荐 | 个性化推荐、详情页相似电影、行为反馈 | 仅面向登录用户；记录曝光、点击、不感兴趣 |
| 管理后台 | 电影、分类、评论、用户和管理员管理 | 管理员与普通用户账号分离 |
| 审计 | 管理员操作日志、点赞操作历史 | 日志长期保留，不设置自动清理期限 |
| 数据分析 | 用户、电影、评论、评分、举报、推荐指标 | 指标口径见“数据分析模块” |

## 数据分析模块

数据分析范围以用户行为明细和推荐反馈闭环为主。PySpark 用于批量数据清洗、时间范围聚合、维度分析、数据质量检查，以及离线推荐所需的数据整理和特征准备。推荐算法范围包含 Spark MLlib ALS：以 `personalratings` 中的用户 ID、电影 ID 和 1–10 分显式评分作为训练数据，异步执行训练、离线评估和批量候选生成。Celery 负责将耗时任务放到后台执行，Redis 负责消息代理；FastAPI 在线请求读取已生成的推荐结果，不在请求处理中启动 Spark 训练作业。

ALS 参数、训练/验证数据切分方式、评估指标、重训频率、冷启动用户/电影的处理策略、Spark 部署模式和 Celery worker 如何提交 Spark 作业均待补充。建议离线评估同时考虑评分误差指标和 Top-K 排序指标，最终指标及计算口径待确认。模型文件和训练产物需写入持久化存储；具体存储位置待补充。

初期指标由明细表聚合，不预建统计快照表。若后续需要缓存周期性分析结果，应先确认分析结果的存储位置、刷新频率和查询接口，再评估增加汇总表或文件存储。

| 指标 | 数据来源 | 统计说明 |
|---|---|---|
| 用户总数、启用数、禁用数 | `user.created_at`、`user.status`、`user.deleted_at` | 默认排除软删除用户；软删除后昵称、手机号和邮箱可以重新注册 |
| 有效电影数 | `movieinfo.movieid`、`movieinfo.deleted_at` | 默认排除软删除电影 |
| 评分分布、电影平均分、评分人数 | `personalratings.rating`、`movieid`、`rated_at` | 评分范围 1–10；用户修改评分后按当前评分统计 |
| 评论总数、待审核数、隐藏数 | `moviecomment.moderation_status`、`created_at`、`deleted_at` | 待审核评论仍展示；隐藏及软删除评论不计入前台可见评论数 |
| 当前点赞数、点赞和取消次数 | `commentlike.is_active`、`commentlike_event.action` | 当前状态与操作历史分开统计 |
| 举报量、待处理量、处理时长 | `commentreport.status`、`created_at`、`handled_at` | 状态为 `pending`、`accepted`、`rejected` |
| 想看数、已看数 | `userfavorite.status`、`deleted_at` | 排除已取消收藏记录 |
| 推荐曝光量、点击率、不感兴趣率 | `recommendationevent.event_type` | 事件包括 `impression`、`click`、`not_interested`；曝光应在推荐项实际进入可视区域后记录 |
| 管理员操作量 | `adminoperationlog.adminid`、`action`、`created_at` | 按管理员、操作类型和时间范围聚合；日志长期保留 |

推荐只面向登录用户。推荐结果明细保存请求批次、电影、列表位置和算法版本；事件表保存曝光及后续行为。ALS 预测分与 `movieinfo` 的电影评分是不同概念；当前 `recommendresult.rating` 已确认表示电影评分，不能复用为 ALS 预测分。推荐项是否增加独立的 `prediction_score` 字段，或另设模型输出表，需在 ORM/结果表设计前确认。具体去重窗口、点击率分母及“不感兴趣”统计口径待补充。

## 数据库表结构概览

以下为 ORM 目标结构。`movierecommend.sql` 是升级前基线；新增模型与升级 SQL 位于 `app/models.py` 和 `migrations/0001_schema_upgrade.sql`。

| 表 | 用途与关键关系 |
|---|---|
| `user` | 普通用户账号；包含头像 `avatar` 字段；昵称、手机号、邮箱必填，未删除账号唯一且昵称大小写不敏感；软删除后可重新注册 |
| `adminuser` | 独立管理员账号，区分普通管理员和超级管理员 |
| `movieinfo` | 电影基础信息；包含评分、热度及旧字段 `typelist`；软删除 |
| `category` | 电影分类；软删除 |
| `moviecategory` | 电影与分类的多对多关联 |
| `personalratings` | 注册用户评分；`ratingid` 单列主键，`(userid, movieid)` 联合唯一，分值范围 1–10，时间按 UTC 处理 |
| `trainingdataset` | 离线训练数据集元信息及原始评分范围 |
| `trainingrating` | 离线数据集评分；外部用户 ID 与应用用户 ID 分开，避免 ID 冲突 |
| `moviecomment` | 电影评论；不可修改，支持审核状态及软删除 |
| `commentlike` | 用户对评论的当前点赞状态；允许反复点赞和取消 |
| `commentlike_event` | 每次点赞或取消的历史操作记录 |
| `commentreport` | 评论举报；同一用户对同一评论唯一，记录原因和处理结论 |
| `userfavorite` | 用户电影收藏；想看/已看，取消软删除，重新收藏恢复记录 |
| `adminoperationlog` | 管理员关键操作日志，长期保留 |
| `recommendationitem` | 面向登录用户生成的推荐项，记录请求、电影、位置、电影评分快照、ALS 预测分、算法版本及生成时间 |
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
- PySpark 作业目录：当前仓库未提供；建议后续按数据导入/清洗、离线聚合和推荐特征准备划分作业模块，具体目录待补充。
- Celery worker/task 配置、Redis 配置及 Spark 作业提交脚本：当前仓库未提供，待补充。
- `电影推荐系统需求分析.docx`：功能需求文档。
- FastAPI API、Vue3 前端、Celery 任务和 PySpark 作业代码：待补充。

## 环境与启动

### 环境要求

- Python 版本：本地虚拟环境使用 Python 3.12.5。
- FastAPI、Tortoise ORM、Aerich、PySpark、Celery 及数据库驱动的直接依赖版本见 `requirement.txt`。
- 当前机器检测到 Java 24；与 PySpark 4.0.4 的运行兼容性待验证，Spark 部署模式待补充。
- Celery、Redis 版本及 Redis 在部署中的高可用、鉴权和持久化配置：待补充。
- Vue3、Node.js 和包管理器版本：待补充。
- MySQL 版本：输入 SQL 导出标注 MySQL 8.0.42；实际运行环境待补充。
- 数据库连接配置、JWT 密钥及其他环境变量：待补充。敏感配置应通过环境变量或本地配置管理，不应提交密钥。

### 启动方式

创建虚拟环境并安装 Python 依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirement.txt
```

Tortoise 配置读取 `DATABASE_URL`；连接地址需通过环境变量提供。仓库当前没有 FastAPI 应用入口、前端 `package.json`、PySpark 作业、Celery worker 配置或 Redis 服务端，因此这些服务的启动命令待补充。

升级数据库前先备份，并在确认目标库后执行 `migrations/0001_schema_upgrade.sql`。该脚本清理 `personalratings` 中无法关联应用用户/电影、评分越界、时间戳非法及重复的记录；给定 SQL 导出中的 `user` 表为空，因此其中现有评分会作为孤立记录清理。脚本不会连接或自动执行。

后续应至少提供：

1. 数据库创建、迁移及初始数据导入步骤。
2. Python 依赖安装和 FastAPI 服务启动命令。
3. 前端依赖安装和 Vue3 开发服务启动命令。
4. Redis 启动与连接配置，以及 Celery worker（和可选 Celery Beat）的启动命令。
5. PySpark ALS 作业提交命令、运行模式、配置入口及模型/结果存储位置。
6. 完整应用所需环境变量及本地开发配置示例。

## 接口与数据流概要

实际 API 路径、请求/响应 schema、分页格式、错误码和认证中间件尚未提供，均待补充。按已确认业务规则，核心数据流如下：

1. 用户通过 FastAPI 注册或登录；账号数据写入 `user`，登录成功后由后端签发 JWT。
2. 电影浏览、搜索和分类查询读取未软删除的 `movieinfo`，分类关联由 `moviecategory` 提供。
3. 用户评分写入或更新 `personalratings`；评论、点赞、收藏和举报写入对应行为表。
4. 举报创建时，评论进入 `review_pending` 但继续展示；管理员结案后按结果设置为 `hidden` 或恢复为 `published`，后台操作写入 `adminoperationlog`。
5. 用户推荐请求由 FastAPI 查询已完成的推荐结果；模型未就绪或用户无历史评分时的回退策略待补充。
6. Celery 接收训练/批量推荐任务，并通过 worker 编排 PySpark ALS 作业；训练结果、模型文件和任务状态分别使用确认后的持久化存储、模型存储和任务状态方案。
7. PySpark 从数据库或数据文件读取用户评分及必要维度数据，进行清洗、校验、训练/评估和批量候选生成；推荐结果写入确认后的结果存储。
8. 用户实际看到推荐项时记录曝光，点击和不感兴趣反馈关联对应推荐项；数据分析查询聚合推荐指标及其他用户行为指标。

## 待补充事项

- 后端和前端源码目录、依赖文件、版本及本地启动命令。
- API 路径清单、接口 schema、错误码、分页与排序参数约定。
- MySQL 实际版本、迁移工具及目标结构迁移脚本。
- PySpark/Spark 与 Java 版本、部署模式、作业调度方式、输入/输出存储和数据刷新频率。
- PySpark 批处理结果由后端实时聚合、写入 MySQL 汇总表，还是保存到文件/数据湖供查询。
- ALS 训练参数、训练数据切分、评估指标、冷启动策略、模型版本发布/回滚和重训频率。
- 推荐结果是否持久化 ALS `prediction_score`，以及模型文件和训练产物的持久化位置。
- Celery worker 与 Spark 的集成方式（本地进程提交、Standalone 或集群作业提交）、任务幂等、重试及失败状态处理。
- 两份 SQL 导出文件的版本关系，以及 `recommendresult` 是否在运行环境中有数据或被现有接口使用。
- 数据集来源、导入流程和使用许可。
- 推荐算法版本的命名规则、推荐请求 ID 生成规则及分析指标去重口径。
- 找回密码流程、JWT 失效/刷新策略和管理员权限明细。
