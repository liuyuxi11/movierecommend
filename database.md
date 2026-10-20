# 数据库结构说明

本文档描述当前 `movierecommend` MySQL 数据库。业务 schema 由 `migrations/0001_schema_upgrade.sql` 建立，Tortoise ORM 定义位于 `app/models.py`。当前数据库另有 Aerich 迁移元数据表 `aerich`。

## 约定

- 数据库为 MySQL 8.0.42，表使用 InnoDB。新建业务表使用 `utf8mb4_0900_ai_ci`；沿用旧 schema 的 `user`、`movieinfo`、`personalratings`、`recommendresult` 仍为 `utf8mb3_general_ci`。`user.active_username` 生成列单独使用 `utf8mb4_0900_ai_ci`，因此昵称唯一性大小写不敏感。旧表字符集后续若需统一，应单独评估字符转换和索引影响。
- `DATETIME(6)` 本身不携带时区。应用通过 Tortoise `use_tz=True`、`timezone="UTC"` 统一按 UTC 写入和读取；Unix 秒时间戳需先转换为 UTC，再写入 `rated_at` 或对应 UTC 时间列。
- 业务关系外键默认采用 `RESTRICT`，阻止物理删除仍被引用的用户、电影、评论或数据集；举报处理人外键 `handled_by_adminid` 使用 `SET NULL`。业务账号、电影、评论、收藏和分类应通过 `deleted_at` 软删除；分析查询需按指标口径过滤软删除数据。
- `user` 的 `active_username`、`active_phone`、`active_email` 是数据库生成列，仅用于活动账号的唯一约束，不属于业务输入字段。软删除账号对应生成值为 `NULL`，允许相同昵称、手机号或邮箱重新注册。
- 时间列的 `CURRENT_TIMESTAMP(6)` 和 `ON UPDATE` 是数据库默认行为；服务写入时间应继续遵循 UTC 约定。
- 下文 `PK` 表示主键，`FK` 表示外键，`UQ` 表示唯一约束，`IDX` 表示普通索引，`CK` 表示 CHECK 约束。

## 关系总览

```text
user ──< personalratings >── movieinfo
user ──< moviecomment >───── movieinfo
user ──< commentlike >────── moviecomment
user ──< commentlike_event > moviecomment
user ──< commentreport >──── moviecomment ──> adminuser (handled_by)
user ──< userfavorite >───── movieinfo
movieinfo ──< moviecategory >── category
trainingdataset ──< trainingrating >── movieinfo
user ──< recommendationitem >── movieinfo ──< recommendationevent
adminuser ──< adminoperationlog
```

符号 `A ──< B` 表示 B 中可有多条记录引用 A。推荐事件通过 `recommendationid` 关联推荐项，再从推荐项取得用户和电影。

## 业务表

### `user`：普通用户

保存注册用户身份、登录和资料信息；管理员账号单独保存在 `adminuser`。

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `userid` | int | 否 | PK，自增用户 ID。 |
| `username` | varchar(50) | 否 | 昵称；活动账号唯一且大小写不敏感。 |
| `password` | varchar(255) | 否 | 密码哈希，不得保存明文密码。 |
| `phone` | varchar(32) | 否 | 必填；活动账号唯一。 |
| `email` | varchar(254) | 否 | 必填；活动账号唯一。 |
| `avatar` | varchar(1000) | 是 | 头像 URL 或存储引用。 |
| `status` | varchar(20) | 否 | 默认 `active`；账号状态值需由应用约定。 |
| `created_at` / `updated_at` | datetime(6) | 否 | 创建和最后更新时间。 |
| `deleted_at` | datetime(6) | 是 | 软删除时间；NULL 表示未删除。 |
| `active_username` / `active_phone` / `active_email` | 生成列 | 是 | 仅未删除用户计算实际值；用于三个活动账号唯一索引。 |

约束：PK `userid`；UQ `uk_user_active_username(active_username)`、`uk_user_active_phone(active_phone)`、`uk_user_active_email(active_email)`；IDX `idx_user_status_created(status, created_at)`、`idx_user_deleted_at(deleted_at)`。生成列不是由 ORM 创建用户时传入的字段。

### `adminuser`：管理员

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `adminid` | int | 否 | PK，自增管理员 ID。 |
| `username` | varchar(50) | 否 | 管理员登录名。 |
| `password` | varchar(255) | 否 | 管理员密码哈希。 |
| `role` | varchar(30) | 否 | 管理角色。 |
| `status` | varchar(20) | 否 | 默认 `active`。 |
| `created_at` / `updated_at` | datetime(6) | 否 | 创建和更新时间。 |
| `deleted_at` | datetime(6) | 是 | 管理员软删除时间。 |

