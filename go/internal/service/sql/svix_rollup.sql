
WITH source AS (
    SELECT *, (timestamp AT TIME ZONE 'UTC')::date AS day
    FROM svix_history WHERE timestamp < $1
), grouped AS (
    SELECT day, max(svix) AS high, min(svix) AS low,
           count(*)::integer AS samples, min(calculation_quality) AS quality
    FROM source GROUP BY day
), first_row AS (
    SELECT DISTINCT ON (day) day, timestamp, svix FROM source ORDER BY day, timestamp, id
), last_row AS (
    SELECT DISTINCT ON (day) day, timestamp, svix, core_vol, memory_vol, ai_vol,
           estimated, source_feed FROM source ORDER BY day, timestamp DESC, id DESC
)
INSERT INTO svix_daily
    (date, svix_open, svix_high, svix_low, svix_close, core_close, memory_close,
     ai_close, sample_count, min_calculation_quality, estimated, source_feed,
     open_timestamp, close_timestamp, created_at, updated_at)
SELECT g.day, f.svix, g.high, g.low, l.svix, l.core_vol, l.memory_vol,
       l.ai_vol, g.samples, g.quality, l.estimated, l.source_feed,
       f.timestamp, l.timestamp, now(), now()
FROM grouped g JOIN first_row f USING(day) JOIN last_row l USING(day)
ON CONFLICT (date) DO UPDATE SET
    svix_open = CASE WHEN svix_daily.open_timestamp IS NULL OR EXCLUDED.open_timestamp < svix_daily.open_timestamp THEN EXCLUDED.svix_open ELSE svix_daily.svix_open END,
    svix_high = greatest(svix_daily.svix_high, EXCLUDED.svix_high),
    svix_low = least(svix_daily.svix_low, EXCLUDED.svix_low),
    svix_close = CASE WHEN svix_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > svix_daily.close_timestamp THEN EXCLUDED.svix_close ELSE svix_daily.svix_close END,
    core_close = CASE WHEN svix_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > svix_daily.close_timestamp THEN EXCLUDED.core_close ELSE svix_daily.core_close END,
    memory_close = CASE WHEN svix_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > svix_daily.close_timestamp THEN EXCLUDED.memory_close ELSE svix_daily.memory_close END,
    ai_close = CASE WHEN svix_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > svix_daily.close_timestamp THEN EXCLUDED.ai_close ELSE svix_daily.ai_close END,
    sample_count = svix_daily.sample_count + EXCLUDED.sample_count,
    min_calculation_quality = least(svix_daily.min_calculation_quality, EXCLUDED.min_calculation_quality),
    estimated = CASE WHEN svix_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > svix_daily.close_timestamp THEN EXCLUDED.estimated ELSE svix_daily.estimated END,
    source_feed = CASE WHEN svix_daily.close_timestamp IS NULL OR EXCLUDED.close_timestamp > svix_daily.close_timestamp THEN EXCLUDED.source_feed ELSE svix_daily.source_feed END,
    open_timestamp = least(svix_daily.open_timestamp, EXCLUDED.open_timestamp),
    close_timestamp = greatest(svix_daily.close_timestamp, EXCLUDED.close_timestamp),
    updated_at = now()
RETURNING date
