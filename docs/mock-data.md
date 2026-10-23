# 第一部分：信息核验与待确认清单

以用户更新后的 `database/dumps/movierecommend.sql` 为结构依据，`docs/database.md` 用于解释业务语义。脚本不会执行 dump 中的 DROP、CREATE、INSERT 或关闭外键语句，也不会修改表结构。

已通过项目 `.env` 配置只读查询 MySQL：`movieinfo` 共 **50,581** 行，其中 `deleted_at IS NULL` 为 **50,581** 行。最新 dump 也包含 50,581 条单行电影 INSERT；后者只是导出快照，不替代运行时查询。

## 字段与约束摘要

以下 `!` 表示 NOT NULL；`?` 表示可空；所有 datetime 均为 datetime(6)，按 UTC 解释；列名均来自最新 SQL。未标默认值的必填业务列由脚本显式提供。

| 表 | 字段摘要 | 主键、唯一键与外键 |
|---|---|---|
| user | userid int!；username varchar(50)!；password varchar(255)!；phone varchar(32)!；email varchar(254)!；avatar varchar(1000)?；status varchar(20)! 默认 active；created_at/updated_at! 默认 CURRENT_TIMESTAMP(6)，updated_at 自动更新；deleted_at?；active_username/active_phone/active_email 可空 STORED 生成列 | 自增 PK(userid)；三个 active_* 分别唯一；没有外键 |
| personalratings | ratingid bigint!；userid/movieid/rating int!；timestamp char(10)? 默认 NULL；rated_at! 无默认 | 自增 PK(ratingid)；UQ(userid,movieid)；FK userid→user、movieid→movieinfo；CHECK rating BETWEEN 1 AND 10 |
| moviecomment | commentid bigint!；userid/movieid int!；content varchar(500)!；moderation_status varchar(20)! 默认 published；created_at! 默认当前时间；deleted_at? | 自增 PK(commentid)；FK 用户、电影；没有业务唯一键；CHECK moderation_status IN (published,review_pending,hidden) |
| commentlike | id bigint!；userid int!；commentid bigint!；is_active tinyint(1)! 默认 1；created_at/updated_at! 默认当前时间，updated_at 自动更新 | 自增 PK(id)；UQ(userid,commentid)；FK 用户、评论；SQL 没有 is_active CHECK，业务只生成 0/1 |
| commentlike_event | eventid bigint!；userid int!；commentid bigint!；action varchar(10)!；created_at! 默认当前时间 | 自增 PK(eventid)；FK 用户、评论；CHECK action IN (like,unlike)；没有 FK 指向 commentlike，按(userid,commentid)对应 |
| userfavorite | id bigint!；userid/movieid int!；status varchar(30)! 无默认；created_at/updated_at! 默认当前时间，updated_at 自动更新；deleted_at? | 自增 PK(id)；UQ(userid,movieid)；FK 用户、电影；CHECK status IN (want_to_watch,watched) |
| recommendationitem | recommendationid bigint!；request_id varchar(64)!；userid/movieid/position int!；movie_rating_snapshot decimal(4,1)?；prediction_score decimal(10,6)?；algorithm_version varchar(100)?；generated_at! 默认当前时间 | 自增 PK(recommendationid)；UQ(request_id,movieid)；FK 用户、电影；请求归属和位置唯一性没有数据库约束，由脚本保证 |
| recommendationevent | eventid bigint!；recommendationid bigint!；event_type varchar(20)!；created_at! 默认当前时间 | 自增 PK(eventid)；FK recommendationid→recommendationitem；CHECK event_type IN (impression,click,not_interested) |
| recommendresult | userid/movieid int?；rating float?；moviename varchar(1000)?，均默认 NULL | **没有 PK、FK、唯一索引**；脚本额外保证有效用户/电影引用及用户电影组合不重复，不添加约束 |

以上目标表外键均为 ON DELETE RESTRICT / ON UPDATE RESTRICT。数据库自增分配主键；批量插入后读取实际 ID，不假设 ID 连续，也不使用 MAX(id)+1。user 的生成列不进入 INSERT。movieinfo.movieid 为非自增 int 主键，仅选用实际存在、未软删除的电影。

SQL 中 user、movieinfo、personalratings、recommendresult 使用 utf8mb3，其余目标表使用 utf8mb4；生成用户名、邮箱等用 ASCII，评论使用不含补充平面字符的中文。active_username 使用 utf8mb4_0900_ai_ci，唯一性大小写不敏感。

安全插入次序：user → personalratings/userfavorite/moviecomment/recommendationitem → commentlike/commentlike_event/recommendationevent → recommendresult。独立分支可交错写入；真正的外键父记录总是先完成写入。commentlike_event 仅通过用户与评论建立物理 FK，脚本在批次结束时确保其状态行存在。

清理次序：recommendationevent → recommendationitem → recommendresult → commentlike_event → commentlike → moviecomment → userfavorite → personalratings → user。全程保持外键检查开启，使用可回滚 DELETE，不使用 TRUNCATE、不重置自增计数器。

## 待确认清单及当前处理边界

1. **user.status 的其他业务状态没有定义**：仅使用 SQL 默认值 active，不创造其他值。
2. **recommendresult 是否保留、何时下线没有确定**：因为本任务要求生成该表，明确采用“每个新用户最后一次模拟推荐请求的电影清单镜像”策略。这是模拟策略，不是源文件规定的关联；该表没有 recommendationid/request_id，不能与事件建立直接 FK。rating 来自 movieinfo.averating，绝不填入预测分。
3. **曝光去重、CTR、点击归因和重复点击规范尚未定义**：只生成可视曝光后的一次互斥反馈，不宣称这就是生产统计口径。未曝光的条目没有事件。
4. **算法及预测分分布未提供**：prediction_score、algorithm_version 留 NULL；movie_rating_snapshot 从真实电影 averating 复制，超出 decimal(4,1) 时报错而非篡改数据。
5. **审核状态改变通常依赖举报/审核流程，本任务不生成 commentreport**：全部评论使用 published，不伪造不存在的审核记录。全部新用户、评论与收藏不软删除。
6. **字段没有规定电话格式或密码哈希算法**：电话使用唯一的合成标识，不代表真实可拨号手机号；密码哈希额外核对项目 auth.py，采用兼容的 bcrypt。若需要模拟真实手机号校验、其他审核状态或生产推荐口径，需先补充相应规则。

文档“关系总览”是简图，推荐事件实际只引用 recommendationitem；以 SQL 外键与文档详细章节为准。没有把事件直接连到电影或 recommendresult。

# 第二部分：数据量估算表与生成策略

默认 M=50,581，电影抽样比例 f=1，U=ceil(M×f×0.1)=5,059。这是开发联调的中等活跃度方案，不是线上指标推断。全部比例均可从命令行调整。

