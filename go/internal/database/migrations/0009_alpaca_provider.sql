-- Schema migration 0009_alpaca_provider; no application data.
ALTER TABLE provider_credentials ADD COLUMN data_feed VARCHAR(32);
