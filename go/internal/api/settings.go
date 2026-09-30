package api

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strings"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
)

type Settings struct {
	RefreshFrequencyMinutes int                 `json:"refresh_frequency_minutes"`
	IntradayRefreshSeconds  int                 `json:"intraday_refresh_seconds"`
	SelectedSymbols         []string            `json:"selected_symbols"`
	ManualComponentWeights  *map[string]float64 `json:"manual_component_weights"`
	OptionCleanupEnabled    bool                `json:"option_cleanup_enabled"`
	OptionRetentionDays     int                 `json:"option_retention_days"`
	SVIXDownsampleEnabled   bool                `json:"svix_downsample_enabled"`
	DetailedRetentionDays   int                 `json:"detailed_retention_days"`
	MaintenanceTimeUTC      string              `json:"maintenance_time_utc"`
}

var settingsKeys = []string{
	"refresh_frequency_minutes", "intraday_refresh_seconds", "selected_symbols",
	"manual_component_weights", "option_cleanup_enabled", "option_retention_days",
	"svix_downsample_enabled", "detailed_retention_days", "maintenance_time_utc",
}

func defaults() Settings {
	return Settings{RefreshFrequencyMinutes: 15, IntradayRefreshSeconds: 60,
		SelectedSymbols:     []string{"SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO"},
		OptionRetentionDays: 14, SVIXDownsampleEnabled: true, DetailedRetentionDays: 7,
		MaintenanceTimeUTC: "03:30"}
}