| 表 | 默认建议新增行数 | 业务解释与参数 |
|---|---:|---|
| user | 5,059 | 每 10 部电影配置 1 名用户，`--users-per-movie .1` |
| personalratings | 202,360 | 每用户评价 40 部不同电影，模拟有历史行为的用户，`--ratings-per-user 40` |
| moviecomment | 20,236 | 每用户从已评分电影中选 4 部评论，约评分的十分之一，`--comments-per-user 4` |
| userfavorite | 50,590 | 每用户收藏 10 部不同电影，约评分数量的四分之一，`--favorites-per-user 10` |
| commentlike | 60,708 | 每条评论被 3 名不同的其他用户操作过，`--likes-per-comment 3` |
| commentlike_event | 约 74,064 | 每关系先 like；20% 后续 unlike；其中 10% 再 like。L×[1+.2×(1+.1)]；`--unlike-rate .2 --relike-rate .1` |
| recommendationitem | 151,770 | 每用户 3 次请求、每次 10 部，模拟多次浏览，`--requests-per-user 3 --items-per-request 10` |
| recommendationevent | 约 145,699 | 80% 条目可视曝光，其中 15% 点击、5% 不感兴趣；I×.8×(1+.15+.05)；对应三个 rate 参数 |
| recommendresult | 50,590 | 每用户只保存最后一次模拟请求的 10 部电影，避免旧表积累无法区分批次的重复对 |

事件数量是期望值，实际由随机采样决定，日志给出真实插入行数。用户电影对、每次请求电影、每评论点赞者均无放回抽样。小电影集会把评分/收藏/推荐数量截断到电影池大小；评论数量不超过实际评分数；点赞人数不超过 U−1，单用户时可为 0。脚本日志展示截断后的计划。

`--movie-count` / 环境变量 `MOVIE_COUNT` 仅覆盖**规模估算基数**，不替代真实电影行或伪造电影 ID；`--movie-ratio` 决定真实活跃电影池的抽样比例，同时缩放用户规模。不指定 MOVIE_COUNT 时使用运行时真实活跃电影数；离线估算必须显式指定基数，且禁止执行写入。

电影均匀抽样，避免在没有业务定义时把 SQL 注释为“热度”的 numrating 擅自解释为采样权重。日期不基于电影上映日做观看限制：资料没有给出上映日可空、未来上映电影的交互约束。

UTC 时间分布：以 `--as-of` 为终点，在 `--history-days 180` 的前 20% 时间段注册用户；评分发生于注册后；评论发生于相应评分后；点赞同时晚于评论和点赞者注册；like/unlike/re-like 严格递增；请求时间按序递增，曝光晚于生成 1–60 秒，反馈再晚 1–180 秒且不超过 as-of。收藏来自已评分电影时标为 watched，其余标为 want_to_watch。created_at≤updated_at。

同 seed、as-of、run-tag、参数、按 ID 排序的相同电影快照及密码哈希，可重现业务抽样、文本和时间。主键值不保证重复；MySQL 自增值在回滚后也可能有间隙。默认 run-tag 随机，便于追加；固定 seed 本身不意味着幂等去重。

批量大小默认 1,000，使用 pymysql.executemany；同一运行仅在全部写入和校验成功后提交一次，失败整体回滚。批量大小控制每次发送的行数，**不代表每批提交**。脚本保留电影池、用户映射及部分评论/推荐 ID 供关联，内存规模约 O(电影+用户+评论+推荐条目)，默认规模适合本地联调；极大规模需另行评估内存和单事务 undo 日志容量。

# 第三部分：完整 Python 脚本

可直接运行的脚本：`database/seed/generate_mock_data.py`。依赖：`database/seed/requirements.txt`。以下代码与交付文件保持一致。

```python
#!/usr/bin/env python3
"""Seed the schema in the CURRENT dump. No DDL; one atomic DML transaction.

Default: read-only plan. --execute writes, --mode rebuild deletes ALL target rows.
See docs/mock-data.md. Python 3.10+, requirements in database/seed/requirements.txt.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import random
import re
import secrets
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
TABLES = ('user', 'personalratings', 'userfavorite', 'moviecomment',
          'commentlike', 'commentlike_event', 'recommendationitem',
          'recommendationevent', 'recommendresult')
DELETE_ORDER = ('recommendationevent', 'recommendationitem', 'recommendresult',
                'commentlike_event', 'commentlike', 'moviecomment',
                'userfavorite', 'personalratings', 'user')
LOG = logging.getLogger('mock-data')


def ident(name):
    return '`' + name.replace('`', '``') + '`'


def args_parse():
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env', override=False)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true', help='Otherwise read-only plan')
    p.add_argument('--rollback-test', action='store_true', help='Exercise inserts/validation then ROLLBACK; requires --execute')
    p.add_argument('--mode', choices=['append', 'rebuild'], default='append')
    p.add_argument('--offline', action='store_true', help='Plan only; requires MOVIE_COUNT')
    p.add_argument('--dump', type=Path, default=ROOT / 'database/dumps/movierecommend.sql')
    p.add_argument('--database-url', default=os.getenv('DATABASE_URL'))
    p.add_argument('--host', default=os.getenv('MYSQL_HOST'))
    p.add_argument('--port', type=int, default=int(os.environ['MYSQL_PORT']) if os.getenv('MYSQL_PORT') else None)
    p.add_argument('--user', default=os.getenv('MYSQL_USER'))
    p.add_argument('--password', default=os.getenv('MYSQL_PASSWORD'))
    p.add_argument('--database', default=os.getenv('MYSQL_DATABASE'))
    p.add_argument('--ssl-ca', default=os.getenv('MYSQL_SSL_CA'))
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--batch-size', type=int, default=1000)
    p.add_argument('--movie-count', type=int, default=int(os.getenv('MOVIE_COUNT', '0')),
                   help='Sizing baseline only; never invents movie IDs')
    p.add_argument('--movie-ratio', type=float, default=1.0, help='Fraction of active movies sampled')
    p.add_argument('--users-per-movie', type=float, default=.1)
    p.add_argument('--ratings-per-user', type=int, default=40)
    p.add_argument('--comments-per-user', type=int, default=4)
    p.add_argument('--favorites-per-user', type=int, default=10)
    p.add_argument('--likes-per-comment', type=int, default=3)
    p.add_argument('--unlike-rate', type=float, default=.2)
    p.add_argument('--relike-rate', type=float, default=.1, help='Conditional on unlike')
    p.add_argument('--requests-per-user', type=int, default=3)
    p.add_argument('--items-per-request', type=int, default=10)
    p.add_argument('--impression-rate', type=float, default=.8)
    p.add_argument('--click-rate', type=float, default=.15, help='Conditional on impression')
    p.add_argument('--not-interested-rate', type=float, default=.05,
                   help='Conditional on impression; mutually exclusive with click')
    p.add_argument('--history-days', type=int, default=180)
    p.add_argument('--as-of', help='UTC ISO time; fixed value makes logical data repeatable')
    p.add_argument('--run-tag', default=secrets.token_hex(6), help='1-12 lowercase hex digits')
    p.add_argument('--password-hash', default=os.getenv('SEED_PASSWORD_HASH'),
                   help='Existing bcrypt hash; no plaintext is written or logged')
    a = p.parse_args()
    if not re.fullmatch('[0-9a-f]{1,12}', a.run_tag):
        p.error('run-tag must contain 1-12 lowercase hex digits')
    for n in ('batch_size', 'history_days', 'ratings_per_user', 'comments_per_user',
              'favorites_per_user', 'likes_per_comment', 'requests_per_user', 'items_per_request'):
        if getattr(a, n) <= 0:
            p.error(n + ' must be positive')
    if a.movie_count < 0 or not math.isfinite(a.users_per_movie) or a.users_per_movie <= 0:
        p.error('movie-count >= 0 and users-per-movie > 0 required')
    for n in ('movie_ratio', 'unlike_rate', 'relike_rate', 'impression_rate',
              'click_rate', 'not_interested_rate'):
        if not 0 <= getattr(a, n) <= 1:
            p.error(n + ' must be between 0 and 1')
    if a.movie_ratio == 0 or a.click_rate + a.not_interested_rate > 1:
        p.error('movie-ratio > 0 and click-rate + not-interested-rate <= 1 required')
    if a.offline and (a.execute or not a.movie_count):
        p.error('offline requires --movie-count and does not allow --execute')
    if a.rollback_test and not a.execute:
        p.error('--rollback-test requires --execute')
    supplied_time = datetime.fromisoformat(a.as_of.replace('Z', '+00:00')) if a.as_of else datetime.now(timezone.utc)
    if supplied_time.tzinfo is None:
        supplied_time = supplied_time.replace(tzinfo=timezone.utc)
    a.as_of = supplied_time.astimezone(timezone.utc).replace(tzinfo=None)
    if a.as_of < datetime(1970, 1, 1) + timedelta(days=a.history_days):
        p.error('history must be after Unix epoch')
    return a


