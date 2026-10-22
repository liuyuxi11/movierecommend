# 电影推荐系统 API 契约

本文档描述当前 FastAPI 实际注册的接口，供前端联调使用。接口共16个方法/路径组合；未实现的规划功能不视为可调用接口。

## 1. 通用约定
### 1.1 基础信息

| 项目 | 约定 |
|---|---|
| Base URL | 部署环境提供，例如 `http://127.0.0.1:8000`；下文路径均相对于 Base URL |
| 请求格式 | JSON 请求使用 `Content-Type: application/json` |
| 认证方式 | 受保护接口使用 `Authorization: Bearer <access_token>` |
| Token 有效期 | 登录成功后签发的 JWT 有效期为 2 小时 |
| 时间 | 服务端按 UTC 处理时间字段；时间响应为 ISO 8601 字符串 |
| API 在线文档 | `<API_BASE_URL>/docs` |
| OpenAPI JSON | `<API_BASE_URL>/openapi.json` |
| 开发 CORS | 默认允许 `http://localhost:5173`；可通过逗号分隔的 `CORS_ORIGINS` 配置 |

账号被禁用或软删除后，即使 JWT 尚未过期，受保护接口也会返回 HTTP `401`。当前没有刷新 Token、退出登录或服务端 Token 撤销接口；修改密码不会主动撤销已签发的 Token。

### 1.2 响应与错误

成功响应的 HTTP 状态码通常为 `200`，注册接口为 `201`。业务成功数据一般包含 `code` 字段，但 HTTP 状态码才是请求结果的权威状态；根路径和推荐结果接口的结构与其他接口不同。
FastAPI 参数校验失败时返回 HTTP `422`，常见结构如下：

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

业务错误通常使用 `{"detail":"错误说明"}`；具体端点可能返回结构化 `detail` 对象。常见状态码：

| HTTP 状态码 | 含义 |
|---|---|
| `400` | 原密码错误 |
| `401` | 登录凭据错误，或缺少/无效/过期的 Bearer Token |
| `403` | 请求中的 `userid` 与当前登录用户不一致 |
| `404` | 电影、分类或当前用户的推荐记录不存在/不可用 |
| `409` | 注册资料冲突或收藏并发冲突 |
| `422` | 请求体或查询参数未通过校验 |
| `503` | 推荐生成任务服务尚未配置 |

## 2. 接口总览

| 方法 | 路径 | 认证 | 功能 |
|---|---|---|---|
| `GET` | `/` | 否 | 服务状态 |
| `POST` | `/api/auth/register` | 否 | 注册 |
| `POST` | `/api/auth/login` | 否 | 登录并获取 JWT |
| `GET` | `/api/auth/me` | 是 | 查询当前用户资料 |
| `PUT` | `/api/auth/me` | 是 | 修改当前用户资料 |
| `PUT` | `/api/auth/me/password` | 是 | 修改密码 |
| `GET` | `/api/movies/random` | 否 | 获取随机电影 |
| `GET` | `/api/movies` | 否 | 分页、搜索、分类筛选和排序 |
| `GET` | `/api/movies/{movieid}` | 否 | 查询电影详情 |
| `POST` | `/api/ratings/submit` | 是 | 批量新增或更新评分 |
| `GET` | `/api/ratings/me` | 是 | 查询当前用户评分 |
| `GET` | `/api/favorites/me` | 是 | 查询当前用户收藏 |
| `POST` | `/api/favorites/toggle` | 是 | 新增、更新或取消收藏 |
| `POST` | `/api/recommend/generate` | 是 | 请求生成推荐；当前返回 `503` |
| `GET` | `/api/recommend/result` | 是 | 查询当前用户最新推荐结果 |
| `POST` | `/api/recommend/event` | 是 | 记录推荐曝光/点击/不感兴趣事件 |

## 3. 服务状态

### `GET /`

- 认证：不需要。
- 成功：HTTP `200`。

```json
{"message":"后端启动成功，数据库已连接！"}
```