func respond(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func invalid(w http.ResponseWriter, status int, message string) {
	respond(w, status, map[string]string{"detail": message})
}

type SettingsHandler struct{ auth *auth.Handler }

func NewSettingsHandler(authHandler *auth.Handler) *SettingsHandler {
	return &SettingsHandler{auth: authHandler}
}

func (h *SettingsHandler) load() (Settings, error) {
	result := defaults()
	encoded, _ := json.Marshal(result)
	values := map[string]json.RawMessage{}
	_ = json.Unmarshal(encoded, &values)
	rows, err := h.auth.Database().Query("SELECT key,value FROM system_settings")
	if err != nil {
		return result, err
	}
	defer rows.Close()
	allowed := map[string]bool{}
	for _, key := range settingsKeys {
		allowed[key] = true
	}
	for rows.Next() {
		var key, value string
		if err := rows.Scan(&key, &value); err != nil {
			return result, err
		}
		if allowed[key] && json.Valid([]byte(value)) {
			values[key] = json.RawMessage(value)
		}
	}
	if err := rows.Err(); err != nil {
		return result, err
	}
	merged, _ := json.Marshal(values)
	if err := json.Unmarshal(merged, &result); err != nil {
		return result, err
	}
	if result.OptionRetentionDays < 14 {
		result.OptionRetentionDays = 14
	}
	return result, nil
}

var clockPattern = regexp.MustCompile(`^([01]\d|2[0-3]):[0-5]\d$`)

func (settings Settings) validate() error {
	if settings.RefreshFrequencyMinutes < 5 || settings.RefreshFrequencyMinutes > 1440 ||
		settings.IntradayRefreshSeconds < 60 || settings.IntradayRefreshSeconds > 3600 ||
		settings.OptionRetentionDays < 14 || settings.OptionRetentionDays > 365 ||
		settings.DetailedRetentionDays < 1 || settings.DetailedRetentionDays > 365 ||
		!clockPattern.MatchString(settings.MaintenanceTimeUTC) {
		return errors.New("invalid settings")
	}
	return nil
}

func (h *SettingsHandler) save(settings Settings) error {
	tx, err := h.auth.Database().Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	encoded, err := json.Marshal(settings)
	if err != nil {
		return err
	}
	values := map[string]json.RawMessage{}
	if err := json.Unmarshal(encoded, &values); err != nil {
		return err
	}
	for _, key := range settingsKeys {
		_, err := tx.Exec(`INSERT INTO system_settings (key,value,updated_at) VALUES ($1,$2,now())
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=now()`, key, string(values[key]))
		if err != nil {
			return err
		}
	}
	return tx.Commit()
}

func nullableTime(value sql.NullTime) any {
	if value.Valid {
		return value.Time.UTC()
	}
	return nil
}

func (h *SettingsHandler) lifecycle(w http.ResponseWriter) {
	db := h.auth.Database()
	var optionRows, optionBytes, historyRows, historyBytes, dailyRows, dailyBytes int64
	err := db.QueryRow(`SELECT
        (SELECT count(*) FROM option_snapshot),pg_total_relation_size('option_snapshot'),
        (SELECT count(*) FROM svix_history),pg_total_relation_size('svix_history'),
        (SELECT count(*) FROM svix_daily),pg_total_relation_size('svix_daily')`).Scan(
		&optionRows, &optionBytes, &historyRows, &historyBytes, &dailyRows, &dailyBytes)
	if err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	var status string
	var started, finished sql.NullTime
	var deleted, aggregated, written int64
	lastRun := any(nil)
	err = db.QueryRow(`SELECT status,started_at,finished_at,option_rows_deleted,history_rows_aggregated,daily_rows_written
        FROM data_maintenance_runs ORDER BY started_at DESC LIMIT 1`).Scan(
		&status, &started, &finished, &deleted, &aggregated, &written)
	if err == nil {
		lastRun = map[string]any{"status": status, "started_at": nullableTime(started), "finished_at": nullableTime(finished),
			"option_rows_deleted": deleted, "history_rows_aggregated": aggregated, "daily_rows_written": written}
	} else if err != sql.ErrNoRows {
		invalid(w, 503, "Database unavailable")
		return
	}
	respond(w, 200, map[string]any{"option_snapshot_rows": optionRows, "option_snapshot_bytes": optionBytes,
		"svix_history_rows": historyRows, "svix_history_bytes": historyBytes,
		"svix_daily_rows": dailyRows, "svix_daily_bytes": dailyBytes, "last_run": lastRun})
}

func (h *SettingsHandler) requestLifecycle(w http.ResponseWriter) {
	_, err := h.auth.Database().Exec(`INSERT INTO system_settings (key,value,updated_at) VALUES ('maintenance_requested','true',now())
        ON CONFLICT(key) DO UPDATE SET value='true',updated_at=now()`)
	if err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	respond(w, 202, map[string]string{"status": "queued"})
}

func (h *SettingsHandler) systemStatus(w http.ResponseWriter) {
	db := h.auth.Database()
	if err := db.Ping(); err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	var configured, queued bool
	var last sql.NullTime
	err := db.QueryRow(`SELECT EXISTS(SELECT 1 FROM provider_credentials WHERE enabled=true),
        EXISTS(SELECT 1 FROM calculation_jobs WHERE status IN ('PENDING','RUNNING')),
        COALESCE((SELECT max(timestamp) FROM svix_history),(SELECT max(date)::timestamptz FROM svix_daily))`).Scan(&configured, &queued, &last)
	if err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	market, worker := "Not configured", "Go scheduler idle"
	if configured {
		market = "Configured"
	}
	if queued {
		worker = "Queued"
	}
	respond(w, 200, map[string]any{"database": "OK", "market_data": market, "svix_engine": "Go",
		"worker": worker, "last_calculation": nullableTime(last)})
}

func (h *SettingsHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !h.auth.Authorize(w, r) {
		return
	}
	path := strings.TrimSuffix(r.URL.Path, "/")
	switch {
	case path == "/api/settings" && r.Method == http.MethodGet:
		settings, err := h.load()
		if err != nil {
			invalid(w, 503, "Settings unavailable")
			return
		}
		respond(w, 200, settings)
	case path == "/api/settings" && r.Method == http.MethodPut:
		settings := defaults()
		decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
		decoder.DisallowUnknownFields()
		if decoder.Decode(&settings) != nil || settings.validate() != nil {
			invalid(w, 422, "Invalid settings")
			return
		}
		if err := h.save(settings); err != nil {
			invalid(w, 503, "Settings could not be saved")
			return
		}
		respond(w, 200, settings)
	case path == "/api/settings/system-status" && r.Method == http.MethodGet:
		h.systemStatus(w)
	case path == "/api/settings/data-lifecycle/status" && r.Method == http.MethodGet:
		h.lifecycle(w)
	case path == "/api/settings/data-lifecycle/run" && r.Method == http.MethodPost:
		h.requestLifecycle(w)
	default:
		invalid(w, http.StatusMethodNotAllowed, "Method not allowed")
	}
}
