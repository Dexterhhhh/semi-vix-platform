-- Schema migration 0008_data_lifecycle; no application data.
CREATE TABLE svix_daily (
    id SERIAL NOT NULL,
    date DATE NOT NULL,
    svix_open FLOAT NOT NULL,
    svix_high FLOAT NOT NULL,
    svix_low FLOAT NOT NULL,
    svix_close FLOAT NOT NULL,
    core_close FLOAT NOT NULL,
    memory_close FLOAT NOT NULL,
    ai_close FLOAT NOT NULL,
    sample_count INTEGER NOT NULL,
    min_calculation_quality FLOAT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (date)
);

CREATE UNIQUE INDEX ix_svix_daily_date ON svix_daily (date);

CREATE TABLE data_maintenance_runs (
    id SERIAL NOT NULL,
    status VARCHAR(16) NOT NULL,
    option_rows_deleted INTEGER DEFAULT '0' NOT NULL,
    history_rows_aggregated INTEGER DEFAULT '0' NOT NULL,
    daily_rows_written INTEGER DEFAULT '0' NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    PRIMARY KEY (id)
);

CREATE INDEX ix_data_maintenance_runs_status ON data_maintenance_runs (status);
