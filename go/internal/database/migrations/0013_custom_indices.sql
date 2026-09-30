-- Schema migration 0013_custom_indices; no application data.
CREATE TABLE custom_indices (
    id SERIAL NOT NULL,
    name VARCHAR(64) NOT NULL,
    enabled BOOLEAN DEFAULT true NOT NULL,
    missing_policy VARCHAR(16) DEFAULT 'STRICT' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id)
);

CREATE TABLE custom_index_versions (
    id SERIAL NOT NULL,
    custom_index_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    name VARCHAR(64) NOT NULL,
    missing_policy VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_custom_index_version UNIQUE (custom_index_id, version_number),
    FOREIGN KEY(custom_index_id) REFERENCES custom_indices (id) ON DELETE CASCADE
);

CREATE INDEX ix_custom_index_versions_custom_index_id ON custom_index_versions (custom_index_id);

CREATE TABLE custom_index_components (
    id SERIAL NOT NULL,
    version_id INTEGER NOT NULL,
    symbol VARCHAR(16) NOT NULL,
    weight FLOAT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT custom_index_component_weight_range CHECK (weight > 0 AND weight <= 1),
    CONSTRAINT uq_custom_index_component_symbol UNIQUE (version_id, symbol),
    FOREIGN KEY(version_id) REFERENCES custom_index_versions (id) ON DELETE CASCADE
);

CREATE INDEX ix_custom_index_components_version_id ON custom_index_components (version_id);

CREATE INDEX ix_custom_index_components_symbol ON custom_index_components (symbol);

CREATE TABLE custom_index_history (
    id SERIAL NOT NULL,
    custom_index_id INTEGER NOT NULL,
    version_id INTEGER NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    value FLOAT NOT NULL,
    calculation_quality FLOAT NOT NULL,
    estimated BOOLEAN DEFAULT true NOT NULL,
    source_feed VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_custom_index_history_point UNIQUE (custom_index_id, version_id, timestamp),
    FOREIGN KEY(custom_index_id) REFERENCES custom_indices (id) ON DELETE CASCADE,
    FOREIGN KEY(version_id) REFERENCES custom_index_versions (id) ON DELETE CASCADE
);

CREATE INDEX ix_custom_index_history_timestamp ON custom_index_history (timestamp);

CREATE INDEX ix_custom_index_history_index_timestamp ON custom_index_history (custom_index_id, timestamp);

CREATE TABLE custom_index_daily (
    id SERIAL NOT NULL,
    custom_index_id INTEGER NOT NULL,
    version_id INTEGER NOT NULL,
    date DATE NOT NULL,
    value_open FLOAT NOT NULL,
    value_high FLOAT NOT NULL,
    value_low FLOAT NOT NULL,
    value_close FLOAT NOT NULL,
    sample_count INTEGER NOT NULL,
    min_calculation_quality FLOAT NOT NULL,
    estimated BOOLEAN DEFAULT true NOT NULL,
    source_feed VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_custom_index_daily_point UNIQUE (custom_index_id, version_id, date),
    FOREIGN KEY(custom_index_id) REFERENCES custom_indices (id) ON DELETE CASCADE,
    FOREIGN KEY(version_id) REFERENCES custom_index_versions (id) ON DELETE CASCADE
);

CREATE INDEX ix_custom_index_daily_index_date ON custom_index_daily (custom_index_id, date);
