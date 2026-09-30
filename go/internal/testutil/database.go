// Package testutil only connects to an explicitly named disposable test database.
package testutil

import (
	"database/sql"
	"net/url"
	"os"
	"strings"
	"testing"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/database"
	_ "github.com/lib/pq"
)

func Database(t *testing.T) *sql.DB {
	t.Helper()
	raw := os.Getenv("SVIX_TEST_DATABASE_URL")
	if raw == "" {
		t.Skip("SVIX_TEST_DATABASE_URL is not set")
	}
	u, err := url.Parse(raw)
	if err != nil || !strings.HasSuffix(strings.Trim(u.Path, "/"), "_test") {
		t.Fatal("integration tests require a disposable database ending in _test")
	}
	dsn, err := database.PostgresURL(raw)
	if err != nil {
		t.Fatal(err)
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		t.Fatal(err)
	}
	if err = db.Ping(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
	return db
}
