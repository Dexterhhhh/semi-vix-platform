package service

import (
	"context"
	"database/sql"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

//go:embed sql/*.sql
var maintenanceSQL embed.FS

func (s *Service) setting(ctx context.Context, key string, target any) error {
	var encoded string
	err := s.DB.QueryRowContext(ctx, "SELECT value FROM system_settings WHERE key=$1", key).Scan(&encoded)
	if err == sql.ErrNoRows {
		return nil
	}
	if err != nil {
		return err
	}
	return json.Unmarshal([]byte(encoded), target)
}
func (s *Service) lock(ctx context.Context, name string) (*sql.Conn, bool, error) {
	conn, err := s.DB.Conn(ctx)
	if err != nil {
		return nil, false, err
	}
	var locked bool
	err = conn.QueryRowContext(ctx, "SELECT pg_try_advisory_lock(hashtext($1))", name).Scan(&locked)
	if err != nil || !locked {
		conn.Close()
		return nil, false, err
	}
	return conn, true, nil
}
func unlock(conn *sql.Conn, name string) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_, _ = conn.ExecContext(ctx, "SELECT pg_advisory_unlock(hashtext($1))", name)
	_ = conn.Close()
}
func (s *Service) Maintenance(ctx context.Context, now time.Time, force bool) (map[string]any, error) {
	conn, locked, err := s.lock(ctx, "svix_maintenance")
	if err != nil {
		return nil, err
	}
	if !locked {
		return map[string]any{"status": "SKIPPED", "reason": "maintenance_running"}, nil
	}
	defer unlock(conn, "svix_maintenance")
	now = now.UTC()
	requested := false
	if err = s.setting(ctx, "maintenance_requested", &requested); err != nil {
		return nil, err
	}
	force = force || requested
	scheduled := "03:30"
	if err = s.setting(ctx, "maintenance_time_utc", &scheduled); err != nil {
		return nil, err
	}
	clock, err := time.Parse("15:04", scheduled)
	if err != nil {
		return nil, err
	}
	due := time.Date(now.Year(), now.Month(), now.Day(), clock.Hour(), clock.Minute(), 0, 0, time.UTC)
	var last sql.NullTime
	if err = s.DB.QueryRowContext(ctx, "SELECT max(finished_at) FROM data_maintenance_runs WHERE status='COMPLETED'").Scan(&last); err != nil {
		return nil, err
	}
	if !force && (now.Before(due) || last.Valid && last.Time.UTC().Format("2006-01-02") == now.Format("2006-01-02")) {
		return map[string]any{"status": "SKIPPED", "reason": "not_due"}, nil
	}
	downsample, cleanup := true, false
	historyDays, optionDays := 7, 14
	archive := ""
	for _, pair := range []struct {
		key    string
		target any
	}{{"svix_downsample_enabled", &downsample}, {"option_cleanup_enabled", &cleanup}, {"detailed_retention_days", &historyDays}, {"option_retention_days", &optionDays}, {"option_archive_through", &archive}} {
		if err = s.setting(ctx, pair.key, pair.target); err != nil {
			return nil, err
		}
	}
	if historyDays < 1 || historyDays > 365 {
		return nil, errors.New("invalid detailed retention")
	}
	if optionDays < 14 {
		optionDays = 14
	}
	var id int
	if err = s.DB.QueryRowContext(ctx, `INSERT INTO data_maintenance_runs(status,option_rows_deleted,history_rows_aggregated,daily_rows_written,started_at) VALUES('RUNNING',0,0,0,$1) RETURNING id`, now).Scan(&id); err != nil {
		return nil, err
	}
	result, err := s.maintainSQL(ctx, now.AddDate(0, 0, -historyDays), now.AddDate(0, 0, -optionDays), archive, downsample, cleanup, id)
	if err != nil {
		_, _ = s.DB.ExecContext(context.Background(), "UPDATE data_maintenance_runs SET status='FAILED',finished_at=now(),error_message='Data maintenance failed' WHERE id=$1", id)
		return nil, err
	}
	if requested {
		_, err = s.DB.ExecContext(ctx, "UPDATE system_settings SET value='false',updated_at=now() WHERE key='maintenance_requested'")
	}
	return result, err
}
func (s *Service) maintainSQL(ctx context.Context, historyCutoff, optionCutoff time.Time, archive string, downsample, cleanup bool, id int) (map[string]any, error) {
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	var aggregated, daily, deleted int64
	if downsample {
		for _, table := range []string{"svix", "custom"} {
			query, _ := maintenanceSQL.ReadFile("sql/" + table + "_rollup.sql")
			rows, err := tx.QueryContext(ctx, string(query), historyCutoff)
			if err != nil {
				return nil, err
			}
			for rows.Next() {
				var day time.Time
				if err := rows.Scan(&day); err != nil {
					rows.Close()
					return nil, err
				}
				daily++
			}
			err = rows.Err()
			rows.Close()
			if err != nil {
				return nil, err
			}
			historyTable := "svix_history"
			if table == "custom" {
				historyTable = "custom_index_history"
			}
			r, err := tx.ExecContext(ctx, "DELETE FROM "+historyTable+" WHERE timestamp < $1", historyCutoff)
			if err != nil {
				return nil, err
			}
			n, _ := r.RowsAffected()
			aggregated += n
		}
	}
	if cleanup && archive != "" {
		if _, err = time.Parse("2006-01-02", archive); err != nil {
			return nil, fmt.Errorf("invalid archive watermark")
		}
		query, _ := maintenanceSQL.ReadFile("sql/option_delete.sql")
		for {
			r, err := tx.ExecContext(ctx, string(query), optionCutoff.Format("2006-01-02"), archive, 10000)
			if err != nil {
				return nil, err
			}
			n, _ := r.RowsAffected()
			deleted += n
			if n < 10000 {
				break
			}
		}
	}
	_, err = tx.ExecContext(ctx, `UPDATE data_maintenance_runs SET status='COMPLETED',finished_at=now(),option_rows_deleted=$1,history_rows_aggregated=$2,daily_rows_written=$3 WHERE id=$4`, deleted, aggregated, daily, id)
	if err != nil {
		return nil, err
	}
	if err = tx.Commit(); err != nil {
		return nil, err
	}
	return map[string]any{"status": "COMPLETED", "option_rows_deleted": deleted, "history_rows_aggregated": aggregated, "daily_rows_written": daily}, nil
}