约束：PK `adminid`；UQ `uk_adminuser_username(username)`；IDX `idx_adminuser_role_status(role, status)`；CK `chk_adminuser_role` 只允许 `admin`、`superadmin`。管理员用户名当前唯一约束不因软删除释放。

### `movieinfo`：电影

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `movieid` | int | 否 | PK；当前 ID 由导入数据提供，不是自增列。 |
| `moviename` | varchar(1000) | 是 | 电影名。 |
| `releasetime` | date | 是 | 上映日期。 |
| `director` / `leadactors` | varchar(1000) | 是 | 导演和主演文本。 |
| `picture` | varchar(1000) | 是 | 图片地址或存储引用。 |
| `averating` | double(11,1) | 是 | 电影资料中的平均分；需与站内用户评分聚合口径区分。 |
| `numrating` | int | 是 | 电影资料中的评分数；需明确其数据来源。 |
| `description` | varchar(1000) | 是 | 简介。 |
| `typelist` | varchar(255) | 是 | 原始逗号分隔类型，保留用于兼容；规范关系见 `moviecategory`。 |
| `updated_at` | datetime(6) | 否 | 更新时间。 |
| `deleted_at` | datetime(6) | 是 | 电影软删除时间。 |

约束：PK `movieid`；IDX `idx_movieinfo_rating(averating)`、`idx_movieinfo_popularity(numrating)`、`idx_movieinfo_release(releasetime)`、`idx_movieinfo_deleted_at(deleted_at)`。业务列表默认过滤 `deleted_at IS NOT NULL` 的电影；历史评分和反馈仍保留。

### `personalratings`：站内用户评分

保存注册用户当前有效评分，每个用户对每部电影至多一条。修改评分是更新当前记录，不保留每次修改历史。

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `ratingid` | bigint | 否 | PK，自增评分记录 ID。 |
| `userid` | int | 否 | FK → `user.userid`。 |
| `movieid` | int | 否 | FK → `movieinfo.movieid`。 |
| `rating` | int | 否 | 1–10 分。 |
| `rated_at` | datetime(6) | 否 | 当前评分时间，按 UTC 存储。 |
| `timestamp` | char(10) | 是 | 旧 Unix 时间戳字段，作为兼容/审计字段暂留；新逻辑使用 `rated_at`。 |

约束：PK `ratingid`；UQ `uk_personalratings_user_movie(userid, movieid)`；FK `fk_personalratings_user`、`fk_personalratings_movie`，删除规则均为 RESTRICT；CK `chk_personalratings_rating` 限制 1–10；IDX `idx_personalratings_movie_rating(movieid, rating)`、`idx_personalratings_user_rated(userid, rated_at)`。

ALS 显式反馈可从 `(userid, movieid, rating)` 读取。导出到 Spark 前需决定是否过滤软删除用户/电影；当前表不含独立的评分变更事件。

### `trainingdataset`：离线训练数据集元信息

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `datasetid` | int | 否 | PK，自增数据集 ID。 |
| `dataset_key` | varchar(100) | 否 | 稳定的数据集业务标识。 |
| `source_name` | varchar(255) | 否 | 数据源名称。 |
| `rating_min` / `rating_max` | decimal(5,2) | 否 | 原始评分范围边界。 |
| `created_at` | datetime(6) | 否 | 数据集记录创建时间。 |

约束：PK `datasetid`；UQ `uk_trainingdataset_key(dataset_key)`；CK `chk_trainingdataset_rating_range(rating_min < rating_max)`。该表目前不记录文件路径、校验和、导入状态或许可信息。

### `trainingrating`：离线训练评分明细

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `trainingratingid` | bigint | 否 | PK，自增导入行 ID。 |
| `datasetid` | int | 否 | FK → `trainingdataset.datasetid`。 |
| `external_userid` | int | 否 | 原始数据集中的用户 ID，不是站内 `userid`。 |
| `movieid` | int | 否 | FK → `movieinfo.movieid`。 |
| `rating` | decimal(5,2) | 否 | 原始评分；导入时按数据集评分范围验证。 |
| `rated_at` | datetime(6) | 是 | 原始评分时间；若源时间存在，转换为 UTC。 |

约束：PK `trainingratingid`；UQ `uk_trainingrating_dataset_user_movie(datasetid, external_userid, movieid)`；FK `fk_trainingrating_dataset`、`fk_trainingrating_movie`，删除规则为 RESTRICT；IDX `idx_trainingrating_movie(movieid)`、`idx_trainingrating_dataset_user(datasetid, external_userid)`。跨数据集训练时外部用户 ID 可能重复，Spark 侧应使用数据集维度构造训练用户键或重新编码连续整数 ID。

