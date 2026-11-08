# ratings.dat Import Record

The import used `data/raw/ratings.dat` (SHA-256 `f2ba11cda25e322bb1ea0b1309d6d1ebcf639c61461b09409dcd159c9aeef6db`) and `data/raw/movies.dat` as the authoritative movie ID/title source. Existing `movieinfo` metadata was retained; 47 missing rated movie IDs were added.

The Aerich migration `2_20261029160409_personalratings_zero_to_five.py` is applied. `personalratings.rating` is constrained to 0–5. The import maps each MovieLens user to a generated internal user named `ml1m_<six-digit external ID>` and writes all 878,415 ratings.

| Table | Rows after import |
|---|---:|
| `movieinfo` | 50,628 |
| `user` | 6,040 |
| `personalratings` | 878,415 |
| `moviecomment` | 24,160 |
| `commentlike` | 72,480 |
| `commentlike_event` | 87,183 |
| `userfavorite` | 60,400 |
| `recommendationitem` | 181,200 |
| `recommendationevent` | 174,295 |
| `recommendresult` | 60,400 |

The old user and behavior rows were cleared after confirming `commentreport` was empty. A rollback rehearsal passed before the final commit. Post-commit SQL checks found no rating range violations, rating duplicates, orphan references, invalid event state, or recommendation feedback at/before exposure. The rating distribution is 1: 50,030; 2: 96,671; 3: 233,647; 4: 307,916; 5: 190,151.

The full pre-import backup is `.local-backups/pre-ratings-import-20261029.sql.gz`. The post-import snapshot is `.local-backups/post-ratings-import-20261029.sql.gz`; the uncompressed current dump is `database/dumps/movierecommend.sql` (192,781,342 bytes, SHA-256 `e71f0f5e607097bc3864fe28343f8f902453b99c636e282ac8fd26fccea1fef7`). Both SQL snapshots include destructive table recreation statements and should only be restored into a disposable database or as part of an intentional full restore.
