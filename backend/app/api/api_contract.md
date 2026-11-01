# 电影推荐系统 API 契约

本文按当前 FastAPI OpenAPI 中注册的接口整理，供前端联调。接口实现是请求和响应的实际依据；未注册为 HTTP 路由的数据分析能力不属于本契约。当前 OpenAPI 包含 53 个 method/path 操作（含 `GET /`）。

## 连接与通用约定

- 本地地址：`http://127.0.0.1:8000`；Swagger：`/docs`；OpenAPI：`/openapi.json`。
- 除头像注册外，请求体均为 JSON，使用 `Content-Type: application/json`。头像注册使用 `multipart/form-data`。
- 受保护的用户接口使用 `Authorization: Bearer <access_token>`；管理员接口使用管理员登录得到的 access token。不可将 refresh token 用作 Bearer token。
- 用户登录 `POST /api/auth/login` 返回 access token 有效期 900 秒、refresh token 有效期 604800 秒。管理员登录返回相同期限。刷新接口需在 JSON 请求体中传 refresh token。
- HTTP 状态码是请求结果依据；成功响应通常包含 `code`，但 `data`、`msg` 等字段因接口而异。不要假设所有接口都有相同的响应外壳。
- 请求校验失败通常为 `422`；业务错误为 JSON `detail`。全局异常响应为 `{"code":500,"detail":"服务器内部错误"}`。
- 常见状态：`201` 创建成功；`202` 任务已接受；`400` 业务操作失败；`401` 凭据缺失/无效/过期；`403` 角色或资源所有权不符；`404` 资源不存在或已软删除；`409` 唯一性/状态冲突；`413` 头像超过 5 MiB；`415` 头像类型不接受；`422` 参数校验失败；`429` 找回密码请求冷却；`502` 邮件发送失败；`503` 相关服务未配置或不可用。
- Swagger 的 **Authorize** 使用隐藏的 OAuth2 表单接口 `/api/auth/token`：填账号到 `username`、密码到 `password`。该接口不在 OpenAPI 路由清单中；普通前端登录应调用 JSON 接口 `/api/auth/login`。

## 接口索引

