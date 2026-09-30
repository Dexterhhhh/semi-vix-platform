package api

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/market"
)

type MarketStatusHandler struct{ auth *auth.Handler }

func NewMarketStatusHandler(authHandler *auth.Handler) *MarketStatusHandler {
	return &MarketStatusHandler{auth: authHandler}
}

func (h *MarketStatusHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		invalid(w, 405, "Method not allowed")
		return
	}
	if !h.auth.Authorize(w, r) {
		return
	}
	status, err := market.Current(time.Now())
	if err != nil {
		invalid(w, 503, "NYSE calendar unavailable")
		return
	}
	var sessionDate, started time.Time
	var finished sql.NullTime
	var latestStatus string
	var calculationStatus sql.NullString
	var retryAfter sql.NullInt64
	err = h.auth.Database().QueryRow(`SELECT session_date,started_at,finished_at,status,calculation_status,retry_after_seconds
        FROM market_collection_runs ORDER BY started_at DESC LIMIT 1`).Scan(
		&sessionDate, &started, &finished, &latestStatus, &calculationStatus, &retryAfter)
	hasLatest := err == nil
	if err != nil && err != sql.ErrNoRows {
		invalid(w, 503, "Market status unavailable")
		return
	}
	var next *time.Time = status.NextOpen
	if status.IsCollectionWindow {
		interval := 60
		var encoded string
		err := h.auth.Database().QueryRow("SELECT value FROM system_settings WHERE key='intraday_refresh_seconds'").Scan(&encoded)
		if err == nil {
			_ = json.Unmarshal([]byte(encoded), &interval)
		} else if err != sql.ErrNoRows {
			invalid(w, 503, "Market status unavailable")
			return
		}
		if interval < 60 {
			interval = 60
		}
		if interval > 3600 {
			interval = 3600
		}
		now := time.Now().UTC()
		due := now
		if hasLatest && status.SessionDate != nil && sessionDate.Format("2006-01-02") == *status.SessionDate {
			if intervalDue := started.Add(time.Duration(interval) * time.Second); intervalDue.After(due) {
				due = intervalDue
			}
			if finished.Valid && retryAfter.Valid {
				if retryDue := finished.Time.Add(time.Duration(retryAfter.Int64) * time.Second); retryDue.After(due) {
					due = retryDue
				}
			}
		}
		if status.CollectionEnd == nil || due.After(*status.CollectionEnd) {
			next = nil
		} else {
			next = &due
		}
	}
	value := map[string]any{"state": status.State, "is_collection_window": status.IsCollectionWindow,
		"session_date": status.SessionDate, "market_open": status.MarketOpen, "market_close": status.MarketClose,
		"collection_end": status.CollectionEnd, "next_open": status.NextOpen,
		"last_collection_at": nil, "last_collection_status": nil,
		"last_calculation_status": nil, "next_collection_at": next}
	if hasLatest {
		value["last_collection_at"] = nullableTime(finished)
		value["last_collection_status"] = latestStatus
		if calculationStatus.Valid {
			value["last_calculation_status"] = calculationStatus.String
		}
	}
	respond(w, 200, value)
}