def canonical(expression):
    # MySQL SHOW CREATE and Navicat use different whitespace/parentheses/charset introducers.
    s = re.sub(r"_utf8(?:mb[34])?(?=')", '', expression.lower())
    return re.sub(r'[\s`()]+', '', s)


def signature(ddl):
    """Compare columns/defaults/generated expressions, PK/UQ, FKs and CHECKs to dump."""
    cols, keys, fks, checks = {}, [], [], []
    table_collation = re.search(r'\)\s*ENGINE\s*=.*?\bCOLLATE\s*=\s*(\w+)', ddl, re.I)
    charset = re.search(r'\bCHARSET\s*=\s*(\w+)', ddl, re.I)
    inherited_collation = table_collation[1].lower() if table_collation else (
        {'utf8mb3': 'utf8mb3_general_ci', 'utf8mb4': 'utf8mb4_0900_ai_ci'}.get(charset[1].lower()) if charset else None)
    for line in ddl.splitlines()[1:]:
        line = line.strip().rstrip(',')
        m = re.match(r'`([^`]+)`\s+([a-z]+(?:\([\d, ]+\))?)(.*)', line, re.I)
        if m:
            name, typ, tail = m.groups()
            default = re.search(r"\bDEFAULT\s+('(?:[^']|'')*'|CURRENT_TIMESTAMP(?:\(\d+\))?|NULL|[-\d.]+)", tail, re.I)
            generated = re.search(r'GENERATED ALWAYS AS\s*\((.*)\)\s*(?:STORED|VIRTUAL)', tail, re.I)
            collation = re.search(r'COLLATE\s+(\w+)', tail, re.I)
            cols[name] = (canonical(typ), 'NOT NULL' in tail.upper(),
                          (canonical(default[1]).strip("'") if typ.lower().startswith(('int', 'bigint', 'tinyint', 'decimal', 'double', 'float'))
                           else canonical(default[1])) if default else None,
                          'AUTO_INCREMENT' in tail.upper(),
                          canonical(generated[1]) if generated else None,
                          collation[1].lower() if collation else
                          (inherited_collation if typ.lower().startswith(('varchar', 'char', 'text')) else None),
                          'ON UPDATE' in tail.upper())
        elif re.match(r'(PRIMARY KEY|UNIQUE (?:INDEX|KEY))', line, re.I):
            keys.append(('PK' if line.upper().startswith('PRIMARY') else 'UQ',
                         tuple(re.findall(r'`([^`]+)`', line[line.index('('):]))))
        elif 'FOREIGN KEY' in line.upper():
            actions = []
            for operation in ('DELETE', 'UPDATE'):
                action = re.search(r'ON ' + operation + r' (RESTRICT|CASCADE|SET NULL|NO ACTION)', line, re.I)
                actions.append(action[1].upper() if action else 'RESTRICT')
            fks.append((*re.findall(r'`([^`]+)`', line)[1:], *actions))
        elif ' CHECK ' in line.upper():
            checks.append(canonical(line.split('CHECK', 1)[1]))
    return cols, sorted(keys), sorted(fks), sorted(checks)


def load_schema(path):
    text = path.read_text(encoding='utf-8-sig')
    ddl = dict(re.findall(r'CREATE TABLE `([^`]+)`\s*(\(.*?\) ENGINE[^;]*);', text, re.S))
    return {t: 'CREATE TABLE ' + ident(t) + ' ' + ddl[t]
            for t in (*TABLES, 'movieinfo')}


def connect(a):
    import pymysql
    u = urlsplit(a.database_url or '')
    config = dict(host=a.host or u.hostname or '127.0.0.1',
                  port=a.port or u.port or 3306,
                  user=a.user or unquote(u.username or ''),
                  password=a.password if a.password is not None else unquote(u.password or ''),
                  database=a.database or unquote(u.path.lstrip('/')),
                  charset='utf8mb4', autocommit=False, connect_timeout=10,
                  read_timeout=120, write_timeout=120)
    if a.ssl_ca:
        config['ssl'] = {'ca': a.ssl_ca, 'check_hostname': True}
    if not config['user'] or not config['database']:
        raise ValueError('Configure DATABASE_URL or MYSQL_USER/MYSQL_DATABASE')
    return pymysql.connect(**config)


def preflight(q, schema):
    q.execute("SET time_zone = '+00:00'")
    q.execute("SET SESSION sql_mode = 'STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'")
    q.execute('SELECT @@foreign_key_checks')
    if q.fetchone() != (1,):
        raise ValueError('Foreign key enforcement must already be enabled')
    q.execute("SELECT TABLE_NAME FROM information_schema.TABLE_CONSTRAINTS "
              "WHERE CONSTRAINT_SCHEMA=DATABASE() AND CONSTRAINT_TYPE='CHECK' AND ENFORCED<>'YES'")
    if any(row[0] in schema for row in q.fetchall()):
        raise ValueError('CHECK constraints must be enforced')
    for t, ddl in schema.items():
        q.execute('SHOW CREATE TABLE ' + ident(t))
        live = q.fetchone()[1]
        if not re.search(r'ENGINE=InnoDB', live, re.I) or signature(live) != signature(ddl):
            raise ValueError('Schema differs from current dump: ' + t)
    LOG.info('Schema verified against latest dump; no DDL will be executed')