## 4. 用户与认证

认证接口前缀为 `/api/auth`。登录账号可使用昵称、手机号或邮箱。昵称与邮箱按不区分大小写的方式查找；手机号按数字字符串匹配。

### `POST /api/auth/register`

- 认证：不需要。
- 成功：HTTP `201`。
- 请求体：
| 字段 | 类型 | 必填 | 约束 |
|---|---|---:|---|
| `username` | string | 是 | 2–50 字符；首尾空白会被去除 |
| `password` | string | 是 | 8–255 字符，至少包含一个英文字母和一个数字 |
| `confirm_password` | string | 是 | 8–255 字符，必须与 `password` 相同 |
| `email` | string | 是 | 有效邮箱，最多 254 字符；保存前转为小写 |
| `phone` | string | 是 | 1–32 位数字，不允许其他字符 |
| `avatar` | string \| null | 否 | 最多 1000 字符；可省略或为 `null` |

```json
{
  "username": "film_fan",
  "password": "Movie1234",
  "confirm_password": "Movie1234",
  "email": "fan@example.com",
  "phone": "13800138000",
  "avatar": "https://example.com/avatar.jpg"
}
```

成功响应：

```json
{"code":201,"msg":"注册成功","userid":123}
```

昵称（忽略大小写）、手机号或邮箱与未软删除账号重复时返回 HTTP `409`。

### `POST /api/auth/login`

- 认证：不需要。
- 成功：HTTP `200`。
- 请求字段：`account` 为规范字段；为兼容旧请求，也接受 `username`。
- `account` 可填写昵称、手机号或邮箱。

```json
{"account":"13800138000","password":"Movie1234"}
```

兼容格式：

```json
{"username":"film_fan","password":"Movie1234"}
```

成功响应：

```json
{
  "code":200,
  "msg":"登录成功",
  "access_token":"<JWT>",
  "token_type":"bearer",
  "userid":123
}
```

账号或密码错误返回 HTTP `401`。

### `GET /api/auth/me`

- 认证：需要 Bearer Token。
- 成功：HTTP `200`。

```json
{
  "code":200,
  "data":{
    "userid":123,
    "username":"film_fan",
    "email":"fan@example.com",
    "phone":"13800138000",
    "avatar":"https://example.com/avatar.jpg"
  }
}
```

### `PUT /api/auth/me`

- 认证：需要 Bearer Token。
- 成功：HTTP `200`。
- 可修改字段：`username`、`email`、`phone`、`avatar`。只提交需要修改的字段；未提交字段保持不变。
- `username`、`email`、`phone` 不能显式传 `null`；`avatar` 可传 `null` 清除头像。
- 昵称长度为 2–50；邮箱必须有效且最多 254 字符；手机号为 1–32 位数字。
- 空请求体返回 `422`。昵称、手机号或邮箱与其他未软删除账号重复时返回 `409`。

```json
{"username":"movie_fan","avatar":null}
```

成功响应：

```json
{"code":200,"msg":"资料修改成功"}
```

### `PUT /api/auth/me/password`

- 认证：需要 Bearer Token。
- 成功：HTTP `200`。
- 新密码长度为 8–255，且必须包含英文字母和数字。

```json
{"old_password":"Movie1234","new_password":"NewMovie5678"}
```

成功响应：`{"code":200,"msg":"密码修改成功"}`。原密码错误返回 HTTP `400`。修改密码后，已签发 Token 仍可继续使用，直到过期或账号被禁用/软删除。

## 5. 电影

电影查询接口不需要认证；所有电影查询均排除 `deleted_at` 非空的软删除电影。当前没有分类列表接口。

### `GET /api/movies/random`

- 认证：不需要。
- 成功：HTTP `200`。
- 从按 `movieid` 升序的有效电影中随机选择起始位置，返回最多 10 条连续记录。
- 空库返回 `{"code":200,"data":[]}`。

```json
{
  "code":200,
  "data":[
    {"movieid":1,"moviename":"电影名称","picture":"https://example.com/movie.jpg"}
  ]
}
```

