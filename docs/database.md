# 鏁版嵁搴撶粨鏋勮鏄?
鏈枃妗ｆ弿杩板綋鍓?`movierecommend` MySQL 鏁版嵁搴撱€備笟鍔?schema 鐢?`backend/migrations/0001_schema_upgrade.sql` 寤虹珛锛孴ortoise ORM 瀹氫箟浣嶄簬 `backend/app/models.py`銆傚綋鍓嶆暟鎹簱鍙︽湁 Aerich 杩佺Щ鍏冩暟鎹〃 `aerich`銆?
## 绾﹀畾

- 鏁版嵁搴撲负 MySQL 8.0.42锛岃〃浣跨敤 InnoDB銆傛柊寤轰笟鍔¤〃浣跨敤 `utf8mb4_0900_ai_ci`锛涙部鐢ㄦ棫 schema 鐨?`user`銆乣movieinfo`銆乣personalratings`銆乣recommendresult` 浠嶄负 `utf8mb3_general_ci`銆俙user.active_username` 鐢熸垚鍒楀崟鐙娇鐢?`utf8mb4_0900_ai_ci`锛屽洜姝ゆ樀绉板敮涓€鎬уぇ灏忓啓涓嶆晱鎰熴€傛棫琛ㄥ瓧绗﹂泦鍚庣画鑻ラ渶缁熶竴锛屽簲鍗曠嫭璇勪及瀛楃杞崲鍜岀储寮曞奖鍝嶃€?- `DATETIME(6)` 鏈韩涓嶆惡甯︽椂鍖恒€傚簲鐢ㄩ€氳繃 Tortoise `use_tz=True`銆乣timezone="UTC"` 缁熶竴鎸?UTC 鍐欏叆鍜岃鍙栵紱Unix 绉掓椂闂存埑闇€鍏堣浆鎹负 UTC锛屽啀鍐欏叆 `rated_at` 鎴栧搴?UTC 鏃堕棿鍒椼€?- 涓氬姟鍏崇郴澶栭敭榛樿閲囩敤 `RESTRICT`锛岄樆姝㈢墿鐞嗗垹闄や粛琚紩鐢ㄧ殑鐢ㄦ埛銆佺數褰便€佽瘎璁烘垨鏁版嵁闆嗭紱涓炬姤澶勭悊浜哄閿?`handled_by_adminid` 浣跨敤 `SET NULL`銆備笟鍔¤处鍙枫€佺數褰便€佽瘎璁恒€佹敹钘忓拰鍒嗙被搴旈€氳繃 `deleted_at` 杞垹闄わ紱鍒嗘瀽鏌ヨ闇€鎸夋寚鏍囧彛寰勮繃婊よ蒋鍒犻櫎鏁版嵁銆?- `user` 鐨?`active_username`銆乣active_phone`銆乣active_email` 鏄暟鎹簱鐢熸垚鍒楋紝浠呯敤浜庢椿鍔ㄨ处鍙风殑鍞竴绾︽潫锛屼笉灞炰簬涓氬姟杈撳叆瀛楁銆傝蒋鍒犻櫎璐﹀彿瀵瑰簲鐢熸垚鍊间负 `NULL`锛屽厑璁哥浉鍚屾樀绉般€佹墜鏈哄彿鎴栭偖绠遍噸鏂版敞鍐屻€?- 鏃堕棿鍒楃殑 `CURRENT_TIMESTAMP(6)` 鍜?`ON UPDATE` 鏄暟鎹簱榛樿琛屼负锛涙湇鍔″啓鍏ユ椂闂村簲缁х画閬靛惊 UTC 绾﹀畾銆?- 涓嬫枃 `PK` 琛ㄧず涓婚敭锛宍FK` 琛ㄧず澶栭敭锛宍UQ` 琛ㄧず鍞竴绾︽潫锛宍IDX` 琛ㄧず鏅€氱储寮曪紝`CK` 琛ㄧず CHECK 绾︽潫銆?
## 鍏崇郴鎬昏

```text
user 鈹€鈹€< personalratings >鈹€鈹€ movieinfo
user 鈹€鈹€< moviecomment >鈹€鈹€鈹€鈹€鈹€ movieinfo
user 鈹€鈹€< commentlike >鈹€鈹€鈹€鈹€鈹€鈹€ moviecomment
user 鈹€鈹€< commentlike_event > moviecomment
user 鈹€鈹€< commentreport >鈹€鈹€鈹€鈹€ moviecomment 鈹€鈹€> adminuser (handled_by)
user 鈹€鈹€< userfavorite >鈹€鈹€鈹€鈹€鈹€ movieinfo
movieinfo 鈹€鈹€< moviecategory >鈹€鈹€ category
trainingdataset 鈹€鈹€< trainingrating >鈹€鈹€ movieinfo
user 鈹€鈹€< recommendationitem >鈹€鈹€ movieinfo 鈹€鈹€< recommendationevent
adminuser 鈹€鈹€< adminoperationlog
```

