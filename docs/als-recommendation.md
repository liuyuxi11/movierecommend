# ALS 推荐作业与验证

## 数据与数据库口径

- 交互唯一来源是 `personalratings(userid,movieid,rating,rated_at)`；显式 ALS (`implicitPrefs=False`)，评分 1–5。
- 只过滤 `user.deleted_at` 和 `movieinfo.deleted_at`；不按 `user.status` 过滤，不使用 `trainingrating` 或 `userfavorite`。
- `rated_at` 代表当前评分记录最近一次写入时间。表不保留评分修改历史，因此此作业的时间切分是“当前评分记录的更新时间切分”，不是严格历史回测。要做严格回测，需新增追加式评分事件表，或固定保存不可变评分快照并在评估时读取对应快照。
- 推荐结果只落到现有 `recommendationitem`。不使用缺少主外键、批次和位置字段的旧 `recommendresult`。
- 排序指标正例阈值默认为 `rating >= 4`，可通过 `--positive-threshold` 修改。Precision/Recall/NDCG 仅评估测试集里至少有一条正例、且在训练模型中有用户因子的用户；冷启动用户不计入 ALS 排序指标，并单独由用户覆盖率体现。

## 环境检查

项目固定 `pyspark==4.0.4`。建议使用 Java 17 或 21，并在 `spark-submit` classpath 上提供与 MySQL 服务器兼容的 Connector/J。脚本不会打印连接凭据或完整 URL。

```powershell
python -m pip install -r requirements.txt
$env:MYSQL_JDBC_URL = "jdbc:mysql://<readonly-host>:3306/movierecommend?useSSL=true&serverTimezone=UTC"
$env:MYSQL_USER = "<readonly-user>"
$env:MYSQL_PASSWORD = "<secret>"
python backend/jobs/check_als_environment.py
spark-submit --jars "C:\drivers\mysql-connector-j-<version>.jar" `
  backend/jobs/check_als_environment.py --probe-mysql
```

自检确认 PySpark、Java 17/21、`spark-submit`、环境变量和 UTC URL 参数。Connector/J 是否已加载以及 MySQL 只读权限、schema、时间值仍需执行下面的 Spark JDBC 冒烟运行验证。测试应使用只读副本或只读账号，不能用写账号做模型测试。

不连接数据库的合成算法冒烟：

```powershell
spark-submit --master "local[2]" backend/jobs/test_als_smoke.py
```

该脚本验证 ALS 拟合、时间切分空集错误、冷启动评估空集错误、三类排序指标以及无评分用户热门回退；数据只在 Spark DataFrame 中构造，ALS checkpoint 写入系统临时目录，不访问数据库或写推荐结果。

## 训练、调参与结果

默认只读 MySQL，训练模型并输出指标日志；指定 `--snapshot-path`、`--model-path`、`--recommendations-path`、`--metadata-path` 后只写文件系统，不会写 MySQL：

```powershell
$run = [guid]::NewGuid().ToString("N")
spark-submit --master "local[*]" `
  --jars "C:\drivers\mysql-connector-j-<version>.jar" `
  backend/jobs/als_recommender.py `
  --tune --rank-grid 32,64 --iter-grid 10,15 --reg-grid 0.01,0.05 `
  --top-n 20 --positive-threshold 4 --batch-id $run `
  --snapshot-path "D:\als-output\$run\snapshot" `
  --model-path "D:\als-output\$run\model" `
  --recommendations-path "D:\als-output\$run\recommendations" `
  --metadata-path "D:\als-output\$run\metadata.json"
```

参数网格默认 2×2×2，共 8 次验证训练；之后还会拟合一次测试评估模型和一次生产模型。大数据场景成本约为 10 次 ALS 拟合，应按验证算力预算缩小网格。固定参数验证可省略 `--tune`，通过 `--rank`、`--max-iter`、`--reg-param` 设置。

首次抽取要求提供唯一 `--snapshot-path`，保存有效评分、活跃用户、活跃电影、电影分类 Parquet 快照和来源质量统计 `quality.json`；MySQL 多个只读查询不是统一跨表事务，因此元数据始终标记 `cross_table_snapshot_atomic=false`。复跑时改用 `--input-snapshot <path>`，作业离线读取同一组 Parquet 和 `quality.json`，不再连接 MySQL；缺少质量文件的快照会失败，避免伪造原始质量计数。两者必须且只能提供一个。作业同时记录 UTC cutoffs、训练/验证/测试行数、质量统计、Spark 版本、参数、指标和批次 ID。cutoffs 可通过 `--train-cutoff`、`--valid-cutoff` 提供带时区 ISO 时间，用于复跑相同时间边界。自动 cutoff 使用 `rated_at` 的近似分位数。每次输出目录和 JSON 路径需唯一，脚本拒绝覆盖已有文件。

使用已保存快照离线复跑：

```powershell
spark-submit --master "local[*]" backend/jobs/als_recommender.py `
  --input-snapshot "D:\als-output\<capture-run>\snapshot" `
  --rank 32 --max-iter 5 --reg-param 0.05 --top-n 20 `
  --batch-id "<new-run-token>" `
  --model-path "D:\als-output\<new-run-token>\model" `
  --recommendations-path "D:\als-output\<new-run-token>\recommendations" `
  --metadata-path "D:\als-output\<new-run-token>\metadata.json"
