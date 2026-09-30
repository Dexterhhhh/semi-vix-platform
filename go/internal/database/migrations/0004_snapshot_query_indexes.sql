-- Schema migration 0004_snapshot_query_indexes; no application data.
CREATE INDEX ix_stock_snapshot_symbol_timestamp ON stock_snapshot (symbol, timestamp);

CREATE INDEX ix_option_snapshot_symbol_timestamp ON option_snapshot (symbol, timestamp);
