# ALS 推荐任务本地演示

## 架构

离线 `als_recommender.py` 训练一次模型并发布不可变批次目录：

```text
<ALS_RECOMMENDATION_ROOT>/
  latest.json
  batches/<batch-id>/users/<userid>.jsonl
```

JSONL 由 Python 从 Spark DataFrame 的 `toLocalIterator()` 流式写入，不使用 Spark/Hadoop 本地文件写入，因此不依赖 Windows `winutils.exe`。离线作业先完成候选生成和完整性检查，再将 `latest.json` 原子切换到新批次。API 与 Worker 必须能访问同一个根目录。

每个用户文件含有该用户的 `userid`、`movieid`、`position`、离线 `prediction_score`、电影评分快照、算法版本和生成时间。Worker 使用候选 `position` 表示离线排序信号，不把离线分数直接作为前端分数；在线排序分由 Worker 按当前候选列表重新计算。Worker 使用 API 提供的 request_id，不复用离线 batch id。

## 环境变量

本地忽略的 `.env` 中配置以下内容；不要把凭据提交到仓库：

- `DATABASE_URL`：指向 `movierecommend_test` 的只读连接，用于用户、评分、电影和既有推荐查询。
- `MYSQL_JDBC_URL`、`MYSQL_USER`、`MYSQL_PASSWORD`：ALS 离线抽取只读账号，JDBC schema 必须是 `movierecommend_test`，时区设置为 UTC。
- `RECOMMENDATION_WRITE_ENABLED=YES`：明确开启测试写入。未设置时 Worker 拒绝执行。
- `RECOMMENDATION_WRITE_URL`：单独的测试库写账号 URL，必须指向 `movierecommend_test`；账号只授予 `recommendationitem` 的 INSERT 权限。request_id 幂等查询由 `DATABASE_URL` 只读账号执行；外键由 MySQL 约束检查。
- `REDIS_URL` 与 `CELERY_RESULT_BACKEND`：本地 Redis 地址；若未单独配置结果后端，Celery 默认复用 broker 地址。
- `ALS_RECOMMENDATION_ROOT`：API、Worker 和离线作业共同访问的目录，例如仓库下的 `data/processed/als-recommendations`。
- `RECOMMENDATION_CACHE_TTL=300`：JSON 缓存秒数。在线列表上限固定为 Top-20，界面、Mock 和 Worker 共用该目标。
- `REDIS_SOCKET_TIMEOUT=1`：缓存读写连接超时秒数。

代码硬性要求 source URL 与 writer URL 的数据库名都等于 `movierecommend_test`，并在 writer 建连后再次执行 `SELECT DATABASE()` 检查。不要将写账号用于 ALS 评分抽取。

## 离线发布

从项目根目录使用虚拟环境执行；`MYSQL_JDBC_URL` 必须是测试 schema 的只读 JDBC URL，Connector/J 通过 Spark classpath 提供：

```powershell
$env:ALS_RECOMMENDATION_ROOT = Join-Path $PWD 'data/processed/als-recommendations'
$batch = [guid]::NewGuid().ToString('N')
& .\.venv_new\Scripts\spark-submit.cmd `
  --master 'local[2]' `
  --jars 'C:\drivers\mysql-connector-j-8.0.33.jar' `
  backend/jobs/als_recommender.py `
  --no-snapshot `
  --batch-id $batch `
  --checkpoint-interval -1 `
  --jsonl-recommendations-root $env:ALS_RECOMMENDATION_ROOT `
  --metadata-path (Join-Path $env:ALS_RECOMMENDATION_ROOT "batches/$batch/metadata.json")
```

离线作业会用 Python 本地文件 API 写 JSONL 和元数据；训练过程本身仍需在支持的 Spark/Java 环境运行。`--checkpoint-interval -1` 避免该课程演示依赖 checkpoint 文件。

## Redis 与 Celery 启动/自检

需先启动本机 Redis 服务，并确保 `REDIS_URL`、Celery broker 与结果后端指向同一可达 Redis。Windows 课程演示使用 Celery `solo` pool：

```powershell
docker run --name movie-recommend-redis -p 6379:6379 -d redis:7-alpine
Push-Location backend
..\.venv_new\Scripts\celery.exe -A app.celery_app:celery_app worker --pool=solo --loglevel=INFO
```

另开终端执行：

```powershell
& .\.venv_new\Scripts\python.exe backend/jobs/check_recommendation_runtime.py
```

检查输出只含服务状态、包版本和测试库名是否匹配，不输出连接串。`celery_worker_online=True` 需要 Redis 正常且 Worker 已启动。脚本不连接 MySQL，也不写数据。

## 请求与一致性

推荐任务读取当前用户评分和离线用户文件，排除已评分/软删除电影。Worker 将离线候选原顺序转换为离线排名分，联合热门榜排名和用户评分的电影类型偏好计算列表排序分。默认权重为离线排名 0.75、热门 0.10、类型偏好 0.15，可由 `RECOMMENDATION_OFFLINE_RANK_WEIGHT`、`RECOMMENDATION_POPULARITY_RANK_WEIGHT` 和 `RECOMMENDATION_PROFILE_RANK_WEIGHT` 调整；离线候选次序已经包含 ALS/热门混合信号，因此在线热门权重较低，避免重复过度加权。缺少某个信号时对可用信号重新归一化。候选不足或没有离线 ALS 用户文件时由热门榜补位。排序分范围为 0–1，仅用于同一用户列表内排序。

Worker 先在 MySQL 单事务内写推荐条目，commit 后用单条 Redis JSON `SET EX` 更新 `recommendation:<userid>:latest`。缓存失败不撤销 MySQL，API 原有 Redis miss → MySQL 回源 → Redis 回填路径保持有效。

Celery 重试使用同一 request_id。已有 request_id 时 Worker 从只读连接复用已提交结果；`UQ(request_id,movieid)` 是并发重试的最终防护。新增推荐记录仅写 `recommendationitem`，不写业务评分、用户或电影表。

评分 API 仅在评分事务提交后投递 `recommendation.refresh_user`。此任务使用新的 request_id，复用最新离线 ALS 用户候选文件，并读取刚提交的评分更新类型偏好后重排。它不运行 Spark，不更新 ALS 用户/电影因子；新因子要等下一次离线 ALS 作业。队列投递失败不会撤销评分，API 响应将 `recommendation_refresh_queued` 置为 false。前端打开推荐页时，最多轮询 15 秒等待该 request_id 的新结果。

在线重排会改变离线列表顺序。须使用固定快照、固定正例阈值和相同候选集，对照 ALS、热门和混合方案的 Precision@20、Recall@20、NDCG@20、覆盖率及类别多样性。当前权重是演示初始值，不代表排序提升已通过离线验证。

## 测试边界

当前运行环境的 Redis 地址默认到本机 6379；启动前执行自检。集成写入必须先确认测试 schema 已准备好有效用户、电影、评分及推荐表，并确认只读/写入账号权限。此文档不会创建数据库、复制业务数据或清理任何表记录。
