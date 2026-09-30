package database_test

import (
	"context"
	"database/sql"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/database"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/testutil"
	"github.com/lib/pq"
)

func fingerprint(t *testing.T, db *sql.DB, schema string) []string {
	t.Helper()
	query := `SELECT table_name||':'||column_name||':'||data_type||':'||is_nullable||':'||COALESCE(column_default,'') FROM information_schema.columns WHERE table_schema=$1
	UNION ALL SELECT tablename||':'||indexname||':'||indexdef FROM pg_indexes WHERE schemaname=$1
	UNION ALL SELECT rel.relname||':'||c.conname||':'||pg_get_constraintdef(c.oid) FROM pg_constraint c JOIN pg_class rel ON rel.oid=c.conrelid JOIN pg_namespace n ON n.oid=rel.relnamespace WHERE n.nspname=$1
	ORDER BY 1`
	rows, err := db.Query(query, schema)
	if err != nil {
		t.Fatal(err)
	}
	defer rows.Close()
	var result []string
	for rows.Next() {
		var value string
		if err = rows.Scan(&value); err != nil {
			t.Fatal(err)
		}
		result = append(result, strings.ReplaceAll(strings.ReplaceAll(value, schema+".", ""), "public.", ""))
	}
	if err = rows.Err(); err != nil {
		t.Fatal(err)
	}
	return result
}

// Compare all legacy revision upgrades with the existing Alembic-created public schema.
func TestMigrationsFromEveryRevision(t *testing.T) {
	root := testutil.Database(t)
	expected := fingerprint(t, root, "public")
	files, err := filepath.Glob("migrations/*.sql")
	if err != nil || len(files) != 15 {
		t.Fatal("expected 15 schema migrations", err)
	}
	for count := 0; count <= len(files); count++ {
		t.Run(fmt.Sprintf("revision_%02d", count), func(t *testing.T) {
			schema := fmt.Sprintf("go_migration_fixture_%d", count)
			if _, err = root.Exec("CREATE SCHEMA " + pq.QuoteIdentifier(schema)); err != nil {
				t.Fatal(err)
			}
			defer root.Exec("DROP SCHEMA " + pq.QuoteIdentifier(schema) + " CASCADE")
			u, err := url.Parse(os.Getenv("SVIX_TEST_DATABASE_URL"))
			if err != nil {
				t.Fatal(err)
			}
			q := u.Query()
			q.Set("search_path", schema)
			u.RawQuery = q.Encode()
			dsn, err := database.PostgresURL(u.String())
			if err != nil {
				t.Fatal(err)
			}
			db, err := sql.Open("postgres", dsn)
			if err != nil {
				t.Fatal(err)
			}
			defer db.Close()
			if count > 0 {
				if _, err = db.Exec("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY(version_num))"); err != nil {
					t.Fatal(err)
				}
				for _, file := range files[:count] {
					ddl, err := os.ReadFile(file)
					if err != nil {
						t.Fatal(err)
					}
					if _, err = db.Exec(string(ddl)); err != nil {
						t.Fatal(err)
					}
				}
				revision := strings.TrimSuffix(filepath.Base(files[count-1]), ".sql")
				if _, err = db.Exec("INSERT INTO alembic_version VALUES($1)", revision); err != nil {
					t.Fatal(err)
				}
				if _, err = db.Exec("INSERT INTO admin_account(id,username,password_hash,is_active,created_at) VALUES(1,'migration-fixture','fixture-only',true,now())"); err != nil {
					t.Fatal(err)
				}
			}
			if err = database.Migrate(context.Background(), db); err != nil {
				t.Fatal(err)
			}
			if err = database.Migrate(context.Background(), db); err != nil {
				t.Fatal("idempotence", err)
			}
			var revision string
			if err = db.QueryRow("SELECT version_num FROM alembic_version").Scan(&revision); err != nil || revision != "0015_free_observation" {
				t.Fatal(revision, err)
			}
			if count > 0 {
				var name string
				if err = db.QueryRow("SELECT username FROM admin_account WHERE id=1").Scan(&name); err != nil || name != "migration-fixture" {
					t.Fatal("existing account changed", err)
				}
			}
			actual := fingerprint(t, db, schema)
			if !reflect.DeepEqual(expected, actual) {
				for i := 0; i < len(expected) && i < len(actual); i++ {
					if expected[i] != actual[i] {
						t.Fatalf("schema differs at %d: expected %s; actual %s", i, expected[i], actual[i])
					}
				}
				t.Fatalf("schema item count differs: expected %d; actual %d", len(expected), len(actual))
			}
			if _, err = db.Exec("UPDATE alembic_version SET version_num='future_unknown_revision'"); err != nil {
				t.Fatal(err)
			}
			if err = database.Migrate(context.Background(), db); err == nil {
				t.Fatal("unknown revision accepted")
			}
		})
	}
}
