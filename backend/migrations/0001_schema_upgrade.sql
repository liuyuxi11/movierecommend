-- Upgrade the supplied movierecommend.sql schema to the ORM model schema.
-- Run against a backup of the target database. MySQL DDL auto-commits.
USE `movierecommend`;

-- User rows in the supplied dump are empty. Existing deployments with accounts
-- must backfill required fields and hash passwords before applying NOT NULL.
ALTER TABLE `user`
  MODIFY COLUMN `username` varchar(50) NOT NULL,
  MODIFY COLUMN `password` varchar(255) NOT NULL,
  ADD COLUMN `phone` varchar(32) NOT NULL,
  ADD COLUMN `email` varchar(254) NOT NULL,
  ADD COLUMN `avatar` varchar(1000) NULL,
  ADD COLUMN `status` varchar(20) NOT NULL DEFAULT 'active',
  ADD COLUMN `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  ADD COLUMN `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  ADD COLUMN `deleted_at` datetime(6) NULL,
  ADD COLUMN `active_username` varchar(50)
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci
    GENERATED ALWAYS AS (
      IF(`deleted_at` IS NULL, `username`, NULL)
    ) STORED,
  ADD COLUMN `active_phone` varchar(32)
    GENERATED ALWAYS AS (
      IF(`deleted_at` IS NULL, `phone`, NULL)
    ) STORED,
  ADD COLUMN `active_email` varchar(254)
    GENERATED ALWAYS AS (
      IF(`deleted_at` IS NULL, `email`, NULL)
    ) STORED,
  ADD UNIQUE KEY `uk_user_active_username` (`active_username`),
  ADD UNIQUE KEY `uk_user_active_phone` (`active_phone`),
  ADD UNIQUE KEY `uk_user_active_email` (`active_email`),
  ADD KEY `idx_user_status_created` (`status`, `created_at`),
  ADD KEY `idx_user_deleted_at` (`deleted_at`);