def plan(a, available):
    pool = max(1, math.ceil(available * a.movie_ratio))
    baseline = a.movie_count or available
    users = max(1, math.ceil(baseline * a.movie_ratio * a.users_per_movie))
    ratings = min(a.ratings_per_user, pool)
    comments = min(a.comments_per_user, ratings)
    favorites = min(a.favorites_per_user, pool)
    likes = min(a.likes_per_comment, users - 1)
    items = min(a.items_per_request, pool)
    counts = dict(user=users, personalratings=users * ratings,
                  moviecomment=users * comments, userfavorite=users * favorites,
                  commentlike=users * comments * likes,
                  recommendationitem=users * a.requests_per_user * items,
                  recommendresult=users * items)
    counts['commentlike_event'] = counts['commentlike'] * (1 + a.unlike_rate * (1 + a.relike_rate))
    counts['recommendationevent'] = counts['recommendationitem'] * a.impression_rate * (
        1 + a.click_rate + a.not_interested_rate)
    LOG.info('Movie rows=%s; baseline=%s; sampled pool=%s; estimated counts=%s',
             available, baseline, pool, json.dumps(counts))
    return users, pool, ratings, comments, favorites, likes, items


class Writer:
    def __init__(self, q, batch):
        self.q, self.batch = q, batch
        self.pending, self.counts = {}, Counter()

    def add(self, table, columns, row):
        key = (table, columns)
        self.pending.setdefault(key, []).append(row)
        if len(self.pending[key]) >= self.batch:
            self.flush(key)

    def flush(self, key=None):
        for k in ([key] if key else list(self.pending)):
            rows = self.pending[k]
            if not rows:
                continue
            table, columns = k
            sql = 'INSERT INTO ' + ident(table) + ' (' + ','.join(map(ident, columns.split()))
            sql += ') VALUES (' + ','.join(['%s'] * len(rows[0])) + ')'
            self.q.executemany(sql, rows)
            self.counts[table] += len(rows)
            rows.clear()
            LOG.info('Inserted %s total=%s (not committed)', table, self.counts[table])


def generate(a, q, movies, shape):
    import bcrypt
    if not a.password_hash or not re.fullmatch(r'\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}', a.password_hash):
        raise ValueError('Set SEED_PASSWORD_HASH to a bcrypt hash matching the application')
    bcrypt.checkpw(b'seed-format-check', a.password_hash.encode('ascii'))
    rng = random.Random(a.seed)
    n, pool, nr, nc, nf, nl, ni = shape
    if n > 999999:
        raise ValueError('At most 999999 users per run-tag')
    movies = rng.sample(movies, pool)
    by_movie = {m[0]: m for m in movies}
    mids = sorted(by_movie)
    prefix = 'sim' + a.run_tag + '_'
    pattern = prefix.replace('_', '\\_') + '%'
    q.execute('SELECT COUNT(*) FROM `user` WHERE username LIKE %s', (pattern,))
    if q.fetchone()[0]:
        raise ValueError('run-tag already exists; choose a new tag for append')
    w = Writer(q, a.batch_size)
    start = a.as_of - timedelta(days=a.history_days)

    def moment(lo, hi):
        return lo + (hi - lo) * rng.random()

    registrations = {}
    for i in range(n):
        name = prefix + f'{i:06d}'
        created = moment(start, start + (a.as_of - start) * .2)
        registrations[name] = created
        # Synthetic identifiers, not deliverable telephone/email contacts.
        w.add('user', 'username password phone email status created_at updated_at',
              (name, a.password_hash, 'sim' + a.run_tag + f'{i:06d}',
               name + '@example.invalid', 'active', created, created))
    w.flush()
    q.execute('SELECT userid,username FROM `user` WHERE username LIKE %s ORDER BY username', (pattern,))
    users = [(uid, registrations[name]) for uid, name in q.fetchall()]
    if len(users) != n:
        raise ValueError('Unexpected number of new users')
    # IDs are read back; no MAX(id)+1 or assumptions about auto-increment stride/gaps.
    for user_index, (uid, registered) in enumerate(users):
        rated = rng.sample(mids, nr)
        rating_times = {}
        for mid in rated:
            t = moment(registered, a.as_of - timedelta(hours=2))
            rating_times[mid] = t
            unix = str(int(t.replace(tzinfo=timezone.utc).timestamp()))
            if len(unix) > 10:
                raise ValueError('Unix timestamp does not fit char(10)')
            w.add('personalratings', 'userid movieid rating timestamp rated_at',
                  (uid, mid, rng.randint(1, 10), unix, t))
        for mid in rng.sample(rated, nc):
            t = moment(rating_times[mid], a.as_of - timedelta(hours=1))
            content = rng.choice(('叙事节奏清晰，值得再看。', '表演自然，配乐令人印象深刻。',
                                  '题材有趣，结尾还有回味。', '画面表现出色，剧情略显平淡。'))
            w.add('moviecomment', 'userid movieid content moderation_status created_at',
                  (uid, mid, content, 'published', t))
        for mid in rng.sample(mids, nf):
            t = moment(registered, a.as_of)
            status = 'watched' if mid in rating_times else 'want_to_watch'
            if mid in rating_times:
                t = max(t, rating_times[mid])
            w.add('userfavorite', 'userid movieid status created_at updated_at',
                  (uid, mid, status, t, t))
        generated_times = sorted(moment(registered, a.as_of - timedelta(minutes=5))
                                 for _ in range(a.requests_per_user))
        for j, generated in enumerate(generated_times):
            request = prefix + f'{user_index:06d}_{j:010d}'
            if len(request) > 64:
                raise ValueError('request_id exceeds varchar(64)')
            for position, mid in enumerate(rng.sample(mids, ni), 1):
                _, title, rating = by_movie[mid]
                snapshot = None if rating is None else Decimal(str(rating)).quantize(Decimal('.1'))
                if snapshot is not None and not Decimal('-999.9') <= snapshot <= Decimal('999.9'):
                    raise ValueError('Movie rating cannot fit recommendation snapshot: ' + str(mid))
                w.add('recommendationitem', 'request_id userid movieid position movie_rating_snapshot generated_at',
                      (request, uid, mid, position, snapshot, generated))
                # Legacy table contains ONLY the final simulated request for each new user.
                if j == a.requests_per_user - 1:
                    w.add('recommendresult', 'userid movieid rating moviename', (uid, mid, rating, title))
    w.flush()
    q.execute('SELECT c.commentid,c.userid,c.created_at FROM moviecomment c '
              'JOIN `user` u ON u.userid=c.userid WHERE u.username LIKE %s ORDER BY c.commentid', (pattern,))
    comments = q.fetchall()
    uid_order = {uid: i for i, (uid, _) in enumerate(users)}
    for cid, author, created in comments:
        # Sample indexes from n-1 without building a full user list for each comment.
        excluded = uid_order[author]
        for index in rng.sample(range(n - 1), nl):
            index += index >= excluded
            uid, registered = users[index]
            first = moment(max(created, registered), a.as_of - timedelta(seconds=3))
            history = [('like', first)]
            if rng.random() < a.unlike_rate:
                history.append(('unlike', moment(first + timedelta(microseconds=1), a.as_of - timedelta(seconds=1))))
                if rng.random() < a.relike_rate:
                    history.append(('like', moment(history[-1][1] + timedelta(microseconds=1), a.as_of)))
            active = int(history[-1][0] == 'like')
            w.add('commentlike', 'userid commentid is_active created_at updated_at',
                  (uid, cid, active, first, history[-1][1]))
            for action, t in history:
                w.add('commentlike_event', 'userid commentid action created_at', (uid, cid, action, t))
    w.flush()
    q.execute('SELECT i.recommendationid,i.generated_at FROM recommendationitem i '
              'JOIN `user` u ON u.userid=i.userid WHERE u.username LIKE %s ORDER BY i.recommendationid', (pattern,))
    for rid, generated in q.fetchall():
        if rng.random() < a.impression_rate:
            exposed = generated + timedelta(seconds=rng.randint(1, 60))
            w.add('recommendationevent', 'recommendationid event_type created_at', (rid, 'impression', exposed))
            draw = rng.random()
            event = ('click' if draw < a.click_rate else 'not_interested'
                     if draw < a.click_rate + a.not_interested_rate else None)
            if event:
                w.add('recommendationevent', 'recommendationid event_type created_at',
                      (rid, event, exposed + timedelta(seconds=rng.randint(1, 180))))
    w.flush()
    return w.counts


