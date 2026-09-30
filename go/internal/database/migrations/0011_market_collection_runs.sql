-- Schema migration 0011_market_collection_runs; no application data.
CREATE TABLE market_collection_runs (
    id SERIAL NOT NULL,
    session_date DATE NOT NULL,
    status VARCHAR(16) NOT NULL,
    interval_minutes INTEGER NOT NULL,
    stock_quotes_saved INTEGER DEFAULT '0' NOT NULL,
    option_quotes_saved INTEGER DEFAULT '0' NOT NULL,
    symbols_succeeded INTEGER DEFAULT '0' NOT NULL,
    symbols_failed INTEGER DEFAULT '0' NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    PRIMARY KEY (id)
);

CREATE INDEX ix_market_collection_runs_session_date ON market_collection_runs (session_date);

CREATE INDEX ix_market_collection_runs_status ON market_collection_runs (status);

CREATE INDEX ix_market_collection_session_started ON market_collection_runs (session_date, started_at);