| 方法 | 路径 | 权限 | 用途 |
|---|---|---|---|
| GET | `/` | 公开 | 根状态信息 |
| POST | `/api/auth/register` | 公开 | JSON 注册 |
| POST | `/api/auth/register-with-avatar` | 公开 | multipart 注册及头像文件 |
| POST | `/api/auth/login` | 公开 | 用户登录 |
| POST | `/api/auth/refresh` | 公开，需 refresh token | 刷新用户令牌 |
| POST | `/api/auth/logout` | 用户 | 用户退出 |
| GET | `/api/auth/me` | 用户 | 当前用户资料 |
| PUT | `/api/auth/me` | 用户 | 更新当前用户资料 |
| PUT | `/api/auth/me/password` | 用户 | 修改密码 |
| POST | `/api/auth/forgot-password/request` | 公开 | 请求邮箱验证码 |
| POST | `/api/auth/forgot-password/confirm` | 公开 | 验证并重置密码 |
| GET | `/api/movies/random` | 公开 | 随机电影，最多 10 部 |
| GET | `/api/movies` | 公开 | 电影搜索、筛选、排序、分页 |
| GET | `/api/movies/{movieid}` | 公开 | 电影详情和分类 |
| POST | `/api/movies` | 管理员 | 新建电影 |
| PUT | `/api/movies/{movieid}` | 管理员 | 更新电影 |
| DELETE | `/api/movies/{movieid}` | 管理员 | 软删除电影 |
| GET | `/api/movies/categories` | 公开 | 分类列表 |
| POST | `/api/movies/categories` | 管理员 | 新建分类 |
| PUT | `/api/movies/categories/{categoryid}` | 管理员 | 修改分类 |
| DELETE | `/api/movies/categories/{categoryid}` | 管理员 | 软删除分类 |
| GET | `/api/ratings/me` | 用户 | 当前用户评分列表 |
| POST | `/api/ratings/submit` | 用户 | 批量新增或更新评分 |
| GET | `/api/favorites/me` | 用户 | 当前用户收藏列表 |
| POST | `/api/favorites/toggle` | 用户 | 新增、更新、取消或恢复收藏 |
| GET | `/api/comments/movies/{movieid}/comments` | 公开 | 电影评论列表 |
| POST | `/api/comments` | 用户 | 发布评论 |
| GET | `/api/comments/me` | 用户 | 当前用户评论列表 |
| DELETE | `/api/comments/{commentid}` | 评论作者 | 软删除自己的评论 |
| POST | `/api/comments/{commentid}/like` | 用户 | 切换点赞状态 |
| POST | `/api/comments/{commentid}/reports` | 用户 | 举报评论 |
| GET | `/api/comments/admin/reports` | 管理员 | 举报列表 |
| PUT | `/api/comments/admin/reports/{reportid}` | 管理员 | 处理举报 |
| DELETE | `/api/comments/admin/{commentid}` | 管理员 | 管理员软删除评论 |
| POST | `/api/recommend/generate` | 用户 | 提交推荐任务 |
| GET | `/api/recommend/result` | 用户 | 查询当前用户推荐结果 |
| GET | `/api/recommend/result/{userid}` | 用户，仅本人 | 按用户 ID 查询推荐结果 |
| GET | `/api/recommend/similar/{movieid}` | 公开 | 相似电影列表 |
| POST | `/api/recommend/event` | 用户 | 记录推荐行为事件 |
| POST | `/api/admin/register` | Bootstrap Header | 注入普通管理员或超级管理员 |
| POST | `/api/admin/login` | 公开 | 管理员登录 |
| POST | `/api/admin/refresh` | 公开，需管理员 refresh token | 刷新管理员令牌 |
| POST | `/api/admin/logout` | 管理员 | 管理员退出 |
| GET | `/api/admin/me` | 管理员 | 当前管理员资料 |
| GET | `/api/admin/users` | 超级管理员 | 用户列表 |
| PUT | `/api/admin/users/{userid}` | 超级管理员 | 启用或禁用用户 |
| DELETE | `/api/admin/users/{userid}` | 超级管理员 | 软删除用户 |
| GET | `/api/admin/accounts` | 超级管理员 | 管理员账号列表 |
| POST | `/api/admin/accounts` | 超级管理员 | 创建管理员账号 |
| PUT | `/api/admin/accounts/{adminid}` | 超级管理员 | 修改管理员角色/状态 |
| DELETE | `/api/admin/accounts/{adminid}` | 超级管理员 | 软删除管理员账号 |
| GET | `/api/admin/audit/logs` | 管理员 | 管理操作日志 |
| GET | `/api/admin/audit/like-events` | 管理员 | 评论点赞操作历史 |

未计入以上 OpenAPI 清单的隐藏兼容路由：`POST /api/auth/token`（Swagger OAuth2 表单）和 `POST /api/auth/register-legacy`。它们不作为前端业务 API 使用。

## 请求和响应

### 认证与账号

**注册** `POST /api/auth/register`：JSON 字段 `username`（2-50 字符）、`password` 和 `confirm_password`（8-255 字符，含字母和数字且相同）、`email`（有效邮箱）、`phone`（1-32 位数字）；`avatar` 可选字符串。昵称、邮箱按不区分大小写的方式检查冲突，邮箱保存为小写。示例：

```json
{"username":"movie_fan","password":"Movie1234","confirm_password":"Movie1234","email":"fan@example.com","phone":"13800138000","avatar":null}
```

成功 HTTP `201`，返回 `code`、`msg`、`userid`。账号冲突 `409`。

**头像注册** `POST /api/auth/register-with-avatar`：multipart 字段为 `username`、`password`、`confirm_password`、`email`、`phone`，另有可选文件 `avatar`。文件上限 5 MiB；实现按上传 MIME 类型或扩展名校验，不等同于对图片内容解码验证。成功响应同 JSON 注册。

**用户登录** `POST /api/auth/login`：`{"account":"13800138000","password":"Movie1234"}`。`account` 可为昵称、手机号或邮箱；兼容字段名 `username` 也可作为账号。成功返回 `access_token`、`refresh_token`、`token_type`、`expires_in`（900）、`refresh_expires_in`（604800）及 `userid`。无效凭据 `401`。