def validate(q, schema):
    """Generic physical constraints, plus semantic checks from validate_mock_data.sql."""
    def check(label, sql):
        q.execute(sql)
        count = q.fetchone()[0]
        LOG.info('Validation %s: %s violations', label, count)
        if count:
            raise ValueError('Validation failed: ' + label)

    for t in TABLES:
        columns, keys, fks, checks = signature(schema[t])
        required = [ident(c) + ' IS NULL' for c, meta in columns.items() if meta[1]]
        if required:
            check(t + ' NOT NULL', 'SELECT COUNT(*) FROM ' + ident(t) + ' WHERE ' + ' OR '.join(required))
        for _, key in keys:
            group = ','.join(map(ident, key))
            present = ' AND '.join(ident(k) + ' IS NOT NULL' for k in key)
            check(t + ' unique ' + group, f'SELECT COUNT(*) FROM (SELECT {group} FROM {ident(t)} '
                  f'WHERE {present} GROUP BY {group} HAVING COUNT(*)>1) d')
        for child, parent, parent_col, _, _ in fks:
            check(t + ' FK ' + child, 'SELECT COUNT(*) FROM ' + ident(t) + ' c LEFT JOIN ' + ident(parent)
                  + ' p ON c.' + ident(child) + '=p.' + ident(parent_col)
                  + ' WHERE c.' + ident(child) + ' IS NOT NULL AND p.' + ident(parent_col) + ' IS NULL')
        for expression in re.findall(r'CONSTRAINT `[^`]+` CHECK (.*?)(?:,?\n|\n\))', schema[t]):
            check(t + ' CHECK', 'SELECT COUNT(*) FROM ' + ident(t) + ' WHERE NOT (' + expression.rstrip(',') + ')')
    sql = (Path(__file__).with_name('validate_mock_data.sql')).read_text(encoding='utf-8')
    sql = re.sub(r'--[^\n]*', '', sql)
    for index, statement in enumerate(sql.split(';')):
        if statement.strip():
            check('business-' + str(index), statement)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    a = args_parse()
    schema = load_schema(a.dump)
    LOG.info('Dump SHA256=%s; seed=%s; run-tag=%s; as-of UTC=%s; mode=%s',
             hashlib.sha256(a.dump.read_bytes()).hexdigest(), a.seed, a.run_tag, a.as_of, a.mode)
    if a.offline:
        LOG.warning('Offline estimate only: MOVIE_COUNT=%s is not a verified live count', a.movie_count)
        plan(a, a.movie_count)
        return 0
    conn = connect(a)
    locked = False
    try:
        with conn.cursor() as q:
            preflight(q, schema)
            # Advisory lock coordinates copies of this script only, not the application.
            q.execute("SELECT GET_LOCK(CONCAT('mock-seed:',DATABASE()), 0)")
            locked = q.fetchone()[0] == 1
            if not locked:
                raise ValueError('Another seed run is active')
            q.execute('SELECT COUNT(*), COALESCE(SUM(deleted_at IS NULL),0) FROM movieinfo')
            total, available = map(int, q.fetchone())
            LOG.info('Live movieinfo total=%s active=%s', total, available)
            if not available:
                raise ValueError('No active movies; movie-count cannot create referenced movies')
            shape = plan(a, available)
            before = {}
            for t in TABLES:
                q.execute('SELECT COUNT(*) FROM ' + ident(t))
                before[t] = q.fetchone()[0]
            LOG.info('Existing counts=%s', json.dumps(before))
            if not a.execute:
                LOG.info('Read-only plan complete; use --execute to write')
                return 0
            q.execute('SELECT movieid,moviename,averating FROM movieinfo WHERE deleted_at IS NULL ORDER BY movieid')
            movies = q.fetchall()
            if a.mode == 'rebuild':
                # DELETE is transactional. TRUNCATE, FK disabling and AUTO_INCREMENT resets are forbidden.
                for t in DELETE_ORDER:
                    q.execute('DELETE FROM ' + ident(t))
                    LOG.info('Deleted all rows from %s (not committed)', t)
            inserted = generate(a, q, movies, shape)
            for t in TABLES:
                q.execute('SELECT COUNT(*) FROM ' + ident(t))
                expected = inserted[t] + (before[t] if a.mode == 'append' else 0)
                if q.fetchone()[0] != expected:
                    raise ValueError('Row count mismatch: ' + t)
            validate(q, schema)
            if a.rollback_test:
                conn.rollback()
                for t in TABLES:
                    q.execute('SELECT COUNT(*) FROM ' + ident(t))
                    if q.fetchone()[0] != before[t]:
                        raise ValueError('Rollback row count mismatch: ' + t)
                LOG.info('ROLLBACK TEST PASSED; original counts restored; inserted counts=%s', json.dumps(inserted))
            else:
                conn.commit()
                LOG.info('COMMITTED inserted counts=%s', json.dumps(inserted))
    except BaseException as exc:
        try:
            conn.rollback()
        except Exception:
            # A lost connection cannot acknowledge ROLLBACK. Closing it makes
            # MySQL discard an uncommitted transaction; verify before rerunning.
            LOG.error('Rollback acknowledgement unavailable; verify server transaction state')
        # Never print connection URL, passwords or arbitrary SQL row values.
        LOG.error('ROLLED BACK: %s', type(exc).__name__)
        if isinstance(exc, ValueError):
            LOG.error('%s', exc)
        elif getattr(exc, 'args', None) and isinstance(exc.args[0], int):
            LOG.error('MySQL error code=%s (1451 usually means non-target references block rebuild)', exc.args[0])
        return 1
    finally:
        if locked and conn.open:
            try:
                with conn.cursor() as q:
                    q.execute("SELECT RELEASE_LOCK(CONCAT('mock-seed:',DATABASE()))")
            except Exception:
                LOG.error('Lock release acknowledgement unavailable; connection close releases the lock')
        conn.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as error:
        LOG.error('Cannot start: %s; check file/dependencies/connection/arguments', type(error).__name__)
        sys.exit(1)