```

排序评估比较 ALS、热门和固定 seed 的随机基线。三种方法使用相同候选集合：有效电影中有 ALS item factor 的电影；每个用户都排除训练/验证已评分电影。热门度只由训练+验证数据计算。指标包括 Precision@K、Recall@K、NDCG@K、该候选集合内的电影覆盖率、用户覆盖率和平均类别覆盖比例（每用户列表内不同类别数除以推荐电影数，截断到 1）。该类别指标是多样性代理量，不等同于标准列表内距离。ALS 测试用户只评估训练中出现的用户因子；冷启动用户不算排序指标用户分母，另报告覆盖率。类别信息来源于有效 `moviecategory`/`category`。

推荐生成对 ALS 过滤已评分项后不足 Top-N 的用户，以及没有评分因子的活跃用户，使用训练评分数量×均分排序的热门电影补齐。候选来源限定于训练中出现且当前未软删除的电影；若用户已看/评过候选池中全部电影，结果可能少于 N，作业会输出条目数摘要。无有效训练评分时作业明确失败，不会伪造 ALS 模型。

JDBC 默认单分区读取。`--jdbc-partitions N` 使用 `personalratings.ratingid` 主键范围并行读取；该键单调且适合分片，但提高 N 会增加 MySQL 并发连接和负载。优先从只读副本读取；大规模训练优先保存 Parquet 快照后离线训练。`--shuffle-partitions` 和 `--als-blocks` 应按集群资源调整。ALS checkpoint 目录可用 `--checkpoint-dir` 配置；本地默认位于系统临时目录，集群必须指定 executor 可共同访问的 HDFS/对象存储兼容路径。

## 事务型 MySQL 发布

ALS 训练程序不提供直接 Spark JDBC 写入。结果 Parquet 经审查后由单独加载器发布到 `recommendationitem`。字段映射为：

| Parquet 字段 | MySQL 字段 | 说明 |
|---|---|---|
| `request_id` | `request_id` | `<batch-id>-<userid>`，同一批次用户一一对应 |
| `userid` | `userid` | 有效 `user.userid` 外键 |
| `movieid` | `movieid` | 有效 `movieinfo.movieid` 外键 |
| `position` | `position` | 每个用户从 1 连续编号，最大不超过 Top-N |
| `movie_rating_snapshot` | 同名 | `movieinfo.averating` 快照，不是 ALS 分数 |
| `prediction_score` | 同名 | ALS 或热门回退的排序分，写入 `DECIMAL(10,6)` |
| `algorithm_version` | 同名 | 最大 100 字符 |
| `generated_at` | 同名 | UTC 时间 |

发布必须同时提供 CLI 确认、环境开关和预期数据库名；批次 ID 限 1–32 位字母数字。PyMySQL 加载器验证字段、唯一性、排序位置和有效父实体；随后在一个 InnoDB 事务中删除同批次无反馈旧条目并分批插入。任何错误回滚整个事务。若旧批次已关联 `recommendationevent`，外键 `RESTRICT` 下不做删除/重跑，需使用新批次 ID。

```powershell
$env:MYSQL_WRITE_URL = "mysql://<writer>:<secret>@<isolated-host>:3306/movierecommend"
$env:ALLOW_RECOMMENDATION_MYSQL_WRITE = "YES"
python backend/jobs/load_recommendations.py `
  --parquet "D:\als-output\<batch-id>\recommendations" `
  --batch-id "<batch-id>" `
  --expected-database "movierecommend" `
  --top-n 20 `
  --confirm-mysql-write
```

此命令只可对隔离测试库或经批准的目标执行。本项目测试流程不要求运行加载器，更不能把它指向生产库。事务失败会自动回滚；测试成功后清理时必须先确认没有 `recommendationevent` 引用，再按 `request_id LIKE '<batch-id>-%'` 在同一外键约束下清理，建议仅在隔离库中做。

写入前/后只读检查示例：

```sql
SELECT COUNT(*) AS missing_or_deleted_users
FROM recommendationitem i
LEFT JOIN `user` u ON u.userid = i.userid
WHERE i.request_id LIKE '<batch-id>-%'
  AND (u.userid IS NULL OR u.deleted_at IS NOT NULL);

SELECT COUNT(*) AS missing_or_deleted_movies
FROM recommendationitem i
LEFT JOIN movieinfo m ON m.movieid = i.movieid
WHERE i.request_id LIKE '<batch-id>-%'
  AND (m.movieid IS NULL OR m.deleted_at IS NOT NULL);

SELECT request_id, COUNT(*) AS rows, COUNT(DISTINCT movieid) AS movies,
       MIN(position) AS first_position, MAX(position) AS last_position
FROM recommendationitem
WHERE request_id LIKE '<batch-id>-%'
GROUP BY request_id;
```