绗﹀彿 `A 鈹€鈹€< B` 琛ㄧず B 涓彲鏈夊鏉¤褰曞紩鐢?A銆傛帹鑽愪簨浠堕€氳繃 `recommendationid` 鍏宠仈鎺ㄨ崘椤癸紝鍐嶄粠鎺ㄨ崘椤瑰彇寰楃敤鎴峰拰鐢靛奖銆?
## 涓氬姟琛?
### `user`锛氭櫘閫氱敤鎴?
淇濆瓨娉ㄥ唽鐢ㄦ埛韬唤銆佺櫥褰曞拰璧勬枡淇℃伅锛涚鐞嗗憳璐﹀彿鍗曠嫭淇濆瓨鍦?`adminuser`銆?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `userid` | int | 鍚?| PK锛岃嚜澧炵敤鎴?ID銆?|
| `username` | varchar(50) | 鍚?| 鏄电О锛涙椿鍔ㄨ处鍙峰敮涓€涓斿ぇ灏忓啓涓嶆晱鎰熴€?|
| `password` | varchar(255) | 鍚?| 瀵嗙爜鍝堝笇锛屼笉寰椾繚瀛樻槑鏂囧瘑鐮併€?|
| `phone` | varchar(32) | 鍚?| 蹇呭～锛涙椿鍔ㄨ处鍙峰敮涓€銆?|
| `email` | varchar(254) | 鍚?| 蹇呭～锛涙椿鍔ㄨ处鍙峰敮涓€銆?|
| `avatar` | varchar(1000) | 鏄?| 澶村儚 URL 鎴栧瓨鍌ㄥ紩鐢ㄣ€?|
| `status` | varchar(20) | 鍚?| 榛樿 `active`锛涜处鍙风姸鎬佸€奸渶鐢卞簲鐢ㄧ害瀹氥€?|
| `created_at` / `updated_at` | datetime(6) | 鍚?| 鍒涘缓鍜屾渶鍚庢洿鏂版椂闂淬€?|
| `deleted_at` | datetime(6) | 鏄?| 杞垹闄ゆ椂闂达紱NULL 琛ㄧず鏈垹闄ゃ€?|
| `active_username` / `active_phone` / `active_email` | 鐢熸垚鍒?| 鏄?| 浠呮湭鍒犻櫎鐢ㄦ埛璁＄畻瀹為檯鍊硷紱鐢ㄤ簬涓変釜娲诲姩璐﹀彿鍞竴绱㈠紩銆?|

绾︽潫锛歅K `userid`锛沀Q `uk_user_active_username(active_username)`銆乣uk_user_active_phone(active_phone)`銆乣uk_user_active_email(active_email)`锛汭DX `idx_user_status_created(status, created_at)`銆乣idx_user_deleted_at(deleted_at)`銆傜敓鎴愬垪涓嶆槸鐢?ORM 鍒涘缓鐢ㄦ埛鏃朵紶鍏ョ殑瀛楁銆?
### `adminuser`锛氱鐞嗗憳

| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `adminid` | int | 鍚?| PK锛岃嚜澧炵鐞嗗憳 ID銆?|
| `username` | varchar(50) | 鍚?| 绠＄悊鍛樼櫥褰曞悕銆?|
| `password` | varchar(255) | 鍚?| 绠＄悊鍛樺瘑鐮佸搱甯屻€?|
| `role` | varchar(30) | 鍚?| 绠＄悊瑙掕壊銆?|
| `status` | varchar(20) | 鍚?| 榛樿 `active`銆?|
| `created_at` / `updated_at` | datetime(6) | 鍚?| 鍒涘缓鍜屾洿鏂版椂闂淬€?|
| `deleted_at` | datetime(6) | 鏄?| 绠＄悊鍛樿蒋鍒犻櫎鏃堕棿銆?|

绾︽潫锛歅K `adminid`锛沀Q `uk_adminuser_username(username)`锛汭DX `idx_adminuser_role_status(role, status)`锛汣K `chk_adminuser_role` 鍙厑璁?`admin`銆乣superadmin`銆傜鐞嗗憳鐢ㄦ埛鍚嶅綋鍓嶅敮涓€绾︽潫涓嶅洜杞垹闄ら噴鏀俱€?
### `movieinfo`锛氱數褰?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `movieid` | int | 鍚?| PK锛涘綋鍓?ID 鐢卞鍏ユ暟鎹彁渚涳紝涓嶆槸鑷鍒椼€?|
| `moviename` | varchar(1000) | 鏄?| 鐢靛奖鍚嶃€?|
| `releasetime` | date | 鏄?| 涓婃槧鏃ユ湡銆?|
| `director` / `leadactors` | varchar(1000) | 鏄?| 瀵兼紨鍜屼富婕旀枃鏈€?|
| `picture` | varchar(1000) | 鏄?| 鍥剧墖鍦板潃鎴栧瓨鍌ㄥ紩鐢ㄣ€?|
| `averating` | double(11,1) | 鏄?| 鐢靛奖璧勬枡涓殑骞冲潎鍒嗭紱闇€涓庣珯鍐呯敤鎴疯瘎鍒嗚仛鍚堝彛寰勫尯鍒嗐€?|
| `numrating` | int | 鏄?| 鐢靛奖璧勬枡涓殑璇勫垎鏁帮紱闇€鏄庣‘鍏舵暟鎹潵婧愩€?|
| `description` | varchar(1000) | 鏄?| 绠€浠嬨€?|
| `typelist` | varchar(255) | 鏄?| 鍘熷閫楀彿鍒嗛殧绫诲瀷锛屼繚鐣欑敤浜庡吋瀹癸紱瑙勮寖鍏崇郴瑙?`moviecategory`銆?|
| `updated_at` | datetime(6) | 鍚?| 鏇存柊鏃堕棿銆?|
| `deleted_at` | datetime(6) | 鏄?| 鐢靛奖杞垹闄ゆ椂闂淬€?|