### `GET /api/movies`

- 认证：不需要。
- 成功：HTTP `200`。
- 查询参数：
| 参数 | 类型 | 默认值 | 约束与说明 |
|---|---|---:|---|
| `q` | string | 无 | 最多 100 字符；按电影名模糊搜索，不搜索导演或演员 |
| `category_id` | integer | 无 | 正整数；分类不存在或已软删除时返回 `404` |
| `sort_by` | string | `rating` | `rating`、`popularity`、`release_time`；`popularity` 按评分人数 `numrating` 排序 |
| `order` | string | `desc` | `asc` 或 `desc` |
| `page` | integer | `1` | 大于等于 1 |
| `page_size` | integer | `20` | 1–100 |

示例：`GET /api/movies?q=%E6%98%9F&category_id=2&page=1&page_size=20&sort_by=rating&order=desc`

成功响应中的 `data.items` 每项包含 `movieid`、`moviename`、`picture`、`averating`、`numrating`、`releasetime`；除 `movieid` 外，电影资料字段可能为 `null`。

```json
{
  "code":200,
  "data":{
    "items":[
      {
        "movieid":1,
        "moviename":"电影名称",
        "picture":"https://example.com/movie.jpg",
        "averating":8.5,
        "numrating":120,
        "releasetime":"2024-01-01"
      }
    ],
    "total":1,
    "page":1,
    "page_size":20
  }
}
```

没有匹配项时 `items` 为空数组，`total` 为 `0`。当前没有分类枚举接口，前端需要从其他已约定来源取得 `category_id`。

### `GET /api/movies/{movieid}`

- 认证：不需要。
- 路径参数：`movieid`，整数。
- 成功：HTTP `200`；电影不存在或已软删除返回 HTTP `404`。
- `data` 包含 `movieid`、`moviename`、`releasetime`、`director`、`leadactors`、`picture`、`averating`、`numrating`、`description`、`typelist`。除 `movieid` 外字段可能为 `null`。

```json
{
  "code":200,
  "data":{
    "movieid":1,
    "moviename":"电影名称",
    "releasetime":"2024-01-01",
    "director":"导演",
    "leadactors":"主演",
    "picture":"https://example.com/movie.jpg",
    "averating":8.5,
    "numrating":120,
    "description":"电影简介",
    "typelist":"剧情,科幻"
  }
}
```

## 6. 评分

评分接口需要 Bearer Token。评分用户始终由 Token 确定。

### `POST /api/ratings/submit`

- 成功：HTTP `200`。
- `movieids` 与 `ratings` 必须为非空数组且长度一致；电影 ID 必须为正整数且同一批次不可重复；评分必须为 1–10 的整数。
- 每个用户对同一电影只有一条评分；重复提交会更新评分。整批写入在同一数据库事务中完成。
- 可选字段 `userid` 仅为兼容旧请求；若传入，必须与 Token 用户 ID 一致。

```json
{
  "movieids":[1,2],
  "ratings":[9,7]
}
```

成功响应：

```json
{"code":200,"msg":"评分提交成功","count":2}
```

`userid` 不匹配返回 `403`；电影不存在或已软删除返回 `404`，其 `detail` 包含缺失 ID：

```json
{"detail":{"message":"电影不存在或已删除","movieids":[2]}}
```

### `GET /api/ratings/me`

- 认证：需要 Bearer Token。
- 查询参数：`page` 默认 `1` 且大于等于 1；`page_size` 默认 `20`，范围 1–100。
- 按评分时间从新到旧分页；只返回关联电影未软删除的评分。
- 成功响应项包含 `ratingid`、`movieid`、`moviename`、`picture`、`rating`、`rated_at`。

```json
{
  "code":200,
  "data":{
    "items":[
      {
        "ratingid":10,
        "movieid":1,
        "moviename":"电影名称",
        "picture":null,
        "rating":9,
        "rated_at":"2026-10-22T08:00:00Z"
      }
    ],
    "total":1,
    "page":1,
    "page_size":20
  }
}
```

