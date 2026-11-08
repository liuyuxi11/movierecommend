-- Preflight query must return zero. The single ALTER is atomic and revalidates
-- all rows when adding the new CHECK constraint.
SELECT COUNT(*) AS invalid_rating_count
FROM `personalratings`
WHERE `rating` < 1 OR `rating` > 5;

ALTER TABLE `personalratings`
  DROP CHECK `chk_personalratings_rating`,
  ADD CONSTRAINT `chk_personalratings_rating`
  CHECK (`rating` BETWEEN 1 AND 5);
