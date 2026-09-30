
WITH source AS (
    SELECT *, (timestamp AT TIME ZONE 'UTC')::date AS day
    FROM custom_index_history WHERE timestamp < $1
), grouped AS (
    SELECT custom_index_id, version_id, day, max(value) AS high, min(value) AS low,
           count(*)::integer AS samples, min(calculation_quality) AS quality
    FROM source GROUP BY custom_index_id, version_id, day
), first_row AS (
    SELECT DISTINCT ON (custom_index_id, version_id, day)
           custom_index_id, version_id, day, timestamp, value
    FROM source ORDER BY custom_index_id, version_id, day, timestamp, id
), last_row AS (
    SELECT DISTINCT ON (custom_index_id, version_id, day)
           custom_index_id, version_id, day, timestamp, value, estimated, source_feed
    FROM source ORDER BY custom_index_id, version_id, day, timestamp DESC, id DESC
)
INSERT INTO custom_index_daily
    (custom_index_id, version_id, date, value_open, value_high, value_low, value_close,
     sample_count, min_calculation_quality, estimated, source_feed, open_timestamp,
     close_timestamp, created_at, updated_at)
SELECT g.custom_index_id, g.version_id, g.day, f.value, g.high, g.low, l.value,
       g.samples, g.quality, l.estimated, l.source_feed, f.timestamp,
       l.timestamp, now(), now()
FROM grouped g
JOIN first_row f USING(custom_index_id, version_id, day)
JOIN last_row l USING(custom_index_id, version_id, day)
ON CONFLICT (custom_index_id, version_id, date) DO UPDATE SET
    value_open = CASE WHEN custom_index_daily.open_timestamp IS NULL OR EXCLUDED.open_timestamp < custom_index_daily.open_timestamp THEN EXCLUDED.value_open ELSE custom_index_daily.value_open END,
    value_high = greatest(custom_index_daily.value_high, EXCLUDED.value_high),
    value_low = least(custom_index_daily.value_low, EXCLUDED.value_low),
    value_close = CASE WHEN custom_index_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > custom_index_daily.close_timestamp THEN EXCLUDED.value_close ELSE custom_index_daily.value_close END,
    sample_count = custom_index_daily.sample_count + EXCLUDED.sample_count,
    min_calculation_quality = least(custom_index_daily.min_calculation_quality, EXCLUDED.min_calculation_quality),
    estimated = CASE WHEN custom_index_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > custom_index_daily.close_timestamp THEN EXCLUDED.estimated ELSE custom_index_daily.estimated END,
    source_feed = CASE WHEN custom_index_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > custom_index_daily.close_timestamp THEN EXCLUDED.source_feed ELSE custom_index_daily.source_feed END,
    open_timestamp = least(custom_index_daily.open_timestamp, EXCLUDED.open_timestamp),
    close_timestamp = greatest(custom_index_daily.close_timestamp, EXCLUDED.close_timestamp),
    updated_at = now()
RETURNING date