```

# 第四部分：校验 SQL 与运行说明

## 安装与配置

在项目根目录运行 PowerShell：

```powershell
python -m pip install -r database/seed/requirements.txt

# 默认读取项目 .env 中的 DATABASE_URL；环境变量优先于 .env。
# 也可分别配置 MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE。
# 不要把真实密码直接放到命令行或版本库。
$env:SEED_PASSWORD_HASH = python -c "import bcrypt,getpass; print(bcrypt.hashpw(getpass.getpass('模拟账号密码: ').encode(),bcrypt.gensalt()).decode())"
```

数据库参数：`--database-url` 或 `--host --port --user --password --database`；也支持 `--ssl-ca` / MYSQL_SSL_CA。URL 中特殊字符需 URL 编码；URL 查询串不用于配置 TLS，使用显式 ssl-ca。合成账号共用传入的 bcrypt 哈希，明文不写表；此功能用于模拟账号。phone 为合成唯一标识，不能用于测试真实手机验证码登录。

## 执行顺序

```powershell
# 1. 只读核验结构、实时电影数和预计规模；不需要密码哈希。
python database/seed/generate_mock_data.py --seed 42 --run-tag aabb01 --as-of 2026-10-23T00:00:00Z

# 2. 小规模执行全部写入/校验并强制回滚，核对原有行数已恢复。
python database/seed/generate_mock_data.py --execute --rollback-test --movie-count 100 --ratings-per-user 8 --comments-per-user 2 --batch-size 10 --run-tag aabb02 --as-of 2026-10-23T00:00:00Z

# 3. 追加默认规模：只创建新模拟用户及其关联数据，不复用旧用户。
python database/seed/generate_mock_data.py --execute --mode append --seed 42 --batch-size 1000 --run-tag aabb03 --as-of 2026-10-23T00:00:00Z

# 4. 清空九张目标表的全部数据后重建：只在准备覆盖这些数据时运行。
python database/seed/generate_mock_data.py --execute --mode rebuild --seed 42 --run-tag aabb03 --as-of 2026-10-23T00:00:00Z

# 无连接环境：只做离线估算，基数由你明确指定。
python database/seed/generate_mock_data.py --offline --movie-count 50581 --movie-ratio 0.1
```

append 每次使用不同 run-tag，属于增加一批独立模拟用户，不是给同一用户增加历史。已有同名 run-tag 时拒绝写入，不使用 INSERT IGNORE 隐藏冲突。rebuild 会删除目标表中真实数据及模拟数据，必须明确选择；如果 commentreport 或其他非目标表仍引用目标用户/评论，DELETE 被 RESTRICT 拒绝，整个事务回滚，不删除额外表。不会动 movieinfo、adminuser、aerich 或训练数据。

脚本使用数据库命名锁协调自身的多个进程；该锁不能阻止应用写入。正式运行时暂停应用/其他写入任务，避免行数校验、全库一致性检查、清理或电影快照受并发修改影响。

所有校验在提交前执行，覆盖整张目标表，因此追加模式也可能因**原有脏数据**而失败。失败只回滚本次事务，不会替你修正历史记录。COMMIT 成功后不能通过再次 ROLLBACK 撤销；需要恢复备份或明确使用 rebuild。断线若恰好发生在 COMMIT 附近，先查询 run-tag 的用户及关联数据，确认是否已提交，再决定重跑；不要直接换 tag 重复追加。回滚测试不会保留数据，但会消耗自增值。

## 校验 SQL

行数检查，与日志中的 Existing counts / COMMITTED inserted counts 比较；追加应满足 after=before+inserted，重建应满足 after=inserted。随机事件数量以实际日志为准。

```sql
SELECT 'user' AS table_name, COUNT(*) AS row_count FROM `user`
UNION ALL SELECT 'personalratings',COUNT(*) FROM personalratings
UNION ALL SELECT 'moviecomment',COUNT(*) FROM moviecomment
UNION ALL SELECT 'userfavorite',COUNT(*) FROM userfavorite
UNION ALL SELECT 'commentlike',COUNT(*) FROM commentlike
UNION ALL SELECT 'commentlike_event',COUNT(*) FROM commentlike_event
UNION ALL SELECT 'recommendationitem',COUNT(*) FROM recommendationitem
UNION ALL SELECT 'recommendationevent',COUNT(*) FROM recommendationevent
UNION ALL SELECT 'recommendresult',COUNT(*) FROM recommendresult;
```

脚本按最新 SQL 的实际声明自动生成全部 NOT NULL、PK/UQ 重复、FK 孤儿及 CHECK 合法性查询，包括三个 active_* 生成列唯一键；没有把它们留给人工抽查。额外业务校验见 `database/seed/validate_mock_data.sql`，所有结果必须为 0。可单独在 MySQL 8 客户端运行该文件。

下面给出物理约束校验的代表 SQL；完整覆盖由脚本动态执行：

```sql
-- 全部 FK 的声明可用此查询审阅，包括字段名与父表字段。
SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL;

-- 孤儿：其他 FK 由脚本按相同模板逐条检查。
SELECT COUNT(*) AS orphans FROM personalratings r
LEFT JOIN `user` u ON r.userid=u.userid
LEFT JOIN movieinfo m ON r.movieid=m.movieid
WHERE u.userid IS NULL OR m.movieid IS NULL;

SELECT COUNT(*) AS orphans FROM recommendationevent e
LEFT JOIN recommendationitem i ON e.recommendationid=i.recommendationid
WHERE i.recommendationid IS NULL;

-- 唯一组合：其他 PK/UQ 由脚本按相同模板逐条检查。
SELECT userid,movieid,COUNT(*) FROM personalratings
GROUP BY userid,movieid HAVING COUNT(*)>1;
SELECT userid,commentid,COUNT(*) FROM commentlike
GROUP BY userid,commentid HAVING COUNT(*)>1;
SELECT request_id,movieid,COUNT(*) FROM recommendationitem
GROUP BY request_id,movieid HAVING COUNT(*)>1;

