-- Schema migration 0012_intraday_interval_seconds; no application data.
ALTER TABLE market_collection_runs ADD COLUMN interval_seconds INTEGER DEFAULT '300' NOT NULL;