绾︽潫锛歅K `movieid`锛汭DX `idx_movieinfo_rating(averating)`銆乣idx_movieinfo_popularity(numrating)`銆乣idx_movieinfo_release(releasetime)`銆乣idx_movieinfo_deleted_at(deleted_at)`銆備笟鍔″垪琛ㄩ粯璁よ繃婊?`deleted_at IS NOT NULL` 鐨勭數褰憋紱鍘嗗彶璇勫垎鍜屽弽棣堜粛淇濈暀銆?
### `personalratings`锛氱珯鍐呯敤鎴疯瘎鍒?
淇濆瓨娉ㄥ唽鐢ㄦ埛褰撳墠鏈夋晥璇勫垎锛屾瘡涓敤鎴峰姣忛儴鐢靛奖鑷冲涓€鏉°€備慨鏀硅瘎鍒嗘槸鏇存柊褰撳墠璁板綍锛屼笉淇濈暀姣忔淇敼鍘嗗彶銆?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `ratingid` | bigint | 鍚?| PK锛岃嚜澧炶瘎鍒嗚褰?ID銆?|
| `userid` | int | 鍚?| FK 鈫?`user.userid`銆?|
| `movieid` | int | 鍚?| FK 鈫?`movieinfo.movieid`銆?|
| `rating` | int | 鍚?| 1鈥?0 鍒嗐€?|
| `rated_at` | datetime(6) | 鍚?| 褰撳墠璇勫垎鏃堕棿锛屾寜 UTC 瀛樺偍銆?|
| `timestamp` | char(10) | 鏄?| 鏃?Unix 鏃堕棿鎴冲瓧娈碉紝浣滀负鍏煎/瀹¤瀛楁鏆傜暀锛涙柊閫昏緫浣跨敤 `rated_at`銆?|

绾︽潫锛歅K `ratingid`锛沀Q `uk_personalratings_user_movie(userid, movieid)`锛汧K `fk_personalratings_user`銆乣fk_personalratings_movie`锛屽垹闄よ鍒欏潎涓?RESTRICT锛汣K `chk_personalratings_rating` 闄愬埗 1鈥?0锛汭DX `idx_personalratings_movie_rating(movieid, rating)`銆乣idx_personalratings_user_rated(userid, rated_at)`銆?
ALS 鏄惧紡鍙嶉鍙粠 `(userid, movieid, rating)` 璇诲彇銆傚鍑哄埌 Spark 鍓嶉渶鍐冲畾鏄惁杩囨护杞垹闄ょ敤鎴?鐢靛奖锛涘綋鍓嶈〃涓嶅惈鐙珛鐨勮瘎鍒嗗彉鏇翠簨浠躲€?
### `trainingdataset`锛氱绾胯缁冩暟鎹泦鍏冧俊鎭?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `datasetid` | int | 鍚?| PK锛岃嚜澧炴暟鎹泦 ID銆?|
| `dataset_key` | varchar(100) | 鍚?| 绋冲畾鐨勬暟鎹泦涓氬姟鏍囪瘑銆?|
| `source_name` | varchar(255) | 鍚?| 鏁版嵁婧愬悕绉般€?|
| `rating_min` / `rating_max` | decimal(5,2) | 鍚?| 鍘熷璇勫垎鑼冨洿杈圭晫銆?|
| `created_at` | datetime(6) | 鍚?| 鏁版嵁闆嗚褰曞垱寤烘椂闂淬€?|

绾︽潫锛歅K `datasetid`锛沀Q `uk_trainingdataset_key(dataset_key)`锛汣K `chk_trainingdataset_rating_range(rating_min < rating_max)`銆傝琛ㄧ洰鍓嶄笉璁板綍鏂囦欢璺緞銆佹牎楠屽拰銆佸鍏ョ姸鎬佹垨璁稿彲淇℃伅銆?
### `trainingrating`锛氱绾胯缁冭瘎鍒嗘槑缁?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `trainingratingid` | bigint | 鍚?| PK锛岃嚜澧炲鍏ヨ ID銆?|
| `datasetid` | int | 鍚?| FK 鈫?`trainingdataset.datasetid`銆?|
| `external_userid` | int | 鍚?| 鍘熷鏁版嵁闆嗕腑鐨勭敤鎴?ID锛屼笉鏄珯鍐?`userid`銆?|
| `movieid` | int | 鍚?| FK 鈫?`movieinfo.movieid`銆?|
| `rating` | decimal(5,2) | 鍚?| 鍘熷璇勫垎锛涘鍏ユ椂鎸夋暟鎹泦璇勫垎鑼冨洿楠岃瘉銆?|
| `rated_at` | datetime(6) | 鏄?| 鍘熷璇勫垎鏃堕棿锛涜嫢婧愭椂闂村瓨鍦紝杞崲涓?UTC銆?|

绾︽潫锛歅K `trainingratingid`锛沀Q `uk_trainingrating_dataset_user_movie(datasetid, external_userid, movieid)`锛汧K `fk_trainingrating_dataset`銆乣fk_trainingrating_movie`锛屽垹闄よ鍒欎负 RESTRICT锛汭DX `idx_trainingrating_movie(movieid)`銆乣idx_trainingrating_dataset_user(datasetid, external_userid)`銆傝法鏁版嵁闆嗚缁冩椂澶栭儴鐢ㄦ埛 ID 鍙兘閲嶅锛孲park 渚у簲浣跨敤鏁版嵁闆嗙淮搴︽瀯閫犺缁冪敤鎴烽敭鎴栭噸鏂扮紪鐮佽繛缁暣鏁?ID銆?
### `category`锛氱數褰辩被鍨?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `categoryid` | int | 鍚?| PK锛岃嚜澧炲垎绫?ID銆?|
| `name` | varchar(100) | 鍚?| 鍒嗙被鍚嶇О銆?|
| `created_at` | datetime(6) | 鍚?| 鍒涘缓鏃堕棿銆?|
| `deleted_at` | datetime(6) | 鏄?| 杞垹闄ゆ椂闂淬€?|

绾︽潫锛歅K `categoryid`锛沀Q `uk_category_name(name)`銆傚敮涓€绾︽潫娌℃湁鎸夎蒋鍒犻櫎鐘舵€佸尯鍒嗭紱鍚屽悕鍒嗙被涓嶈兘閲嶅鎻掑叆銆?
### `moviecategory`锛氱數褰变笌绫诲瀷鍏宠仈

| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `id` | bigint | 鍚?| PK锛岃嚜澧炲叧鑱?ID銆?|
| `movieid` | int | 鍚?| FK 鈫?`movieinfo.movieid`銆?|
| `categoryid` | int | 鍚?| FK 鈫?`category.categoryid`銆?|

绾︽潫锛歅K `id`锛沀Q `uk_moviecategory_movie_category(movieid, categoryid)`锛汭DX `idx_moviecategory_category_movie(categoryid, movieid)`锛涗袱涓?FK 鍧囦负 RESTRICT銆傜數褰辩瓫閫夊拰绫诲瀷鑱氬悎搴斾娇鐢ㄨ琛紱`movieinfo.typelist` 鏄吋瀹瑰瓧娈碉紝涓嶅簲涓庡叧鑱旇〃褰㈡垚鍙岄噸鍐欏叆婧愩€?
### `moviecomment`锛氱數褰辫瘎璁?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `commentid` | bigint | 鍚?| PK锛岃嚜澧炶瘎璁?ID銆?|
| `userid` | int | 鍚?| FK 鈫?`user.userid`銆?|
| `movieid` | int | 鍚?| FK 鈫?`movieinfo.movieid`銆?|
| `content` | varchar(500) | 鍚?| 璇勮鍐呭锛涗笟鍔¤鍒欎笉鍏佽淇敼銆?|
| `moderation_status` | varchar(20) | 鍚?| 榛樿 `published`锛涘厑璁?`published`銆乣review_pending`銆乣hidden`銆?|
| `created_at` | datetime(6) | 鍚?| 璇勮鍒涘缓鏃堕棿銆?|
| `deleted_at` | datetime(6) | 鏄?| 璇勮杞垹闄ゆ椂闂淬€?|

绾︽潫锛歅K `commentid`锛汧K `fk_moviecomment_user`銆乣fk_moviecomment_movie`锛屽潎涓?RESTRICT锛汭DX `idx_moviecomment_movie_created(movieid, created_at)`銆乣idx_moviecomment_user_created(userid, created_at)`銆乣idx_moviecomment_moderation_created(moderation_status, created_at)`锛汣K `chk_moviecomment_moderation_status`銆傝涓炬姤鍚庝粛灞曠ず浣嗚繘鍏?`review_pending`锛涚粨妗堟帴鍙楀悗鏀逛负 `hidden`锛岄┏鍥炲悗鎭㈠ `published`銆傚睍绀鸿瘎璁哄簲鍚屾椂杩囨护杞垹闄わ紝骞舵寜鐘舵€佽鍒欑瓫閫夈€?
### `commentlike`锛氳瘎璁哄綋鍓嶇偣璧炵姸鎬?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `id` | bigint | 鍚?| PK锛岃嚜澧炲叧绯?ID銆?|
| `userid` | int | 鍚?| FK 鈫?`user.userid`銆?|
| `commentid` | bigint | 鍚?| FK 鈫?`moviecomment.commentid`銆?|
| `is_active` | tinyint(1) | 鍚?| 褰撳墠鐐硅禐鐘舵€侊紝榛樿 1锛涘彇娑堝悗涓?0銆?|
| `created_at` / `updated_at` | datetime(6) | 鍚?| 鐐硅禐鍏崇郴鍒涘缓鍜屾渶杩戠姸鎬佹敼鍙樻椂闂淬€?|

