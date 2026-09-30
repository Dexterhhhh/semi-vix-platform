-- Schema migration 0003_harden_market_data; no application data.
CREATE TABLE audit_events (
    id SERIAL NOT NULL,
    admin_id INTEGER,
    action VARCHAR(128) NOT NULL,
    provider VARCHAR(16),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(admin_id) REFERENCES admin_account (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_events_admin_id ON audit_events (admin_id);

CREATE INDEX ix_audit_events_action ON audit_events (action);

CREATE INDEX ix_audit_events_provider ON audit_events (provider);

CREATE INDEX ix_audit_events_created_at ON audit_events (created_at);

ALTER TABLE stock_snapshot ADD COLUMN provider VARCHAR(16) DEFAULT 'IBKR' NOT NULL;

ALTER TABLE stock_snapshot ADD COLUMN delayed BOOLEAN;

ALTER TABLE stock_snapshot ALTER COLUMN provider DROP DEFAULT;

CREATE INDEX ix_stock_snapshot_provider ON stock_snapshot (provider);

CREATE INDEX ix_stock_snapshot_provider_symbol_timestamp ON stock_snapshot (provider, symbol, timestamp);

ALTER TABLE option_snapshot ADD COLUMN contract_id VARCHAR(256);

UPDATE option_snapshot SET contract_id = provider || ':LEGACY:' || id::text WHERE contract_id IS NULL;

ALTER TABLE option_snapshot ALTER COLUMN contract_id SET NOT NULL;

ALTER TABLE option_snapshot ADD COLUMN delayed BOOLEAN;

CREATE INDEX ix_option_snapshot_contract_id ON option_snapshot (contract_id);

CREATE INDEX ix_option_snapshot_provider_contract_timestamp ON option_snapshot (provider, contract_id, timestamp);

CREATE INDEX ix_option_snapshot_symbol_expiry_timestamp ON option_snapshot (symbol, expiry, timestamp);

ALTER TABLE option_snapshot ADD CONSTRAINT option_snapshot_positive_strike CHECK (strike > 0);
