-- Schema migration 0005_svix_history; no application data.
CREATE TABLE svix_history (
    id SERIAL NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    svix FLOAT NOT NULL,
    core_vol FLOAT NOT NULL,
    memory_vol FLOAT NOT NULL,
    ai_vol FLOAT NOT NULL,
    calculation_quality FLOAT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (timestamp)
);

CREATE INDEX ix_svix_history_timestamp ON svix_history (timestamp);
