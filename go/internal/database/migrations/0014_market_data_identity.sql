-- Schema migration 0014_market_data_identity; no application data.
ALTER TABLE option_snapshot ADD COLUMN feed VARCHAR(32);

ALTER TABLE option_snapshot ADD COLUMN price_type VARCHAR(32) DEFAULT 'unknown' NOT NULL;

ALTER TABLE option_snapshot ADD COLUMN received_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE option_snapshot ADD COLUMN batch_id VARCHAR(64);

CREATE INDEX ix_option_snapshot_batch_id ON option_snapshot (batch_id);

UPDATE option_snapshot SET received_at = timestamp WHERE received_at IS NULL;

ALTER TABLE option_snapshot ALTER COLUMN received_at SET NOT NULL;

ALTER TABLE stock_snapshot ADD COLUMN feed VARCHAR(32);

ALTER TABLE stock_snapshot ADD COLUMN price_type VARCHAR(32) DEFAULT 'unknown' NOT NULL;

ALTER TABLE stock_snapshot ADD COLUMN received_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE stock_snapshot ADD COLUMN batch_id VARCHAR(64);

CREATE INDEX ix_stock_snapshot_batch_id ON stock_snapshot (batch_id);

UPDATE stock_snapshot SET received_at = timestamp WHERE received_at IS NULL;

ALTER TABLE stock_snapshot ALTER COLUMN received_at SET NOT NULL;

ALTER TABLE svix_history ADD COLUMN calculation_method VARCHAR(32) DEFAULT 'legacy' NOT NULL;

ALTER TABLE svix_history ADD COLUMN market_data_quality VARCHAR(32) DEFAULT 'unknown' NOT NULL;

ALTER TABLE svix_daily ADD COLUMN open_timestamp TIMESTAMP WITH TIME ZONE;

ALTER TABLE svix_daily ADD COLUMN close_timestamp TIMESTAMP WITH TIME ZONE;

ALTER TABLE custom_index_daily ADD COLUMN open_timestamp TIMESTAMP WITH TIME ZONE;

ALTER TABLE custom_index_daily ADD COLUMN close_timestamp TIMESTAMP WITH TIME ZONE;