### `category`：电影类型

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `categoryid` | int | 否 | PK，自增分类 ID。 |
| `name` | varchar(100) | 否 | 分类名称。 |
| `created_at` | datetime(6) | 否 | 创建时间。 |
| `deleted_at` | datetime(6) | 是 | 软删除时间。 |

约束：PK `categoryid`；UQ `uk_category_name(name)`。唯一约束没有按软删除状态区分；同名分类不能重复插入。

### `moviecategory`：电影与类型关联

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `id` | bigint | 否 | PK，自增关联 ID。 |
| `movieid` | int | 否 | FK → `movieinfo.movieid`。 |
| `categoryid` | int | 否 | FK → `category.categoryid`。 |

约束：PK `id`；UQ `uk_moviecategory_movie_category(movieid, categoryid)`；IDX `idx_moviecategory_category_movie(categoryid, movieid)`；两个 FK 均为 RESTRICT。电影筛选和类型聚合应使用该表；`movieinfo.typelist` 是兼容字段，不应与关联表形成双重写入源。

### `moviecomment`：电影评论

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `commentid` | bigint | 否 | PK，自增评论 ID。 |
| `userid` | int | 否 | FK → `user.userid`。 |
| `movieid` | int | 否 | FK → `movieinfo.movieid`。 |
| `content` | varchar(500) | 否 | 评论内容；业务规则不允许修改。 |
| `moderation_status` | varchar(20) | 否 | 默认 `published`；允许 `published`、`review_pending`、`hidden`。 |
| `created_at` | datetime(6) | 否 | 评论创建时间。 |
| `deleted_at` | datetime(6) | 是 | 评论软删除时间。 |

约束：PK `commentid`；FK `fk_moviecomment_user`、`fk_moviecomment_movie`，均为 RESTRICT；IDX `idx_moviecomment_movie_created(movieid, created_at)`、`idx_moviecomment_user_created(userid, created_at)`、`idx_moviecomment_moderation_created(moderation_status, created_at)`；CK `chk_moviecomment_moderation_status`。被举报后仍展示但进入 `review_pending`；结案接受后改为 `hidden`，驳回后恢复 `published`。展示评论应同时过滤软删除，并按状态规则筛选。

### `commentlike`：评论当前点赞状态

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `id` | bigint | 否 | PK，自增关系 ID。 |
| `userid` | int | 否 | FK → `user.userid`。 |
| `commentid` | bigint | 否 | FK → `moviecomment.commentid`。 |
| `is_active` | tinyint(1) | 否 | 当前点赞状态，默认 1；取消后为 0。 |
| `created_at` / `updated_at` | datetime(6) | 否 | 点赞关系创建和最近状态改变时间。 |

约束：PK `id`；UQ `uk_commentlike_user_comment(userid, commentid)` 保证每人每条评论只有一个当前状态行；IDX `idx_commentlike_comment_active(commentid, is_active)`；两个 FK 均为 RESTRICT。重点赞更新现有行，而非插入重复当前状态。

### `commentlike_event`：点赞操作日志

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `eventid` | bigint | 否 | PK，自增事件 ID。 |
| `userid` | int | 否 | FK → `user.userid`。 |
| `commentid` | bigint | 否 | FK → `moviecomment.commentid`。 |
| `action` | varchar(10) | 否 | `like` 或 `unlike`。 |
| `created_at` | datetime(6) | 否 | 操作发生时间。 |

约束：PK `eventid`；CK `chk_commentlike_event_action`；IDX `idx_commentlike_event_comment_created(commentid, created_at)`、`idx_commentlike_event_user_created(userid, created_at)`；两个 FK 均为 RESTRICT。该表只追加事件，按要求不设自动清理期限。

### `commentreport`：评论举报与结案

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `reportid` | bigint | 否 | PK，自增举报 ID。 |
| `commentid` | bigint | 否 | FK → `moviecomment.commentid`。 |
| `reporter_userid` | int | 否 | FK → `user.userid`。 |
| `reason_code` | varchar(40) | 否 | 举报原因代码。 |
| `reason_detail` | varchar(500) | 是 | 选择 `other` 时必填。 |
| `status` | varchar(20) | 否 | 默认 `pending`；允许 `pending`、`accepted`、`rejected`。 |
| `created_at` | datetime(6) | 否 | 举报时间。 |
| `handled_at` | datetime(6) | 是 | 后台结案时间。 |
| `handled_by_adminid` | int | 是 | FK → `adminuser.adminid`；删除管理员时设为 NULL。 |