绾︽潫锛歅K `id`锛沀Q `uk_commentlike_user_comment(userid, commentid)` 淇濊瘉姣忎汉姣忔潯璇勮鍙湁涓€涓綋鍓嶇姸鎬佽锛汭DX `idx_commentlike_comment_active(commentid, is_active)`锛涗袱涓?FK 鍧囦负 RESTRICT銆傞噸鐐硅禐鏇存柊鐜版湁琛岋紝鑰岄潪鎻掑叆閲嶅褰撳墠鐘舵€併€?
### `commentlike_event`锛氱偣璧炴搷浣滄棩蹇?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `eventid` | bigint | 鍚?| PK锛岃嚜澧炰簨浠?ID銆?|
| `userid` | int | 鍚?| FK 鈫?`user.userid`銆?|
| `commentid` | bigint | 鍚?| FK 鈫?`moviecomment.commentid`銆?|
| `action` | varchar(10) | 鍚?| `like` 鎴?`unlike`銆?|
| `created_at` | datetime(6) | 鍚?| 鎿嶄綔鍙戠敓鏃堕棿銆?|

绾︽潫锛歅K `eventid`锛汣K `chk_commentlike_event_action`锛汭DX `idx_commentlike_event_comment_created(commentid, created_at)`銆乣idx_commentlike_event_user_created(userid, created_at)`锛涗袱涓?FK 鍧囦负 RESTRICT銆傝琛ㄥ彧杩藉姞浜嬩欢锛屾寜瑕佹眰涓嶈鑷姩娓呯悊鏈熼檺銆?
### `commentreport`锛氳瘎璁轰妇鎶ヤ笌缁撴

| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `reportid` | bigint | 鍚?| PK锛岃嚜澧炰妇鎶?ID銆?|
| `commentid` | bigint | 鍚?| FK 鈫?`moviecomment.commentid`銆?|
| `reporter_userid` | int | 鍚?| FK 鈫?`user.userid`銆?|
| `reason_code` | varchar(40) | 鍚?| 涓炬姤鍘熷洜浠ｇ爜銆?|
| `reason_detail` | varchar(500) | 鏄?| 閫夋嫨 `other` 鏃跺繀濉€?|
| `status` | varchar(20) | 鍚?| 榛樿 `pending`锛涘厑璁?`pending`銆乣accepted`銆乣rejected`銆?|
| `created_at` | datetime(6) | 鍚?| 涓炬姤鏃堕棿銆?|
| `handled_at` | datetime(6) | 鏄?| 鍚庡彴缁撴鏃堕棿銆?|
| `handled_by_adminid` | int | 鏄?| FK 鈫?`adminuser.adminid`锛涘垹闄ょ鐞嗗憳鏃惰涓?NULL銆?|

绾︽潫锛歅K `reportid`锛沀Q `uk_commentreport_reporter_comment(reporter_userid, commentid)` 闄愬埗鍚屼竴鐢ㄦ埛瀵瑰悓涓€璇勮鍙兘涓炬姤涓€娆★紱IDX `idx_commentreport_status_created(status, created_at)`锛汧K `fk_commentreport_comment`銆乣fk_commentreport_reporter` 涓?RESTRICT锛宍fk_commentreport_admin` 涓?SET NULL銆傚師鍥犱唬鐮侊細`malicious_attack`銆乣insulting_language`銆乣harmful_information`銆乣excessive_promotion`銆乣advertisement`銆乣other`銆侰K `chk_commentreport_reason`銆乣chk_commentreport_other_detail`銆乣chk_commentreport_status` 鏍￠獙鍘熷洜銆佸叾浠栧師鍥犺鎯呭強鐘舵€併€?
### `userfavorite`锛氱敤鎴风數褰辨敹钘?
| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `id` | bigint | 鍚?| PK锛岃嚜澧炴敹钘忓叧绯?ID銆?|
| `userid` | int | 鍚?| FK 鈫?`user.userid`銆?|
| `movieid` | int | 鍚?| FK 鈫?`movieinfo.movieid`銆?|
| `status` | varchar(30) | 鍚?| `want_to_watch` 鎴?`watched`銆?|
| `created_at` / `updated_at` | datetime(6) | 鍚?| 鍏崇郴鍒涘缓鍜屾渶杩戞洿鏂版椂闂淬€?|
| `deleted_at` | datetime(6) | 鏄?| 鍙栨秷鏀惰棌鏃堕棿锛汵ULL 涓哄綋鍓嶆湁鏁堟敹钘忋€?|