**刷新令牌** `POST /api/auth/refresh`：`{"refresh_token":"<user-refresh-token>"}`。成功返回 `code` 和 `data` 中的新令牌对及有效秒数。

**退出** `POST /api/auth/logout`：无请求体，需用户 Bearer token。服务端递增账号 `token_version`，当前及更早签发的令牌立即失效；客户端仍应清除本地令牌。

**当前资料** `GET /api/auth/me` 返回 `data` 中的 `userid, username, email, phone, avatar`。`PUT /api/auth/me` 接收这些可更新字段的非空子集；身份字段不能设为 null，`avatar` 可设为 null 清除。空对象 `422`，冲突 `409`。

**修改密码** `PUT /api/auth/me/password`：`{"old_password":"Movie1234","new_password":"Movie5678"}`。新密码 8-255 位且包含字母和数字；原密码错误 `400`。

**申请重置码** `POST /api/auth/forgot-password/request`：`{"email":"fan@example.com"}`。未知邮箱使用通用成功提示；请求间隔 60 秒，验证码 10 分钟过期、最多尝试 5 次。需要 SMTP 配置。验证码当前保存在 API 进程内，多 worker 不共享且服务重启后丢失。

**确认重置** `POST /api/auth/forgot-password/confirm`：`{"email":"fan@example.com","code":"123456","new_password":"Movie5678"}`。验证码必须是 6 位数字；密码需 8-255 位并包含字母、数字。

### 电影与分类

- `GET /api/movies/random`：无参数，返回 `data` 数组，最多 10 部有效电影，每项含 `movieid,moviename,picture`。
- `GET /api/movies`：查询参数 `q`（电影名模糊查询，最多 100 字符）、`category_id`（正整数）、`sort_by=rating|popularity|release_time`（默认 `rating`）、`order=asc|desc`（默认 `desc`）、`page`（默认 1，最小 1）、`page_size`（默认 20，范围 1-100）。响应 `data={items,total,page,page_size}`；列表项含 `movieid,moviename,picture,averating,numrating,releasetime`。无效/已删除分类返回 `404`。列表缓存 TTL 为 120 秒。
- `GET /api/movies/{movieid}`：返回 `data` 中电影详情字段 `movieid,moviename,releasetime,director,leadactors,picture,averating,numrating,description,typelist,categories`；`categories` 是 `{categoryid,name}` 数组，无分类时为空数组。缺失或已删除电影 `404`。
- `GET /api/movies/categories`：返回有效分类的 `data` 数组，每项 `{categoryid,name}`。
- `POST /api/movies`：管理员创建电影。必填正整数 `movieid`、`moviename`；可选 `releasetime`（`YYYY-MM-DD`）、`director,leadactors,picture,description,typelist`、`category_ids`（最多 100 个分类 ID）。`movieid` 沿用现有数据主键，不自动生成。成功 `201`。
- `PUT /api/movies/{movieid}`：管理员可提交上述可更新字段的非空子集；`category_ids` 一旦提供即替换全部关联，空数组清空关联。
- `DELETE /api/movies/{movieid}`：管理员软删除电影。
- `POST /api/movies/categories`：管理员 JSON `{"name":"Drama"}`，成功 `201`。
- `PUT /api/movies/categories/{categoryid}`：管理员 JSON `{"name":"New name"}`。
- `DELETE /api/movies/categories/{categoryid}`：管理员软删除分类并清除电影分类关联。

### 评分、收藏与评论

**评分提交** `POST /api/ratings/submit`：

```json
{"movieids":[1,2],"ratings":[9,8]}
```

数组必须非空且长度相同，电影 ID 为正整数且批次内不重复，分数为 1-10 整数。可选兼容字段 `userid` 必须等于 token 用户 ID。已存在评分更新，不存在则新增；写入使用事务。成功返回 `count`。不存在/软删除电影 `404`，用户 ID 不匹配 `403`。

