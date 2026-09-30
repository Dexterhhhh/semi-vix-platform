
WITH covered AS (
    SELECT DISTINCT (timestamp AT TIME ZONE 'UTC')::date AS day,
           lower(split_part(source_feed, ':', 1)) AS provider
      FROM svix_history WHERE source_feed LIKE '%:%'
    UNION
    SELECT date, lower(split_part(source_feed, ':', 1))
      FROM svix_daily WHERE source_feed LIKE '%:%'
    UNION
    SELECT DISTINCT (timestamp AT TIME ZONE 'UTC')::date,
           lower(split_part(source_feed, ':', 1))
      FROM custom_index_history WHERE source_feed LIKE '%:%'
    UNION
    SELECT date, lower(split_part(source_feed, ':', 1))
      FROM custom_index_daily WHERE source_feed LIKE '%:%'
), candidates AS (
    SELECT o.id FROM option_snapshot o
    JOIN covered c ON c.day = (o.timestamp AT TIME ZONE 'UTC')::date
                  AND c.provider = lower(o.provider)
    WHERE (o.timestamp AT TIME ZONE 'UTC')::date < $1
      AND c.day <= $2
    LIMIT $3
)
DELETE FROM option_snapshot WHERE id IN (SELECT id FROM candidates)