绾︽潫锛歅K `id`锛沀Q `uk_userfavorite_user_movie(userid, movieid)`锛汭DX `idx_userfavorite_user_status_deleted(userid, status, deleted_at)`銆乣idx_userfavorite_movie_status_deleted(movieid, status, deleted_at)`锛汧K 鍧囦负 RESTRICT銆傚彇娑堟敹钘忎繚鐣欒骞惰缃?`deleted_at`锛涘啀娆℃敹钘忔仮澶嶅師琛屻€佹竻绌?`deleted_at` 骞舵洿鏂?`updated_at`銆傚悓涓€鐢ㄦ埛瀵瑰悓涓€鐢靛奖濮嬬粓澶嶇敤涓€鏉″叧绯汇€?
### `adminoperationlog`锛氱鐞嗗憳鎿嶄綔瀹¤

| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `logid` | bigint | 鍚?| PK锛岃嚜澧炴棩蹇?ID銆?|
| `adminid` | int | 鍚?| FK 鈫?`adminuser.adminid`銆?|
| `action` | varchar(100) | 鍚?| 鎿嶄綔绫诲瀷銆?|
| `target_type` | varchar(50) | 鍚?| 鎿嶄綔鐩爣绫诲瀷銆?|
| `target_id` | varchar(100) | 鏄?| 鐩爣 ID锛屼互瀛楃涓插吋瀹逛笉鍚屽疄浣撲富閿被鍨嬨€?|
| `detail` | json | 鏄?| 鎵╁睍鎿嶄綔鏄庣粏銆?|
| `created_at` | datetime(6) | 鍚?| 鎿嶄綔鏃堕棿銆?|

绾︽潫锛歅K `logid`锛汭DX `idx_adminoperationlog_admin_created(adminid, created_at)`銆乣idx_adminoperationlog_target(target_type, target_id)`锛汧K `fk_adminoperationlog_admin` 涓?RESTRICT銆傛棩蹇楁寜瑕佹眰闀挎湡淇濈暀锛屼笉璁剧疆鑷姩杩囨湡銆?
### `recommendationitem`锛氭帹鑽愭壒娆′腑鐨勭數褰遍」

| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `recommendationid` | bigint | 鍚?| PK锛岃嚜澧炴帹鑽愰」 ID銆?|
| `request_id` | varchar(64) | 鍚?| 涓€娆℃帹鑽愯姹?鎵规鏍囪瘑銆?|
| `userid` | int | 鍚?| FK 鈫?`user.userid`锛涘彧闈㈠悜鐧诲綍鐢ㄦ埛鎺ㄨ崘銆?|
| `movieid` | int | 鍚?| FK 鈫?`movieinfo.movieid`銆?|
| `position` | int | 鍚?| 璇ョ數褰卞湪鏈壒娆＄殑鎺掑簭浣嶇疆銆?|
| `movie_rating_snapshot` | decimal(4,1) | 鏄?| 鐢熸垚鏃剁數褰变笟鍔¤瘎鍒嗗揩鐓э紝涓嶆槸 ALS 棰勬祴鍊笺€?|
| `prediction_score` | decimal(10,6) | 鏄?| ALS 鎴栧叾浠栫畻娉曠殑棰勬祴鍒?鎺掑簭鍒嗐€?|
| `algorithm_version` | varchar(100) | 鏄?| 绠楁硶鎴栨ā鍨嬬増鏈爣璇嗐€?|
| `generated_at` | datetime(6) | 鍚?| 鎺ㄨ崘椤圭敓鎴愭椂闂淬€?|

绾︽潫锛歅K `recommendationid`锛沀Q `uk_recommendationitem_request_movie(request_id, movieid)`锛岄伩鍏嶄竴涓姹傞噸澶嶆帹鑽愬悓涓€鐢靛奖锛汭DX `idx_recommendationitem_user_generated(userid, generated_at)`锛汧K 鐢ㄦ埛鍜岀數褰卞潎涓?RESTRICT銆傚綋鍓嶆病鏈夌嫭绔嬫帹鑽愯姹傝〃锛宍request_id` 鐨勭敤鎴峰綊灞炲拰浣嶇疆鍞竴鎬х敱搴旂敤淇濊瘉銆?
### `recommendationevent`锛氭帹鑽愭洕鍏変笌鍙嶉浜嬩欢

| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `eventid` | bigint | 鍚?| PK锛岃嚜澧炰簨浠?ID銆?|
| `recommendationid` | bigint | 鍚?| FK 鈫?`recommendationitem.recommendationid`銆?|
| `event_type` | varchar(20) | 鍚?| `impression`銆乣click` 鎴?`not_interested`銆?|
| `created_at` | datetime(6) | 鍚?| 浜嬩欢鏃堕棿銆?|