**我的评分** `GET /api/ratings/me`：分页参数 `page` 默认 1、`page_size` 默认 20（1-100）；返回 `data={items,total,page,page_size}`，评分项含 `ratingid,movieid,moviename,picture,rating,rated_at`。

**我的收藏** `GET /api/favorites/me`：相同分页参数，另可传 `status=want_to_watch|watched`。列表项含 `movieid,moviename,picture,status,created_at,updated_at`。

**切换收藏** `POST /api/favorites/toggle`：`{"movieid":1,"status":"want_to_watch"}`，状态也可为 `watched`。新建时添加；对当前相同状态再次调用会软删除；不同状态会更新；对软删除记录调用会恢复。响应 `action` 为 `add|remove|update`。

**电影评论** `GET /api/comments/movies/{movieid}/comments`：分页参数 `page`、`page_size` 同上。返回未删除且对外可见的评论列表，含评论内容、用户信息、点赞数、当前用户 `liked` 状态及分页字段。当前 `review_pending` 评论仍可见。

**发布评论** `POST /api/comments`：`{"movieid":1,"content":"A review"}`，内容去除首尾空格后需 1-500 字符，成功 `201`。

**我的评论** `GET /api/comments/me`：分页参数同上。**删除评论** `DELETE /api/comments/{commentid}`：仅作者可删，软删除。

**点赞** `POST /api/comments/{commentid}/like`：无请求体，切换当前点赞状态并记录操作事件；响应 `data.liked` 表示操作后的状态。

**举报** `POST /api/comments/{commentid}/reports`：原因枚举 `malicious_attack|insulting_language|harmful_information|excessive_promotion|advertisement|other`。`other` 必须提供非空 `reason_detail`（最多 500 字符）；同用户重复举报 `409`。新举报使评论进入 `review_pending`，在管理员结案前仍展示。

**举报列表** `GET /api/comments/admin/reports`：管理员可选查询 `status=pending|accepted|rejected`；返回数组，目前无分页。

**处理举报** `PUT /api/comments/admin/reports/{reportid}`：`{"status":"accepted"}` 或 `{"status":"rejected"}`。接受后评论隐藏，驳回后恢复发布；已处理举报 `409`，不存在 `404`。管理员删除评论：`DELETE /api/comments/admin/{commentid}`，执行软删除。

### 推荐

**生成推荐** `POST /api/recommend/generate`：用户 Bearer token，无请求体。成功 HTTP `202`，返回 `request_id`、Celery `task_id`。队列不可用返回 `503`。

**查询结果** `GET /api/recommend/result` 查询当前用户；`GET /api/recommend/result/{userid}` 只允许查询自己的 ID，否则 `403`。尚无结果时返回空 `items` 和空 `request_id`。结果项包含 `movieid,moviename,picture,position,prediction_score`。

当前 Celery 任务写入的是 popularity 排序的 `popularity-v1` 回退结果，按电影现有平均评分填充 `prediction_score`，并非 ALS 模型预测值。ALS/Spark 算法由算法负责人实现，本契约不承诺其已完成。结果缓存 TTL 为 300 秒。

**相似电影** `GET /api/recommend/similar/{movieid}?limit=10`：公开访问，`limit` 默认 10、范围 1-50；当前使用类型字符串和热度排序回退逻辑。

**推荐事件** `POST /api/recommend/event`：`{"request_id":"<request_id>","movieid":1,"event_type":"impression"}`。事件类型为 `impression|click|not_interested`；请求批次和电影必须属于当前用户且电影有效。

### 管理员与审计

管理员角色：`admin` 为普通管理员；`superadmin` 可管理用户和管理员账号。电影、分类、评论维护及举报处理对两种管理员开放。

**注入管理员** `POST /api/admin/register`：仅用于管理员初始化/数据注入，不提供给前端注册流程。请求头 `X-Admin-Bootstrap-Token: <ADMIN_BOOTSTRAP_TOKEN>`，JSON：

```json
{"username":"root_admin","password":"Admin1234","role":"superadmin"}
```

`role` 为 `admin|superadmin`；密码 8-255 位且包含字母和数字。成功 HTTP `201`；未配置服务端 token 为 `503`，请求头错误 `401`，账号重复 `409`。

