-- Schema migration 0001_initial; no application data.
CREATE TABLE admin_account (
    id SERIAL NOT NULL,
    username VARCHAR(128) NOT NULL,
    password_hash VARCHAR(512) NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT single_admin_account CHECK (id = 1),
    UNIQUE (username)
);

CREATE TABLE admin_security (
    id SERIAL NOT NULL,
    admin_id INTEGER NOT NULL,
    totp_secret_encrypted TEXT,
    mfa_enabled BOOLEAN NOT NULL,
    backup_codes_encrypted TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (admin_id),
    FOREIGN KEY(admin_id) REFERENCES admin_account (id) ON DELETE CASCADE
);

CREATE TABLE system_settings (
    id SERIAL NOT NULL,
    key VARCHAR(128) NOT NULL,
    value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (key)
);

CREATE TABLE sessions (
    id SERIAL NOT NULL,
    refresh_token_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ip_address VARCHAR(64),
    PRIMARY KEY (id),
    UNIQUE (refresh_token_hash)
);