绾︽潫锛歅K `eventid`锛汣K `chk_recommendationevent_type`锛汭DX `idx_recommendationevent_type_created(event_type, created_at)`銆乣idx_recommendationevent_item_type(recommendationid, event_type)`锛汧K `fk_recommendationevent_item` 涓?RESTRICT銆傛洕鍏夊簲鍦ㄦ帹鑽愰」瀹為檯杩涘叆鍙鍖哄煙鏃惰褰曘€傜敤鎴峰拰鐢靛奖淇℃伅閫氳繃鎺ㄨ崘椤硅繛鎺ュ彇寰楋紱鍚屼竴鎺ㄨ崘椤瑰彲鏈夊涓涓轰簨浠躲€傛洕鍏夊幓閲嶃€丆TR 鍒嗘瘝銆佺偣鍑诲綊鍥犵獥鍙ｅ拰閲嶅鐐瑰嚮鍙ｅ緞浠嶉渶鐢卞垎鏋愯鑼冪‘瀹氥€?
## 鍏煎涓庤縼绉昏緟鍔╄〃

### `recommendresult`锛氭棫鐗堟帹鑽愮粨鏋滃吋瀹硅〃

| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `userid` | int | 鏄?| 鏃х粨鏋滀腑鐨勭敤鎴?ID锛涙棤 FK銆?|
| `movieid` | int | 鏄?| 鏃х粨鏋滀腑鐨勭數褰?ID锛涙棤 FK銆?|
| `rating` | float | 鏄?| **鐢靛奖璇勫垎**锛屼笉鏄?ALS 棰勬祴鍒嗐€?|
| `moviename` | varchar(1000) | 鏄?| 鐢靛奖鍚嶅揩鐓с€?|

鏃ц〃鏃?PK銆丗K銆佺储寮曘€佹壒娆°€佷綅缃€佺畻娉曠増鏈垨鏇濆厜鍙嶉瀛楁锛屼笉鑳借繕鍘熷巻鍙叉帹鑽愬弽棣堛€傚綋鍓?ORM 鏈槧灏勬琛紱淇濈暀銆佷笅绾挎垨杩佺Щ鑷?`recommendationitem` 鐨勮鍒掗渶缁撳悎鏃ф帴鍙ｇ‘璁ゃ€?
### `aerich`锛氳縼绉荤増鏈厓鏁版嵁

| 瀛楁 | 绫诲瀷 | 鍙┖ | 璇存槑 |
|---|---|---:|---|
| `id` | int | 鍚?| PK锛岃嚜澧炲唴閮?ID銆?|
| `version` | varchar(255) | 鍚?| 宸插簲鐢ㄨ縼绉绘枃浠跺悕銆?|
| `app` | varchar(100) | 鍚?| Tortoise app 鍚嶇О銆?|
| `content` | json | 鍚?| Aerich 淇濆瓨鐨勬ā鍨嬬姸鎬佸揩鐓с€?|

璇ヨ〃鐢?Aerich 浣跨敤锛屼笉鎵胯浇涓氬姟鏁版嵁锛涗笉瑕佹墜宸ョ紪杈戞垨娓呯┖銆傚綋鍓嶉涓凡搴旂敤杩佺Щ涓?`1_schema_upgrade.py`銆?
## 鍒嗘瀽鎸囨爣涓庡叧鑱旇矾寰?
| 鎸囨爣 | 涓昏鏁版嵁婧?| 鍏抽敭杩囨护/杩炴帴 |
|---|---|---|
| 绔欏唴璇勫垎鍒嗗竷銆佺數褰辫瘎鍒嗗潎鍊煎拰浜烘暟 | `personalratings` | 鎸?`rating`銆乣movieid` 鑱氬悎锛涜嫢鏄剧ず鏈夋晥鐢靛奖鍒欒繛鎺?`movieinfo` 骞舵帓闄よ蒋鍒犻櫎鐢靛奖銆?|
| 绂荤嚎鏁版嵁闆嗚瘎鍒嗗垎甯?| `trainingrating`銆乣trainingdataset` | 閫氳繃 `datasetid` 鍒嗘暟鎹泦锛涗笉瑕佹妸 `external_userid` 褰撲綔 `user.userid`銆?|
| 璇勮鏁颁笌瀹℃牳闃熷垪 | `moviecomment` | 缁熻鍓嶆帓闄?`deleted_at` 闈?NULL锛涙寜 `moderation_status` 鍒嗙粍銆?|
| 鐐硅禐褰撳墠閲?| `commentlike` | 杩囨护 `is_active = 1`銆?|
| 鐐硅禐/鍙栨秷鎿嶄綔閲?| `commentlike_event` | 鎸?`action`銆乣created_at` 鑱氬悎銆?|
| 涓炬姤閲忋€佸緟澶勭悊閲忋€佸鐞嗘椂闀?| `commentreport` | 鎸?`status`銆乣created_at` 鑱氬悎锛涘鐞嗘椂闀跨敱 `handled_at - created_at` 璁＄畻銆?|
| 鎯崇湅/宸茬湅鏁伴噺 | `userfavorite` | 鎺掗櫎 `deleted_at` 闈?NULL锛屾寜 `status` 鑱氬悎銆?|
| 鎺ㄨ崘鏇濆厜銆佺偣鍑汇€佷笉鎰熷叴瓒?| `recommendationevent` + `recommendationitem` | 浜嬩欢鍏宠仈鎺ㄨ崘椤逛互鍙栧緱鐢ㄦ埛銆佺數褰便€佹壒娆°€佷綅缃拰绠楁硶鐗堟湰锛涙寚鏍囧幓閲嶄笌鍒嗘瘝灏氭湭瀹氫箟銆?|
| 绠＄悊鎿嶄綔閲?| `adminoperationlog` | 鎸夌鐞嗗憳銆佹搷浣滅被鍨嬨€佺洰鏍囧拰 UTC 鏃堕棿鑼冨洿鑱氬悎銆?|

## 鏁版嵁澶勭悊浜ゆ帴娉ㄦ剰浜嬮」

- ALS 鏄惧紡璇勫垎婧愪互 `personalratings` 鐨勫綋鍓嶆湁鏁堣瘎鍒嗕负鍑嗭紱鑻ュ悎骞跺閮ㄦ暟鎹紝鍐嶈鍙?`trainingrating` 骞跺湪 Spark 渚ф瀯閫犱笉鍐茬獊鐨勭敤鎴风储寮曘€傚簲鐢ㄧ敤鎴疯〃涓虹┖鏃讹紝涓嶈兘鎶婂閮ㄨ瘎鍒嗕吉閫犳垚绔欏唴鐢ㄦ埛璇勫垎銆?- 鐢靛奖 ID 鐢辫緭鍏ユ暟鎹彁渚涖€傚閮ㄦ暟鎹泦鐨勭數褰?ID 蹇呴』鍏堟槧灏勫埌 `movieinfo.movieid`锛涗笉鑳界‘璁ゆ槧灏勬椂搴斿湪瀵煎叆灞備繚鐣欏閮ㄧ數褰遍敭骞堕殧绂绘湭鍖归厤琛岋紝褰撳墠 schema 灏氭棤閫氱敤鐢靛奖鏄犲皠琛ㄣ€?- `movieinfo.averating/numrating` 涓?`personalratings` 鑱氬悎缁撴灉鍙兘鏉ヨ嚜涓嶅悓鏉ユ簮锛涗笅娓告姤琛ㄥ拰鎺ㄨ崘鐗瑰緛蹇呴』鏍囨敞浣跨敤鍝鍙ｅ緞銆?- 璁粌浠诲姟銆佹暟鎹揩鐓х増鏈€佽瘎浼版寚鏍囥€佹ā鍨嬫枃浠朵綅缃€佷换鍔＄姸鎬佸拰妯″瀷鍙戝竷/鍥炴粴涓嶇敱褰撳墠涓氬姟琛ㄧ鐞嗐€傚叾鎸佷箙鍖栦綅缃笌 Celery/Spark 浣滀笟濂戠害闇€鍙﹁纭畾锛汻edis 鍙綔涓轰换鍔℃秷鎭唬鐞?鐭湡鐘舵€佸悗绔€?- MySQL 澶栭敭闄愬埗鐗╃悊鍒犻櫎锛屼絾杞垹闄や笉鑷姩绾ц仈銆傚垎鏋愭煡璇€丄LS 鏁版嵁鎶藉彇鍜屾帹鑽愬€欓€夎繃婊ら兘蹇呴』鏄庣‘鏄惁鎺掗櫎宸茶蒋鍒犻櫎鐨勭敤鎴枫€佺數褰便€佽瘎璁烘垨鍒嗙被銆?
## 褰撳墠闄愬埗涓庡緟瀹氬彛寰?
- `trainingdataset` 鐩墠鍙湁鍚嶇О鍜岃瘎鍒嗚寖鍥达紝缂哄皯鏁版嵁鐗堟湰銆佹潵婧愯鍙€佹牎楠屽拰銆佸鍏ョ姸鎬佸強璁板綍鏁扮瓑鍙鐜版€у厓鏁版嵁銆?- `personalratings` 鍙繚瀛樺綋鍓嶈瘎鍒嗭紱鑻ヨ鍒嗘瀽璇勫垎淇敼鍘嗗彶锛岄渶瑕佹柊澧炶拷鍔犲紡璇勫垎浜嬩欢琛ㄣ€?- 鎺ㄨ崘鎵规灏氭棤鐙珛鐖跺疄浣擄紝涓嶈兘鍗曠嫭淇濆瓨璇锋眰绾х姸鎬併€佸€欓€夋暟閲忔垨澶辫触淇℃伅锛涚洰鍓嶅彧鍙粠鎺ㄨ崘椤圭殑 `request_id` 鑱氬悎銆?- 鏇濆厜/鐐瑰嚮浜嬩欢鐨勫箓绛夐敭銆佸幓閲嶇獥鍙ｃ€丆TR 鍒嗘瘝銆佲€滀笉鎰熷叴瓒ｂ€濈巼瀹氫箟鍙婃帹鑽愯姹傚け璐ョ粺璁″彛寰勫緟纭銆?- `recommendresult` 鏄惁浠嶈鐜版湁鎺ュ彛浣跨敤鍙婂叾閫€褰规椂闂村緟纭銆?
