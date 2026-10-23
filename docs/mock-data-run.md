# 模拟数据投放记录

2026-10-23（香港时间），已对项目 `.env` 对应的 `localhost:3306/movierecommend` 完成正式投放，并更新 `database/dumps/movierecommend.sql`。

## 执行参数与结果

- 模式：append，保留原有数据。
- 随机种子：42；run-tag：`cead69cc48b4`；批量大小：1,000。
- 时间基准：`2026-10-23T00:54:14.281482+00:00`，即香港时间 08:54:14。
- 电影基数：50,581，使用全部未软删除电影。
- 其他规模参数采用 `generate_mock_data.py` 默认值。
- 单事务提交成功，新增合计 **761,000 行**；全部 56 项物理约束及业务一致性校验通过。

| 表 | 本次新增 | 投放后总数 |
|---|---:|---:|
| movieinfo | 0 | 50,581 |
| user | 5,059 | 5,060 |
| personalratings | 202,360 | 202,360 |
| moviecomment | 20,236 | 20,236 |
| userfavorite | 50,590 | 50,590 |
| commentlike | 60,708 | 60,708 |
| commentlike_event | 74,065 | 74,065 |
| recommendationitem | 151,770 | 151,770 |
| recommendationevent | 145,622 | 145,622 |
| recommendresult | 50,590 | 50,590 |

新模拟用户名以 `simcead69cc48b4_` 开头。模拟账号使用随机生成的共用密码及 bcrypt 哈希；用户名规则和明文登录密码仅保存在本地忽略目录的 `seed-credentials.json`，未写入本文档。数据库 password 列存储哈希。

## Aerich 状态

原 `backend/pyproject.toml` 引用了尚未定义的 `app.database.TORTOISE_ORM`。已在 `backend/app/database.py` 补齐配置，连接沿用 DATABASE_URL，模型包含 `app.models`、`aerich.models`，时区使用 UTC。

在 backend 目录执行：

```powershell
../.venv_new/Scripts/python.exe -m aerich heads
../.venv_new/Scripts/python.exe -m aerich history
```

结果：无待执行迁移；现有迁移为 `1_schema_upgrade.py`，数据库 aerich 元数据版本相同。没有创建新迁移、修改表结构或改写 Aerich 版本记录。

## SQL 导出与备份

- 更新文件：`database/dumps/movierecommend.sql`，90,779,184 字节。
- SHA256：`a009074ac64e15daaca94958a091860c2df49e2d3d61ce4938e220fbd0de6228`。
- 使用 MySQL 原生 mysqldump，采用 single-transaction、quick，包含所有表数据、触发器、例程、事件及 Aerich 元数据。
- 已核对 mysqldump 成功退出、导出完成标记，以及目标表与 movieinfo 的结构签名；未在其他数据库执行恢复演练。
- 本地备份目录：`.local-backups/seed-20261023T005349Z/`，受项目 .gitignore 排除。

备份目录中的文件：

- `original-movierecommend.sql`：覆盖前的源 SQL 文件。
- `before-seed.sql`：投放前的实际数据库完整导出。
- `after-seed.sql`：投放后的完整导出，与交付 dump 内容一致。
- `seed.log`：成功执行的全部日志。
- `failed-seed.log`：首次全量校验超时日志；已确认该事务完全回滚后才重试。
- `seed-credentials.json`：模拟账号凭据及生成参数。
- `result.json`：行数、连接标识、迁移版本和导出摘要。

全量执行时已将曝光校验、首次点赞时间校验及旧结果镜像校验改为聚合后关联，避免在初始统计信息不足时进行大量逐行相关查询；修复后的完整数据校验通过。脚本也已改进连接丢失时的回滚与锁释放错误报告。

再次执行 append 会新增另一批数据。重复使用本次 run-tag 会被拒绝；若要重建全部九张目标表，须明确使用 rebuild，并先评估数据覆盖和非目标表引用。