## 7. 收藏

收藏接口需要 Bearer Token。`status` 可取 `want_to_watch`（想看）或 `watched`（已看）。

### `GET /api/favorites/me`
- 查询当前用户未取消、且关联电影未软删除的收藏。
- 查询参数：`page` 默认 `1` 且大于等于 1；`page_size` 默认 `20`，范围 1–100；`status` 可选，值为 `want_to_watch` 或 `watched`。
- 成功响应项包含 `movieid`、`moviename`、`picture`、`status`、`created_at`、`updated_at`。

示例：`GET /api/favorites/me?status=want_to_watch&page=1&page_size=20`

```json
{
  "code":200,
  "data":{
    "items":[
      {
        "movieid":1,
        "moviename":"电影名称",
        "picture":"https://example.com/movie.jpg",
        "status":"want_to_watch",
        "created_at":"2026-10-22T08:00:00Z",
        "updated_at":"2026-10-22T08:00:00Z"
      }
    ],
    "total":1,
    "page":1,
    "page_size":20
  }
}
```

### `POST /api/favorites/toggle`

- 请求体：
```json
{"movieid":1,"status":"want_to_watch"}
```

- `movieid` 必须为正整数；`status` 必须为 `want_to_watch` 或 `watched`。
- 首次请求新增收藏；已有软删除记录时恢复；已收藏且状态相同则软删除取消；状态不同时更新状态。
- 电影不存在或已软删除返回 `404`；并发唯一性冲突返回 `409`。

| 结果 | `action` | `msg` |
|---|---|---|
| 新增或恢复 | `add` | `收藏成功` |
| 取消 | `remove` | `已取消收藏` |
| 修改状态 | `update` | `收藏状态已更新` |

成功响应示例：`{"code":200,"msg":"收藏成功","action":"add"}`。

## 8. 推荐

推荐接口需要 Bearer Token，推荐结果与事件均限定为当前登录用户。

### `POST /api/recommend/generate`

- 当前 Celery/Spark 推荐任务服务尚未配置。
- 此接口目前固定返回 HTTP `503`，不会创建任务或返回 `request_id`。

```json
{"detail":"推荐生成任务服务尚未配置"}
```

### `GET /api/recommend/result`

- 查询当前用户最新一批已持久化推荐，不接受用户 ID 参数。
- 成功：HTTP `200`。没有结果时返回 `request_id: null` 和空 `items`。
- 推荐项包含 `movieid`、`moviename`、`position`、`prediction_score`；`prediction_score` 可能为 `null`。已软删除电影会从响应中排除。

```json
{
  "code":200,
  "request_id":"request-id",
  "items":[
    {"movieid":1,"moviename":"电影名称","position":1,"prediction_score":4.8}
  ]
}
```

### `POST /api/recommend/event`

- 请求体：
| 字段 | 类型 | 约束 |
|---|---|---|
| `request_id` | string | 1–64 字符 |
| `movieid` | integer | 正整数 |
| `event_type` | string | `impression`、`click` 或 `not_interested` |

```json
{
  "request_id":"request-id",
  "movieid":1,
  "event_type":"impression"
}
```

推荐项属于当前用户且电影有效时，成功响应为 HTTP `200`：`{"code":200,"msg":"事件已记录"}`。推荐项不属于当前用户，或电影不存在/已软删除时返回 `404`。每次成功请求都会新增事件记录，服务端不做重复事件去重；曝光事件应在推荐项实际进入可视区域后发送。

## 9. 当前未提供的接口
以下功能尚无可调用 API：分类列表/详情与管理、评论发布/查询、点赞、举报与审核、管理员管理、用户禁用/恢复、找回密码、退出登录/服务端 Token 撤销、ALS 推荐生成任务、数据分析。电影列表虽支持 `category_id` 筛选，但没有分类枚举接口；电影搜索目前只匹配电影名。数据库中存在相关模型或表，不代表对应 API 已实现。