约束：PK `reportid`；UQ `uk_commentreport_reporter_comment(reporter_userid, commentid)` 限制同一用户对同一评论只能举报一次；IDX `idx_commentreport_status_created(status, created_at)`；FK `fk_commentreport_comment`、`fk_commentreport_reporter` 为 RESTRICT，`fk_commentreport_admin` 为 SET NULL。原因代码：`malicious_attack`、`insulting_language`、`harmful_information`、`excessive_promotion`、`advertisement`、`other`。CK `chk_commentreport_reason`、`chk_commentreport_other_detail`、`chk_commentreport_status` 校验原因、其他原因详情及状态。

### `userfavorite`：用户电影收藏

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `id` | bigint | 否 | PK，自增收藏关系 ID。 |
| `userid` | int | 否 | FK → `user.userid`。 |
| `movieid` | int | 否 | FK → `movieinfo.movieid`。 |
| `status` | varchar(30) | 否 | `want_to_watch` 或 `watched`。 |
| `created_at` / `updated_at` | datetime(6) | 否 | 关系创建和最近更新时间。 |
| `deleted_at` | datetime(6) | 是 | 取消收藏时间；NULL 为当前有效收藏。 |

约束：PK `id`；UQ `uk_userfavorite_user_movie(userid, movieid)`；IDX `idx_userfavorite_user_status_deleted(userid, status, deleted_at)`、`idx_userfavorite_movie_status_deleted(movieid, status, deleted_at)`；FK 均为 RESTRICT。取消收藏保留行并设置 `deleted_at`；再次收藏恢复原行、清空 `deleted_at` 并更新 `updated_at`。同一用户对同一电影始终复用一条关系。

### `adminoperationlog`：管理员操作审计

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `logid` | bigint | 否 | PK，自增日志 ID。 |
| `adminid` | int | 否 | FK → `adminuser.adminid`。 |
| `action` | varchar(100) | 否 | 操作类型。 |
| `target_type` | varchar(50) | 否 | 操作目标类型。 |
| `target_id` | varchar(100) | 是 | 目标 ID，以字符串兼容不同实体主键类型。 |
| `detail` | json | 是 | 扩展操作明细。 |
| `created_at` | datetime(6) | 否 | 操作时间。 |

约束：PK `logid`；IDX `idx_adminoperationlog_admin_created(adminid, created_at)`、`idx_adminoperationlog_target(target_type, target_id)`；FK `fk_adminoperationlog_admin` 为 RESTRICT。日志按要求长期保留，不设置自动过期。

### `recommendationitem`：推荐批次中的电影项

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `recommendationid` | bigint | 否 | PK，自增推荐项 ID。 |
| `request_id` | varchar(64) | 否 | 一次推荐请求/批次标识。 |
| `userid` | int | 否 | FK → `user.userid`；只面向登录用户推荐。 |
| `movieid` | int | 否 | FK → `movieinfo.movieid`。 |
| `position` | int | 否 | 该电影在本批次的排序位置。 |
| `movie_rating_snapshot` | decimal(4,1) | 是 | 生成时电影业务评分快照，不是 ALS 预测值。 |
| `prediction_score` | decimal(10,6) | 是 | ALS 或其他算法的预测分/排序分。 |
| `algorithm_version` | varchar(100) | 是 | 算法或模型版本标识。 |
| `generated_at` | datetime(6) | 否 | 推荐项生成时间。 |

约束：PK `recommendationid`；UQ `uk_recommendationitem_request_movie(request_id, movieid)`，避免一个请求重复推荐同一电影；IDX `idx_recommendationitem_user_generated(userid, generated_at)`；FK 用户和电影均为 RESTRICT。当前没有独立推荐请求表，`request_id` 的用户归属和位置唯一性由应用保证。

### `recommendationevent`：推荐曝光与反馈事件

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `eventid` | bigint | 否 | PK，自增事件 ID。 |
| `recommendationid` | bigint | 否 | FK → `recommendationitem.recommendationid`。 |
| `event_type` | varchar(20) | 否 | `impression`、`click` 或 `not_interested`。 |
| `created_at` | datetime(6) | 否 | 事件时间。 |

约束：PK `eventid`；CK `chk_recommendationevent_type`；IDX `idx_recommendationevent_type_created(event_type, created_at)`、`idx_recommendationevent_item_type(recommendationid, event_type)`；FK `fk_recommendationevent_item` 为 RESTRICT。曝光应在推荐项实际进入可视区域时记录。用户和电影信息通过推荐项连接取得；同一推荐项可有多个行为事件。曝光去重、CTR 分母、点击归因窗口和重复点击口径仍需由分析规范确定。