**管理员登录** `POST /api/admin/login`：`{"username":"admin","password":"Admin1234"}`。成功返回 `data` 中令牌对、有效时间和 `role`。`POST /api/admin/refresh` 使用 `{"refresh_token":"<admin-refresh-token>"}`。`POST /api/admin/logout` 无请求体，需管理员 token；服务端递增管理员 `token_version`，当前及更早签发的令牌立即失效。`GET /api/admin/me` 返回当前 `adminid,username,role`。

**用户管理**（仅超级管理员）：`GET /api/admin/users` 支持 `page`（默认 1）、`page_size`（默认 20，1-100）、`status=active|disabled`；列表当前也会包含软删除用户。`PUT /api/admin/users/{userid}` 请求 `{"status":"disabled"}` 或 `{"status":"active"}`。`DELETE /api/admin/users/{userid}` 软删除。

**管理员账号管理**（仅超级管理员）：`GET /api/admin/accounts` 无分页；`POST /api/admin/accounts` 请求字段同注入管理员，不需要 Bootstrap Header；`PUT /api/admin/accounts/{adminid}` 可传 `role`、`status`（`active|disabled`）中的一个或两个，例如 `{"role":"admin","status":"active"}`；`DELETE /api/admin/accounts/{adminid}` 软删除。不能禁用或删除当前登录的管理员。

**操作日志** `GET /api/admin/audit/logs`：管理员可查，`page` 默认 1，`page_size` 默认 20（1-100），可选精确筛选 `action`（最多 100 字符）、`target_type`（最多 50 字符）。响应 `data={items,total,page,page_size}`。

**点赞事件日志** `GET /api/admin/audit/like-events`：管理员可查，支持相同分页参数及可选 `action` 筛选，返回 `data={items,total,page,page_size}`。

## 实现边界与联调注意

- `backend/app/analytics.py` 当前没有挂载 FastAPI 路由，因此数据分析需求不是可调用的 HTTP API。
- 根路径 `/` 返回简单服务消息，不代表 MySQL、Redis、SMTP 或 Celery 都通过健康检查。
- API 代码使用的表、列、索引和唯一约束必须与实际 MySQL 数据库一致。本文不创建、迁移或修改数据库结构；部署环境是否已应用迁移需单独核对。
- 报告列表未分页；举报处理、评论状态更新和审计日志写入不是同一事务，数据库异常时可能部分完成。
- 刷新 token 当前未做服务端单次轮换；登出、改密、重置密码以及管理员/用户状态变更会递增 `token_version`，使旧令牌失效。用户/管理员被禁用或软删除后，后续认证请求也会因重新加载账号而失败。
- 静态导入/OpenAPI 检查不等于真实 MySQL、Redis、SMTP、Celery Worker 端到端测试。前端联调前应在目标环境分别验证这些依赖。

## Swagger 联调顺序

1. 从 `backend` 目录启动 API：`uvicorn app.main:app --reload --port 8000`，打开 `http://127.0.0.1:8000/docs`。
2. 调用用户注册、登录。可在 **Authorize** 弹窗输入 OAuth 表单的账号和密码；也可以在业务请求中手动使用登录返回的 access token。
3. 调用个人资料、评分、收藏、评论和推荐接口。头像上传单独调用 `POST /api/auth/register-with-avatar`。
4. 用 `X-Admin-Bootstrap-Token` 初始化管理员，再通过管理员登录获取 token。分别验证普通管理员和超级管理员权限。
5. 使用错误参数验证 `422`，不带 token 验证 `401`，使用错误角色/他人 userid 验证 `403`，重复或不存在资源验证 `409/404`。
6. 对照实际部署数据库中的 `user`、`adminuser`、`movieinfo`、`category`、`moviecategory`、`personalratings`、`userfavorite`、`moviecomment`、`commentlike`、`commentlike_event`、`commentreport`、`adminoperationlog`、`recommendationitem`、`recommendationevent` 表检查落盘。字段和约束以当前 `models.py` 及实际数据库结构为准。
