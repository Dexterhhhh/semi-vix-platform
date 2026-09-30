-- Schema migration 0002_market_data; no application data.
CREATE TABLE provider_credentials (
    id SERIAL NOT NULL,
    provider VARCHAR(16) NOT NULL,
    api_key_encrypted TEXT,
    secret_encrypted TEXT,
    account_identifier_encrypted TEXT,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (provider)
);

CREATE TABLE option_snapshot (
    id SERIAL NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    provider VARCHAR(16) NOT NULL,
    symbol VARCHAR(16) NOT NULL,
    expiry TIMESTAMP WITH TIME ZONE NOT NULL,
    strike FLOAT NOT NULL,
    option_type VARCHAR(4) NOT NULL,
    bid FLOAT,
    ask FLOAT,
    last FLOAT,
    volume INTEGER,
    open_interest INTEGER,
    implied_volatility FLOAT,
    PRIMARY KEY (id)
);

CREATE TABLE stock_snapshot (
    id SERIAL NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    symbol VARCHAR(16) NOT NULL,
    price FLOAT,
    bid FLOAT,
    ask FLOAT,
    volume INTEGER,
    PRIMARY KEY (id)
);