## 兼容与迁移辅助表

### `recommendresult`：旧版推荐结果兼容表

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `userid` | int | 是 | 旧结果中的用户 ID；无 FK。 |
| `movieid` | int | 是 | 旧结果中的电影 ID；无 FK。 |
| `rating` | float | 是 | **电影评分**，不是 ALS 预测分。 |
| `moviename` | varchar(1000) | 是 | 电影名快照。 |

旧表无 PK、FK、索引、批次、位置、算法版本或曝光反馈字段，不能还原历史推荐反馈。当前 ORM 未映射此表；保留、下线或迁移至 `recommendationitem` 的计划需结合旧接口确认。

### `aerich`：迁移版本元数据

| 字段 | 类型 | 可空 | 说明 |
|---|---|---:|---|
| `id` | int | 否 | PK，自增内部 ID。 |
| `version` | varchar(255) | 否 | 已应用迁移文件名。 |
| `app` | varchar(100) | 否 | Tortoise app 名称。 |
| `content` | json | 否 | Aerich 保存的模型状态快照。 |

该表由 Aerich 使用，不承载业务数据；不要手工编辑或清空。当前首个已应用迁移为 `1_schema_upgrade.py`。

## 分析指标与关联路径

| 指标 | 主要数据源 | 关键过滤/连接 |
|---|---|---|
| 站内评分分布、电影评分均值和人数 | `personalratings` | 按 `rating`、`movieid` 聚合；若显示有效电影则连接 `movieinfo` 并排除软删除电影。 |
| 离线数据集评分分布 | `trainingrating`、`trainingdataset` | 通过 `datasetid` 分数据集；不要把 `external_userid` 当作 `user.userid`。 |
| 评论数与审核队列 | `moviecomment` | 统计前排除 `deleted_at` 非 NULL；按 `moderation_status` 分组。 |
| 点赞当前量 | `commentlike` | 过滤 `is_active = 1`。 |
| 点赞/取消操作量 | `commentlike_event` | 按 `action`、`created_at` 聚合。 |
| 举报量、待处理量、处理时长 | `commentreport` | 按 `status`、`created_at` 聚合；处理时长由 `handled_at - created_at` 计算。 |
| 想看/已看数量 | `userfavorite` | 排除 `deleted_at` 非 NULL，按 `status` 聚合。 |
| 推荐曝光、点击、不感兴趣 | `recommendationevent` + `recommendationitem` | 事件关联推荐项以取得用户、电影、批次、位置和算法版本；指标去重与分母尚未定义。 |
| 管理操作量 | `adminoperationlog` | 按管理员、操作类型、目标和 UTC 时间范围聚合。 |

## 数据处理交接注意事项

- ALS 显式评分源以 `personalratings` 的当前有效评分为准；若合并外部数据，再读取 `trainingrating` 并在 Spark 侧构造不冲突的用户索引。应用用户表为空时，不能把外部评分伪造成站内用户评分。
- 电影 ID 由输入数据提供。外部数据集的电影 ID 必须先映射到 `movieinfo.movieid`；不能确认映射时应在导入层保留外部电影键并隔离未匹配行，当前 schema 尚无通用电影映射表。
- `movieinfo.averating/numrating` 与 `personalratings` 聚合结果可能来自不同来源；下游报表和推荐特征必须标注使用哪种口径。
- 训练任务、数据快照版本、评估指标、模型文件位置、任务状态和模型发布/回滚不由当前业务表管理。其持久化位置与 Celery/Spark 作业契约需另行确定；Redis 只作为任务消息代理/短期状态后端。
- MySQL 外键限制物理删除，但软删除不自动级联。分析查询、ALS 数据抽取和推荐候选过滤都必须明确是否排除已软删除的用户、电影、评论或分类。

## 当前限制与待定口径

- `trainingdataset` 目前只有名称和评分范围，缺少数据版本、来源许可、校验和、导入状态及记录数等可复现性元数据。
- `personalratings` 只保存当前评分；若要分析评分修改历史，需要新增追加式评分事件表。
- 推荐批次尚无独立父实体，不能单独保存请求级状态、候选数量或失败信息；目前只可从推荐项的 `request_id` 聚合。
- 曝光/点击事件的幂等键、去重窗口、CTR 分母、“不感兴趣”率定义及推荐请求失败统计口径待确认。
- `recommendresult` 是否仍被现有接口使用及其退役时间待确认。
