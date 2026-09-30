package database

import (
	"errors"
	"net/url"
	"strings"
)

// PostgresURL converts SQLAlchemy's driver-qualified URL for database/sql.
// The embedded PostgreSQL listener is loopback-only and does not offer TLS.
func PostgresURL(value string) (string, error) {
	value = strings.Replace(value, "postgresql+psycopg://", "postgres://", 1)
	parsed, err := url.Parse(value)
	if err != nil || parsed.Host == "" || parsed.Scheme != "postgres" && parsed.Scheme != "postgresql" {
		return "", errors.New("invalid PostgreSQL URL")
	}
	if parsed.Hostname() == "127.0.0.1" || parsed.Hostname() == "localhost" {
		query := parsed.Query()
		if !query.Has("sslmode") {
			query.Set("sslmode", "disable")
			parsed.RawQuery = query.Encode()
		}
	}
	return parsed.String(), nil
}
