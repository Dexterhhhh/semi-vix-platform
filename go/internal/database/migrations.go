package database

import (
	"context"
	"database/sql"
	"embed"
	"fmt"
	"io/fs"
	"strings"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

// Migrate preserves Alembic revision IDs so either edition can upgrade an existing volume.
// All pending DDL and the revision update commit together under a database lock.
func Migrate(ctx context.Context, db *sql.DB) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, `SELECT pg_advisory_xact_lock(hashtext('svix_schema_migrations'));
	CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY(version_num))`); err != nil {
		return err
	}
	rows, err := tx.QueryContext(ctx, "SELECT version_num FROM alembic_version")
	if err != nil {
		return err
	}
	current := ""
	count := 0
	for rows.Next() {
		if err = rows.Scan(&current); err != nil {
			rows.Close()
			return err
		}
		count++
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return err
	}
	if count > 1 {
		return fmt.Errorf("multiple schema revisions are unsupported")
	}
	files, err := fs.Glob(migrationFiles, "migrations/*.sql")
	if err != nil {
		return err
	}
	start := 0
	if current != "" {
		start = -1
		for i, file := range files {
			if strings.TrimSuffix(strings.TrimPrefix(file, "migrations/"), ".sql") == current {
				start = i + 1
				break
			}
		}
		if start < 0 {
			return fmt.Errorf("unsupported schema revision %q; refusing to change database", current)
		}
	}
	for _, file := range files[start:] {
		ddl, err := migrationFiles.ReadFile(file)
		if err != nil {
			return err
		}
		revision := strings.TrimSuffix(strings.TrimPrefix(file, "migrations/"), ".sql")
		if _, err = tx.ExecContext(ctx, string(ddl)); err != nil {
			return fmt.Errorf("schema migration %s: %w", revision, err)
		}
		if _, err = tx.ExecContext(ctx, "DELETE FROM alembic_version"); err != nil {
			return err
		}
		if _, err = tx.ExecContext(ctx, "INSERT INTO alembic_version(version_num) VALUES($1)", revision); err != nil {
			return err
		}
	}
	return tx.Commit()
}
