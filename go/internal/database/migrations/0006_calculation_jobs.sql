-- Schema migration 0006_calculation_jobs; no application data.
CREATE TABLE calculation_jobs (
    id SERIAL NOT NULL,
    type VARCHAR(32) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    frequency VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    progress INTEGER NOT NULL,
    result_summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    PRIMARY KEY (id)
);

CREATE INDEX ix_calculation_jobs_status ON calculation_jobs (status);

CREATE INDEX ix_calculation_jobs_status_created_at ON calculation_jobs (status, created_at);