ALTER TABLE `movieinfo`
  ADD COLUMN `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  ADD COLUMN `deleted_at` datetime(6) NULL,
  ADD KEY `idx_movieinfo_rating` (`averating`),
  ADD KEY `idx_movieinfo_popularity` (`numrating`),
  ADD KEY `idx_movieinfo_release` (`releasetime`),
  ADD KEY `idx_movieinfo_deleted_at` (`deleted_at`);

-- Conflicting rows are deliberately cleared as requested: this table is for
-- registered application users, while imported ALS ratings live in trainingrating.
DELETE pr
FROM `personalratings` AS pr
LEFT JOIN `user` AS u ON u.`userid` = pr.`userid`
LEFT JOIN `movieinfo` AS m ON m.`movieid` = pr.`movieid`
WHERE u.`userid` IS NULL OR m.`movieid` IS NULL;

DELETE FROM `personalratings`
WHERE `rating` IS NULL
   OR `rating` NOT BETWEEN 1 AND 10
   OR `timestamp` IS NULL
   OR `timestamp` NOT REGEXP '^[0-9]{9,10}$';

ALTER TABLE `personalratings`
  ADD COLUMN `rated_at` datetime(6) NULL,
  ADD COLUMN `ratingid` bigint NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST,
  MODIFY COLUMN `userid` int NOT NULL,
  MODIFY COLUMN `movieid` int NOT NULL,
  MODIFY COLUMN `rating` int NOT NULL;

UPDATE `personalratings`
SET `rated_at` = TIMESTAMPADD(
  SECOND,
  CAST(`timestamp` AS UNSIGNED),
  '1970-01-01 00:00:00'
);

-- Keep one row per user/movie pair; remove duplicates before adding the key.
CREATE TEMPORARY TABLE `tmp_personalratings_keep` AS
SELECT `ratingid`
FROM (
  SELECT
    `ratingid`,
    ROW_NUMBER() OVER (
      PARTITION BY `userid`, `movieid`
      ORDER BY `ratingid`
    ) AS `row_number`
  FROM `personalratings`
) AS ranked
WHERE `row_number` = 1;

DELETE pr
FROM `personalratings` AS pr
LEFT JOIN `tmp_personalratings_keep` AS keep_row
  ON keep_row.`ratingid` = pr.`ratingid`
WHERE keep_row.`ratingid` IS NULL;

DROP TEMPORARY TABLE `tmp_personalratings_keep`;

ALTER TABLE `personalratings`
  MODIFY COLUMN `rated_at` datetime(6) NOT NULL,
  ADD UNIQUE KEY `uk_personalratings_user_movie` (`userid`, `movieid`),
  ADD KEY `idx_personalratings_movie_rating` (`movieid`, `rating`),
  ADD KEY `idx_personalratings_user_rated` (`userid`, `rated_at`),
  ADD CONSTRAINT `chk_personalratings_rating`
    CHECK (`rating` BETWEEN 1 AND 10),
  ADD CONSTRAINT `fk_personalratings_user`
    FOREIGN KEY (`userid`) REFERENCES `user` (`userid`) ON DELETE RESTRICT,
  ADD CONSTRAINT `fk_personalratings_movie`
    FOREIGN KEY (`movieid`) REFERENCES `movieinfo` (`movieid`) ON DELETE RESTRICT;

CREATE TABLE `trainingdataset` (
  `datasetid` int NOT NULL AUTO_INCREMENT,
  `dataset_key` varchar(100) NOT NULL,
  `source_name` varchar(255) NOT NULL,
  `rating_min` decimal(5,2) NOT NULL,
  `rating_max` decimal(5,2) NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`datasetid`),
  UNIQUE KEY `uk_trainingdataset_key` (`dataset_key`),
  CONSTRAINT `chk_trainingdataset_rating_range`
    CHECK (`rating_min` < `rating_max`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `trainingrating` (
  `trainingratingid` bigint NOT NULL AUTO_INCREMENT,
  `datasetid` int NOT NULL,
  `external_userid` int NOT NULL,
  `movieid` int NOT NULL,
  `rating` decimal(5,2) NOT NULL,
  `rated_at` datetime(6) NULL,
  PRIMARY KEY (`trainingratingid`),
  UNIQUE KEY `uk_trainingrating_dataset_user_movie`
    (`datasetid`, `external_userid`, `movieid`),
  KEY `idx_trainingrating_movie` (`movieid`),
  KEY `idx_trainingrating_dataset_user` (`datasetid`, `external_userid`),
  CONSTRAINT `fk_trainingrating_dataset`
    FOREIGN KEY (`datasetid`) REFERENCES `trainingdataset` (`datasetid`)
    ON DELETE RESTRICT,
  CONSTRAINT `fk_trainingrating_movie`
    FOREIGN KEY (`movieid`) REFERENCES `movieinfo` (`movieid`)
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `category` (
  `categoryid` int NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `deleted_at` datetime(6) NULL,
  PRIMARY KEY (`categoryid`),
  UNIQUE KEY `uk_category_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `moviecategory` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `movieid` int NOT NULL,
  `categoryid` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_moviecategory_movie_category` (`movieid`, `categoryid`),
  KEY `idx_moviecategory_category_movie` (`categoryid`, `movieid`),
  CONSTRAINT `fk_moviecategory_movie`
    FOREIGN KEY (`movieid`) REFERENCES `movieinfo` (`movieid`) ON DELETE RESTRICT,
  CONSTRAINT `fk_moviecategory_category`
    FOREIGN KEY (`categoryid`) REFERENCES `category` (`categoryid`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Normalize the existing comma-separated typelist into category relations.
CREATE TEMPORARY TABLE `tmp_moviecategory_seed` AS
SELECT DISTINCT
  m.`movieid`,
  CONVERT(TRIM(category_values.`category_name`) USING utf8mb4)
    COLLATE utf8mb4_0900_ai_ci AS `category_name`
FROM `movieinfo` AS m
CROSS JOIN JSON_TABLE(
  CONCAT('[', REPLACE(JSON_QUOTE(m.`typelist`), ',', '","'), ']'),
  '$[*]' COLUMNS (`category_name` varchar(100) PATH '$')
) AS category_values
WHERE m.`typelist` IS NOT NULL
  AND TRIM(m.`typelist`) <> ''
  AND TRIM(category_values.`category_name`) <> '';

INSERT IGNORE INTO `category` (`name`)
SELECT DISTINCT `category_name`
FROM `tmp_moviecategory_seed`;

INSERT IGNORE INTO `moviecategory` (`movieid`, `categoryid`)
SELECT seed.`movieid`, category.`categoryid`
FROM `tmp_moviecategory_seed` AS seed
JOIN `category` AS category ON category.`name` = seed.`category_name`;

DROP TEMPORARY TABLE `tmp_moviecategory_seed`;

CREATE TABLE `moviecomment` (
  `commentid` bigint NOT NULL AUTO_INCREMENT,
  `userid` int NOT NULL,
  `movieid` int NOT NULL,
  `content` varchar(500) NOT NULL,
  `moderation_status` varchar(20) NOT NULL DEFAULT 'published',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `deleted_at` datetime(6) NULL,
  PRIMARY KEY (`commentid`),
  KEY `idx_moviecomment_movie_created` (`movieid`, `created_at`),
  KEY `idx_moviecomment_user_created` (`userid`, `created_at`),
  KEY `idx_moviecomment_moderation_created`
    (`moderation_status`, `created_at`),
  CONSTRAINT `chk_moviecomment_moderation_status`
    CHECK (`moderation_status` IN ('published', 'review_pending', 'hidden')),
  CONSTRAINT `fk_moviecomment_user`
    FOREIGN KEY (`userid`) REFERENCES `user` (`userid`) ON DELETE RESTRICT,
  CONSTRAINT `fk_moviecomment_movie`
    FOREIGN KEY (`movieid`) REFERENCES `movieinfo` (`movieid`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `commentlike` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `userid` int NOT NULL,
  `commentid` bigint NOT NULL,
  `is_active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_commentlike_user_comment` (`userid`, `commentid`),
  KEY `idx_commentlike_comment_active` (`commentid`, `is_active`),
  CONSTRAINT `fk_commentlike_user`
    FOREIGN KEY (`userid`) REFERENCES `user` (`userid`) ON DELETE RESTRICT,
  CONSTRAINT `fk_commentlike_comment`
    FOREIGN KEY (`commentid`) REFERENCES `moviecomment` (`commentid`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `commentlike_event` (
  `eventid` bigint NOT NULL AUTO_INCREMENT,
  `userid` int NOT NULL,
  `commentid` bigint NOT NULL,
  `action` varchar(10) NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`eventid`),
  KEY `idx_commentlike_event_comment_created` (`commentid`, `created_at`),
  KEY `idx_commentlike_event_user_created` (`userid`, `created_at`),
  CONSTRAINT `chk_commentlike_event_action`
    CHECK (`action` IN ('like', 'unlike')),
  CONSTRAINT `fk_commentlike_event_user`
    FOREIGN KEY (`userid`) REFERENCES `user` (`userid`) ON DELETE RESTRICT,
  CONSTRAINT `fk_commentlike_event_comment`
    FOREIGN KEY (`commentid`) REFERENCES `moviecomment` (`commentid`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `adminuser` (
  `adminid` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `password` varchar(255) NOT NULL,
  `role` varchar(30) NOT NULL,
  `status` varchar(20) NOT NULL DEFAULT 'active',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  `deleted_at` datetime(6) NULL,
  PRIMARY KEY (`adminid`),
  UNIQUE KEY `uk_adminuser_username` (`username`),
  KEY `idx_adminuser_role_status` (`role`, `status`),
  CONSTRAINT `chk_adminuser_role`
    CHECK (`role` IN ('admin', 'superadmin'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `commentreport` (
  `reportid` bigint NOT NULL AUTO_INCREMENT,
  `commentid` bigint NOT NULL,
  `reporter_userid` int NOT NULL,
  `reason_code` varchar(40) NOT NULL,
  `reason_detail` varchar(500) NULL,
  `status` varchar(20) NOT NULL DEFAULT 'pending',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `handled_at` datetime(6) NULL,
  `handled_by_adminid` int NULL,
  PRIMARY KEY (`reportid`),
  UNIQUE KEY `uk_commentreport_reporter_comment`
    (`reporter_userid`, `commentid`),
  KEY `idx_commentreport_status_created` (`status`, `created_at`),
  CONSTRAINT `chk_commentreport_reason`
    CHECK (`reason_code` IN (
      'malicious_attack',
      'insulting_language',
      'harmful_information',
      'excessive_promotion',
      'advertisement',
      'other'
    )),
  CONSTRAINT `chk_commentreport_other_detail`
    CHECK (`reason_code` <> 'other' OR
      (`reason_detail` IS NOT NULL AND CHAR_LENGTH(TRIM(`reason_detail`)) > 0)),
  CONSTRAINT `chk_commentreport_status`
    CHECK (`status` IN ('pending', 'accepted', 'rejected')),
  CONSTRAINT `fk_commentreport_comment`
    FOREIGN KEY (`commentid`) REFERENCES `moviecomment` (`commentid`) ON DELETE RESTRICT,
  CONSTRAINT `fk_commentreport_reporter`
    FOREIGN KEY (`reporter_userid`) REFERENCES `user` (`userid`) ON DELETE RESTRICT,
  CONSTRAINT `fk_commentreport_admin`
    FOREIGN KEY (`handled_by_adminid`) REFERENCES `adminuser` (`adminid`)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `userfavorite` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `userid` int NOT NULL,
  `movieid` int NOT NULL,
  `status` varchar(30) NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  `deleted_at` datetime(6) NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_userfavorite_user_movie` (`userid`, `movieid`),
  KEY `idx_userfavorite_user_status_deleted` (`userid`, `status`, `deleted_at`),
  KEY `idx_userfavorite_movie_status_deleted` (`movieid`, `status`, `deleted_at`),
  CONSTRAINT `chk_userfavorite_status`
    CHECK (`status` IN ('want_to_watch', 'watched')),
  CONSTRAINT `fk_userfavorite_user`
    FOREIGN KEY (`userid`) REFERENCES `user` (`userid`) ON DELETE RESTRICT,
  CONSTRAINT `fk_userfavorite_movie`
    FOREIGN KEY (`movieid`) REFERENCES `movieinfo` (`movieid`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `adminoperationlog` (
  `logid` bigint NOT NULL AUTO_INCREMENT,
  `adminid` int NOT NULL,
  `action` varchar(100) NOT NULL,
  `target_type` varchar(50) NOT NULL,
  `target_id` varchar(100) NULL,
  `detail` json NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`logid`),
  KEY `idx_adminoperationlog_admin_created` (`adminid`, `created_at`),
  KEY `idx_adminoperationlog_target` (`target_type`, `target_id`),
  CONSTRAINT `fk_adminoperationlog_admin`
    FOREIGN KEY (`adminid`) REFERENCES `adminuser` (`adminid`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `recommendationitem` (
  `recommendationid` bigint NOT NULL AUTO_INCREMENT,
  `request_id` varchar(64) NOT NULL,
  `userid` int NOT NULL,
  `movieid` int NOT NULL,
  `position` int NOT NULL,
  `movie_rating_snapshot` decimal(4,1) NULL,
  `prediction_score` decimal(10,6) NULL,
  `algorithm_version` varchar(100) NULL,
  `generated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`recommendationid`),
  UNIQUE KEY `uk_recommendationitem_request_movie` (`request_id`, `movieid`),
  KEY `idx_recommendationitem_user_generated` (`userid`, `generated_at`),
  CONSTRAINT `fk_recommendationitem_user`
    FOREIGN KEY (`userid`) REFERENCES `user` (`userid`) ON DELETE RESTRICT,
  CONSTRAINT `fk_recommendationitem_movie`
    FOREIGN KEY (`movieid`) REFERENCES `movieinfo` (`movieid`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE `recommendationevent` (
  `eventid` bigint NOT NULL AUTO_INCREMENT,
  `recommendationid` bigint NOT NULL,
  `event_type` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`eventid`),
  KEY `idx_recommendationevent_type_created` (`event_type`, `created_at`),
  KEY `idx_recommendationevent_item_type` (`recommendationid`, `event_type`),
  CONSTRAINT `chk_recommendationevent_type`
    CHECK (`event_type` IN ('impression', 'click', 'not_interested')),
  CONSTRAINT `fk_recommendationevent_item`
    FOREIGN KEY (`recommendationid`)
    REFERENCES `recommendationitem` (`recommendationid`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- `personalratings.timestamp` is retained temporarily for rollback/audit.
-- Drop it only after the application has switched to `rated_at` and UTC values
-- have been verified in the target database.