-- NOT NULL 和合法值。
SELECT COUNT(*) FROM `user` WHERE username IS NULL OR password IS NULL
 OR phone IS NULL OR email IS NULL OR status IS NULL;
SELECT COUNT(*) FROM personalratings WHERE rating IS NULL OR rating NOT BETWEEN 1 AND 10;
SELECT COUNT(*) FROM moviecomment WHERE moderation_status IS NULL
 OR moderation_status NOT IN ('published','review_pending','hidden');
SELECT COUNT(*) FROM commentlike WHERE is_active IS NULL OR is_active NOT IN (0,1);
SELECT COUNT(*) FROM commentlike_event WHERE action IS NULL OR action NOT IN ('like','unlike');
SELECT COUNT(*) FROM userfavorite WHERE status IS NULL OR status NOT IN ('want_to_watch','watched');
SELECT COUNT(*) FROM recommendationevent WHERE event_type IS NULL
 OR event_type NOT IN ('impression','click','not_interested');
```

完整独立校验文件：`database/seed/validate_all.sql`。涵盖全部声明约束与关键业务关联；以下为全文：

```sql
-- MySQL 8.0: all 56 SELECT results must be zero. Includes physical and business constraints.

SELECT COUNT(*) FROM `user` WHERE `userid` IS NULL OR `username` IS NULL OR `password` IS NULL OR `phone` IS NULL OR `email` IS NULL OR `status` IS NULL OR `created_at` IS NULL OR `updated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `userid` FROM `user` WHERE `userid` IS NOT NULL GROUP BY `userid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `active_email` FROM `user` WHERE `active_email` IS NOT NULL GROUP BY `active_email` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `active_phone` FROM `user` WHERE `active_phone` IS NOT NULL GROUP BY `active_phone` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `active_username` FROM `user` WHERE `active_username` IS NOT NULL GROUP BY `active_username` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `personalratings` WHERE `ratingid` IS NULL OR `userid` IS NULL OR `movieid` IS NULL OR `rating` IS NULL OR `rated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `ratingid` FROM `personalratings` WHERE `ratingid` IS NOT NULL GROUP BY `ratingid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `userid`,`movieid` FROM `personalratings` WHERE `userid` IS NOT NULL AND `movieid` IS NOT NULL GROUP BY `userid`,`movieid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `personalratings` c LEFT JOIN `movieinfo` p ON c.`movieid`=p.`movieid` WHERE c.`movieid` IS NOT NULL AND p.`movieid` IS NULL;

SELECT COUNT(*) FROM `personalratings` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `personalratings` WHERE NOT ((`rating` between 1 and 10));

SELECT COUNT(*) FROM `userfavorite` WHERE `id` IS NULL OR `userid` IS NULL OR `movieid` IS NULL OR `status` IS NULL OR `created_at` IS NULL OR `updated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `id` FROM `userfavorite` WHERE `id` IS NOT NULL GROUP BY `id` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `userid`,`movieid` FROM `userfavorite` WHERE `userid` IS NOT NULL AND `movieid` IS NOT NULL GROUP BY `userid`,`movieid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `userfavorite` c LEFT JOIN `movieinfo` p ON c.`movieid`=p.`movieid` WHERE c.`movieid` IS NOT NULL AND p.`movieid` IS NULL;

SELECT COUNT(*) FROM `userfavorite` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `userfavorite` WHERE NOT ((`status` in (_utf8mb4'want_to_watch',_utf8mb4'watched')));

SELECT COUNT(*) FROM `moviecomment` WHERE `commentid` IS NULL OR `userid` IS NULL OR `movieid` IS NULL OR `content` IS NULL OR `moderation_status` IS NULL OR `created_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `commentid` FROM `moviecomment` WHERE `commentid` IS NOT NULL GROUP BY `commentid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `moviecomment` c LEFT JOIN `movieinfo` p ON c.`movieid`=p.`movieid` WHERE c.`movieid` IS NOT NULL AND p.`movieid` IS NULL;

SELECT COUNT(*) FROM `moviecomment` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `moviecomment` WHERE NOT ((`moderation_status` in (_utf8mb4'published',_utf8mb4'review_pending',_utf8mb4'hidden')));

SELECT COUNT(*) FROM `commentlike` WHERE `id` IS NULL OR `userid` IS NULL OR `commentid` IS NULL OR `is_active` IS NULL OR `created_at` IS NULL OR `updated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `id` FROM `commentlike` WHERE `id` IS NOT NULL GROUP BY `id` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `userid`,`commentid` FROM `commentlike` WHERE `userid` IS NOT NULL AND `commentid` IS NOT NULL GROUP BY `userid`,`commentid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `commentlike` c LEFT JOIN `moviecomment` p ON c.`commentid`=p.`commentid` WHERE c.`commentid` IS NOT NULL AND p.`commentid` IS NULL;

SELECT COUNT(*) FROM `commentlike` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `commentlike_event` WHERE `eventid` IS NULL OR `userid` IS NULL OR `commentid` IS NULL OR `action` IS NULL OR `created_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `eventid` FROM `commentlike_event` WHERE `eventid` IS NOT NULL GROUP BY `eventid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `commentlike_event` c LEFT JOIN `moviecomment` p ON c.`commentid`=p.`commentid` WHERE c.`commentid` IS NOT NULL AND p.`commentid` IS NULL;

SELECT COUNT(*) FROM `commentlike_event` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `commentlike_event` WHERE NOT ((`action` in (_utf8mb4'like',_utf8mb4'unlike')));

SELECT COUNT(*) FROM `recommendationitem` WHERE `recommendationid` IS NULL OR `request_id` IS NULL OR `userid` IS NULL OR `movieid` IS NULL OR `position` IS NULL OR `generated_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `recommendationid` FROM `recommendationitem` WHERE `recommendationid` IS NOT NULL GROUP BY `recommendationid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM (SELECT `request_id`,`movieid` FROM `recommendationitem` WHERE `request_id` IS NOT NULL AND `movieid` IS NOT NULL GROUP BY `request_id`,`movieid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `recommendationitem` c LEFT JOIN `movieinfo` p ON c.`movieid`=p.`movieid` WHERE c.`movieid` IS NOT NULL AND p.`movieid` IS NULL;

SELECT COUNT(*) FROM `recommendationitem` c LEFT JOIN `user` p ON c.`userid`=p.`userid` WHERE c.`userid` IS NOT NULL AND p.`userid` IS NULL;

SELECT COUNT(*) FROM `recommendationevent` WHERE `eventid` IS NULL OR `recommendationid` IS NULL OR `event_type` IS NULL OR `created_at` IS NULL;

SELECT COUNT(*) FROM (SELECT `eventid` FROM `recommendationevent` WHERE `eventid` IS NOT NULL GROUP BY `eventid` HAVING COUNT(*)>1) d;

