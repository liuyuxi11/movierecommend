-- Optional follow-up for deployments that retain the legacy four tables.
-- Run after 0001_schema_upgrade.sql and after backing up the database.
USE `movierecommend`;

-- The composite application indexes required by the backend are already
-- created by 0001. These statements are for installations that only loaded
-- the original four-table dump.
SET @sql := IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='personalratings'
   AND INDEX_NAME='idx_personalratings_user_rated') = 0,
  'ALTER TABLE `personalratings` ADD KEY `idx_personalratings_user_rated` (`userid`, `rated_at`)',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='personalratings'
   AND INDEX_NAME='idx_personalratings_movie_rating') = 0,
  'ALTER TABLE `personalratings` ADD KEY `idx_personalratings_movie_rating` (`movieid`, `rating`)',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='recommendresult') = 1
  AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='recommendresult'
   AND COLUMN_NAME='created_at') = 0,
  'ALTER TABLE `recommendresult` ADD COLUMN `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF(
  (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='recommendresult') = 1
  AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
   WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='recommendresult'
   AND INDEX_NAME='idx_recommendresult_user_created') = 0,
  'ALTER TABLE `recommendresult` ADD KEY `idx_recommendresult_user_created` (`userid`, `created_at`)',
  'SELECT 1'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;
