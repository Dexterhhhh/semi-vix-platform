-- Schema migration 0010_svix_calculation_provenance; no application data.
ALTER TABLE svix_history ADD COLUMN estimated BOOLEAN DEFAULT true NOT NULL;

ALTER TABLE svix_history ADD COLUMN source_feed VARCHAR(64);

ALTER TABLE svix_daily ADD COLUMN estimated BOOLEAN DEFAULT true NOT NULL;

ALTER TABLE svix_daily ADD COLUMN source_feed VARCHAR(64);