SELECT COUNT(*) FROM `recommendationevent` c LEFT JOIN `recommendationitem` p ON c.`recommendationid`=p.`recommendationid` WHERE c.`recommendationid` IS NOT NULL AND p.`recommendationid` IS NULL;

SELECT COUNT(*) FROM `recommendationevent` WHERE NOT ((`event_type` in (_utf8mb4'impression',_utf8mb4'click',_utf8mb4'not_interested')));






SELECT COUNT(*) FROM recommendresult r
LEFT JOIN `user` u ON u.userid=r.userid
LEFT JOIN movieinfo m ON m.movieid=r.movieid
WHERE r.userid IS NULL OR r.movieid IS NULL OR u.userid IS NULL OR m.movieid IS NULL;




SELECT COUNT(*) FROM (
  SELECT userid,movieid FROM recommendresult GROUP BY userid,movieid HAVING COUNT(*)>1
) duplicates;




SELECT COUNT(*) FROM (
  SELECT request_id FROM recommendationitem GROUP BY request_id
  HAVING COUNT(DISTINCT userid)<>1 OR COUNT(DISTINCT generated_at)<>1
     OR MIN(position)<>1 OR MAX(position)<>COUNT(*) OR COUNT(DISTINCT position)<>COUNT(*)
) bad_requests;




WITH first_impression AS (
 SELECT recommendationid,MIN(created_at) exposed_at FROM recommendationevent
 WHERE event_type='impression' GROUP BY recommendationid
)
SELECT COUNT(*) FROM recommendationevent e
JOIN recommendationitem i ON i.recommendationid=e.recommendationid
LEFT JOIN first_impression p ON p.recommendationid=e.recommendationid
WHERE e.created_at<i.generated_at OR
 (e.event_type IN ('click','not_interested') AND
  (p.recommendationid IS NULL OR p.exposed_at>e.created_at));




WITH ranked AS (
 SELECT e.*,ROW_NUMBER() OVER (
   PARTITION BY userid,commentid ORDER BY created_at DESC,eventid DESC
 ) rn FROM commentlike_event e
)
SELECT COUNT(*) FROM commentlike l LEFT JOIN ranked e
ON e.userid=l.userid AND e.commentid=l.commentid AND e.rn=1
WHERE e.eventid IS NULL OR l.is_active NOT IN (0,1)
 OR l.is_active<>(e.action='like') OR l.updated_at<>e.created_at
 OR l.created_at>l.updated_at;




SELECT COUNT(*) FROM commentlike_event e LEFT JOIN commentlike l
ON l.userid=e.userid AND l.commentid=e.commentid WHERE l.id IS NULL;




WITH history AS (
 SELECT e.*,LAG(action) OVER (
   PARTITION BY userid,commentid ORDER BY created_at,eventid
 ) previous_action,LAG(created_at) OVER (
   PARTITION BY userid,commentid ORDER BY created_at,eventid
 ) previous_time FROM commentlike_event e
)
SELECT COUNT(*) FROM history WHERE (previous_action IS NULL AND action<>'like')
 OR previous_action=action OR previous_time>=created_at;



WITH first_like AS (
 SELECT userid,commentid,MIN(created_at) first_at
 FROM commentlike_event GROUP BY userid,commentid
)
SELECT COUNT(*) FROM commentlike l JOIN first_like e
 ON e.userid=l.userid AND e.commentid=l.commentid
 WHERE l.created_at<>e.first_at;



SELECT COUNT(*) FROM commentlike_event e
JOIN moviecomment c ON c.commentid=e.commentid JOIN `user` u ON u.userid=e.userid
WHERE e.created_at<c.created_at OR e.created_at<u.created_at;



SELECT COUNT(*) FROM personalratings r JOIN `user` u ON u.userid=r.userid
WHERE r.rated_at<u.created_at OR (r.timestamp IS NOT NULL AND
 (r.timestamp NOT REGEXP '^[0-9]{1,10}$' OR
  CAST(r.timestamp AS UNSIGNED)<>TIMESTAMPDIFF(SECOND,'1970-01-01 00:00:00',r.rated_at)));



SELECT COUNT(*) FROM moviecomment c JOIN `user` u ON u.userid=c.userid
WHERE c.created_at<u.created_at OR c.deleted_at<c.created_at;



SELECT COUNT(*) FROM userfavorite f JOIN `user` u ON u.userid=f.userid
WHERE f.created_at<u.created_at OR f.updated_at<f.created_at
 OR f.deleted_at<f.created_at OR f.deleted_at>f.updated_at;



SELECT COUNT(*) FROM recommendationitem i JOIN `user` u ON u.userid=i.userid
WHERE i.generated_at<u.created_at;



SELECT COUNT(*) FROM `user` WHERE created_at>updated_at
 OR deleted_at<created_at OR deleted_at>updated_at;





WITH latest_request AS (
 SELECT i.userid,MAX(i.request_id) request_id
 FROM recommendationitem i JOIN `user` u ON u.userid=i.userid
 WHERE u.username REGEXP '^sim[0-9a-f]{1,12}_[0-9]{6}$'
 GROUP BY i.userid
)
SELECT COUNT(*) FROM recommendresult r JOIN `user` u ON u.userid=r.userid
LEFT JOIN latest_request lr ON lr.userid=r.userid
LEFT JOIN recommendationitem i FORCE INDEX (uk_recommendationitem_request_movie)
 ON i.request_id=lr.request_id AND i.movieid=r.movieid
LEFT JOIN movieinfo m ON m.movieid=i.movieid
WHERE u.username REGEXP '^sim[0-9a-f]{1,12}_[0-9]{6}$' AND
 (i.recommendationid IS NULL OR NOT (r.moviename<=>m.moviename)
  OR NOT (r.rating IS NULL AND i.movie_rating_snapshot IS NULL
      OR r.rating IS NOT NULL AND i.movie_rating_snapshot IS NOT NULL
         AND ABS(r.rating-i.movie_rating_snapshot)<0.0001));
```

## 已执行验证

已在当前 MySQL 8.0 数据库完成只读结构对照，所有目标表及电影表通过。以 3 个模拟用户、批量大小 2 验证 append 与 rebuild，两轮均通过约束和业务 SQL 后主动 ROLLBACK，恢复原有行数。覆盖 18 条评分、6 条评论、12 条收藏、12 条点赞关系、18 条推荐条目、9 条旧表镜像；再点赞用例 36 条点赞事件，取消后未再点赞用例 24 条点赞事件，每轮 36 条推荐事件。另通过单用户、单电影边界测试：评分/评论/收藏正确截断为 1，点赞关系为 0。独立执行全部 56 条校验 SQL，违规数均为 0。随后已完成默认规模的正式追加投放，新增 761,000 行，全部校验通过且已导出数据库；详见 [投放记录](mock-data-run.md)。
