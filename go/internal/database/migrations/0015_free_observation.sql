-- Schema migration 0015_free_observation; no application data.
ALTER TABLE option_snapshot ADD COLUMN trade_timestamp TIMESTAMP WITH TIME ZONE;

ALTER TABLE stock_snapshot ADD COLUMN trade_timestamp TIMESTAMP WITH TIME ZONE;

ALTER TABLE market_collection_runs ADD COLUMN batch_id VARCHAR(64);

ALTER TABLE market_collection_runs ADD COLUMN calculation_status VARCHAR(24);

ALTER TABLE market_collection_runs ADD COLUMN symbol_status TEXT;

ALTER TABLE market_collection_runs ADD COLUMN collection_errors TEXT;

ALTER TABLE market_collection_runs ADD COLUMN retry_after_seconds INTEGER;

ALTER TABLE market_collection_runs ADD CONSTRAINT uq_market_collection_batch UNIQUE (batch_id);

CREATE TABLE svix_observations (
    id SERIAL NOT NULL,
    session_date DATE NOT NULL,
    valuation_at TIMESTAMP WITH TIME ZONE NOT NULL,
    batch_id VARCHAR(64) NOT NULL,
    method_version VARCHAR(64) NOT NULL,
    svix FLOAT,
    core FLOAT,
    memory FLOAT,
    ai FLOAT,
    status VARCHAR(32) NOT NULL,
    coverage FLOAT NOT NULL,
    cached_coverage FLOAT NOT NULL,
    source_feed VARCHAR(64),
    details TEXT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_svix_observation_batch_method UNIQUE (batch_id, method_version),
    FOREIGN KEY(batch_id) REFERENCES market_collection_runs (batch_id)
);

CREATE INDEX ix_svix_observation_session_time ON svix_observations (session_date, valuation_at);

CREATE TABLE svix_asset_observations (
    id SERIAL NOT NULL,
    session_date DATE NOT NULL,
    valuation_at TIMESTAMP WITH TIME ZONE NOT NULL,
    batch_id VARCHAR(64) NOT NULL,
    method_version VARCHAR(64) NOT NULL,
    symbol VARCHAR(16) NOT NULL,
    volatility FLOAT,
    oldest_input_at TIMESTAMP WITH TIME ZONE,
    newest_input_at TIMESTAMP WITH TIME ZONE,
    term_method VARCHAR(24),
    status VARCHAR(24) NOT NULL,
    details TEXT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_svix_asset_batch_method_symbol UNIQUE (batch_id, method_version, symbol),
    FOREIGN KEY(batch_id) REFERENCES market_collection_runs (batch_id)
);

CREATE INDEX ix_svix_asset_observations_session_date ON svix_asset_observations (session_date);

CREATE INDEX ix_svix_asset_observations_batch_id ON svix_asset_observations (batch_id);

CREATE TABLE svix_correlation_cache (
    id SERIAL NOT NULL,
    provider VARCHAR(16) NOT NULL,
    as_of DATE NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE NOT NULL,
    assets VARCHAR(256) NOT NULL,
    matrix TEXT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_svix_corr_day_assets_time UNIQUE (provider, as_of, assets, available_at)
);

CREATE INDEX ix_svix_correlation_cache_as_of ON svix_correlation_cache (as_of);
