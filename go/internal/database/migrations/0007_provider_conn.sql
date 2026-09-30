-- Schema migration 0007_provider_conn; no application data.
ALTER TABLE provider_credentials ADD COLUMN host VARCHAR(255);

ALTER TABLE provider_credentials ADD COLUMN port INTEGER;

ALTER TABLE provider_credentials ADD COLUMN client_id INTEGER;
