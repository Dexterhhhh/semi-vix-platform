package api

import (
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/market"
)

type SVIXHandler struct{ auth *auth.Handler }

func NewSVIXHandler(a *auth.Handler) *SVIXHandler { return &SVIXHandler{auth: a} }

type svixPoint struct {
	Timestamp   time.Time `json:"timestamp"`
	SVIX        *float64  `json:"svix"`
	Core        *float64  `json:"core"`
	Memory      *float64  `json:"memory"`
	AI          *float64  `json:"ai"`
	Quality     float64   `json:"calculation_quality"`
	Estimated   bool      `json:"estimated"`
	Source      *string   `json:"source_feed"`
	Method      string    `json:"calculation_method"`
	DataQuality string    `json:"market_data_quality"`
}

type observationPoint struct {
	svixPoint
	Status         string         `json:"status"`
	Coverage       float64        `json:"coverage"`
	CachedCoverage float64        `json:"cached_coverage"`
	BatchID        *string        `json:"batch_id"`
	OldestInput    any            `json:"oldest_input_at"`
	ComparableKey  *string        `json:"comparable_key"`
	Counts         any            `json:"component_counts"`
	Reasons        any            `json:"reasons"`
	Details        map[string]any `json:"details"`
}

const historyColumns = `timestamp,svix,core_vol,memory_vol,ai_vol,calculation_quality,estimated,source_feed,calculation_method,market_data_quality`
const dailyColumns = `COALESCE(close_timestamp,date::timestamp AT TIME ZONE 'UTC'),svix_close,core_close,memory_close,ai_close,min_calculation_quality,estimated,source_feed,'legacy','unknown'`
const observationColumns = `valuation_at,svix,core,memory,ai,source_feed,method_version,status,coverage,cached_coverage,batch_id,details`

type scanner interface{ Scan(...any) error }

func scanPoint(row scanner) (svixPoint, error) {
	var p svixPoint
	err := row.Scan(&p.Timestamp, &p.SVIX, &p.Core, &p.Memory, &p.AI, &p.Quality, &p.Estimated, &p.Source, &p.Method, &p.DataQuality)
	return p, err
}

func legacyPoint(p svixPoint) observationPoint {
	return observationPoint{svixPoint: p, Status: "LEGACY", Coverage: 1, ComparableKey: &p.Method, Counts: map[string]string{}, Reasons: map[string]string{}, Details: map[string]any{}}
}

func observationMetadata(p *observationPoint, encoded string) error {
	if err := json.Unmarshal([]byte(encoded), &p.Details); err != nil {
		return err
	}
	p.Estimated = true
	p.DataQuality = "bbo_estimate"
	if p.Source != nil && strings.HasSuffix(*p.Source, ":indicative") {
		p.DataQuality = "indicative_estimate"
	}
	p.Counts = map[string]string{}
	p.Reasons = map[string]string{}
	if v, ok := p.Details["component_counts"]; ok {
		p.Counts = v
	}
	if v, ok := p.Details["reasons"]; ok {
		p.Reasons = v
	}
	p.OldestInput = p.Details["oldest_input_at"]
	structure := make([][]any, 0)
	if assets, ok := p.Details["assets"].(map[string]any); ok {
		for symbol, value := range assets {
			if item, ok := value.(map[string]any); ok && (item["status"] == "NEW" || item["status"] == "CACHED") {
				structure = append(structure, []any{symbol, item["term_method"]})
			}
		}
	}
	sort.Slice(structure, func(i, j int) bool { return structure[i][0].(string) < structure[j][0].(string) })
	// Python json.dumps includes spaces; preserve the existing comparison key.
	key, _ := json.Marshal([]any{p.Method, structure})
	var pretty strings.Builder
	quoted, escaped := false, false
	for _, c := range string(key) {
		pretty.WriteRune(c)
		if escaped {
			escaped = false
			continue
		}
		if c == '\\' && quoted {
			escaped = true
			continue
		}
		if c == '"' {
			quoted = !quoted
		}
		if !quoted && (c == ',' || c == ':') {
			pretty.WriteByte(' ')
		}
	}
	result := pretty.String()
	p.ComparableKey = &result
	return nil
}

func scanObservation(row scanner) (observationPoint, error) {
	var p observationPoint
	var details string
	err := row.Scan(&p.Timestamp, &p.SVIX, &p.Core, &p.Memory, &p.AI, &p.Source, &p.Method, &p.Status, &p.Coverage, &p.CachedCoverage, &p.BatchID, &details)
	if err == nil {
		err = observationMetadata(&p, details)
	}
	return p, err
}

func (h *SVIXHandler) current() (observationPoint, error) {
	db := h.auth.Database()
	p, err := scanObservation(db.QueryRow("SELECT " + observationColumns + " FROM svix_observations ORDER BY valuation_at DESC,id DESC LIMIT 1"))
	if err != sql.ErrNoRows {
		return p, err
	}
	legacy, err := scanPoint(db.QueryRow("SELECT " + historyColumns + " FROM svix_history ORDER BY timestamp DESC LIMIT 1"))
	if err != sql.ErrNoRows {
		return legacyPoint(legacy), err
	}
	legacy, err = scanPoint(db.QueryRow("SELECT " + dailyColumns + " FROM svix_daily ORDER BY date DESC LIMIT 1"))
	return legacyPoint(legacy), err
}

func dateRange(r *http.Request) (time.Time, time.Time, string, error) {
	start, e1 := time.Parse("2006-01-02", r.URL.Query().Get("start_date"))
	end, e2 := time.Parse("2006-01-02", r.URL.Query().Get("end_date"))
	freq := r.URL.Query().Get("frequency")
	if freq == "" {
		freq = "daily"
	}
	if e1 != nil || e2 != nil || end.Before(start) || (freq != "daily" && freq != "weekly") {
		return start, end, freq, errors.New("invalid date range or frequency")
	}
	return start, end, freq, nil
}

func weeklyPoints(points []svixPoint) []svixPoint {
	out := make([]svixPoint, 0)
	for _, p := range points {
		y, w := p.Timestamp.ISOWeek()
		if len(out) > 0 {
			py, pw := out[len(out)-1].Timestamp.ISOWeek()
			if py == y && pw == w {
				out[len(out)-1] = p
				continue
			}
		}
		out = append(out, p)
	}
	return out
}

func (h *SVIXHandler) history(start, end time.Time, frequency string) ([]svixPoint, error) {
	// Select each day's latest strict result before falling back to estimates.
	rows, err := h.auth.Database().Query(`WITH selected AS (
	 SELECT DISTINCT ON ((timestamp AT TIME ZONE 'UTC')::date) `+historyColumns+`
	 FROM svix_history WHERE timestamp >= $1 AND timestamp < $2
	 ORDER BY (timestamp AT TIME ZONE 'UTC')::date,estimated ASC,timestamp DESC
	) SELECT `+historyColumns+` FROM selected
	UNION ALL SELECT `+dailyColumns+` FROM svix_daily d
	WHERE date >= $1::timestamptz::date AND date < $2::timestamptz::date
	AND NOT EXISTS(SELECT 1 FROM selected s WHERE (s.timestamp AT TIME ZONE 'UTC')::date=d.date)
	ORDER BY 1`, start, end.AddDate(0, 0, 1))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	points := make([]svixPoint, 0)
	for rows.Next() {
		p, err := scanPoint(rows)
		if err != nil {
			return nil, err
		}
		points = append(points, p)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if frequency == "weekly" {
		points = weeklyPoints(points)
	}
	return points, nil
}

func (h *SVIXHandler) intraday(day string) ([]observationPoint, error) {
	points := make([]observationPoint, 0)
	if day == "" {
		status, err := market.Current(time.Now())
		if err != nil {
			return nil, err
		}
		if status.SessionDate == nil {
			return points, nil
		}
		day = *status.SessionDate
	}
	start, end, ok := market.Bounds(day)
	if !ok {
		return points, nil
	}
	rows, err := h.auth.Database().Query("SELECT "+observationColumns+" FROM svix_observations WHERE session_date=$1 AND valuation_at >= $2 AND valuation_at <= $3 ORDER BY valuation_at,id", day, start, end)
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		p, err := scanObservation(rows)
		if err != nil {
			rows.Close()
			return nil, err
		}
		points = append(points, p)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	if len(points) > 0 {
		return points, nil
	}
	rows, err = h.auth.Database().Query("SELECT "+historyColumns+" FROM svix_history WHERE timestamp >= $1 AND timestamp <= $2 ORDER BY timestamp", start, end)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		p, err := scanPoint(rows)
		if err != nil {
			return nil, err
		}
		points = append(points, legacyPoint(p))
	}
	return points, rows.Err()
}

func (h *SVIXHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !h.auth.Authorize(w, r) {
		return
	}
	if r.Method != http.MethodGet {
		invalid(w, 405, "Method not allowed")
		return
	}
	var result any
	var err error
	switch strings.TrimSuffix(r.URL.Path, "/") {
	case "/api/svix/current", "/api/svix/components":
		var p observationPoint
		p, err = h.current()
		result = p
		if strings.HasSuffix(r.URL.Path, "components") {
			result = map[string]any{"core": p.Core, "memory": p.Memory, "ai": p.AI}
		}
	case "/api/svix/history":
		start, end, freq, parseErr := dateRange(r)
		if parseErr != nil {
			invalid(w, 422, parseErr.Error())
			return
		}
		result, err = h.history(start, end, freq)
	case "/api/svix/intraday":
		day := r.URL.Query().Get("session_date")
		if day != "" {
			if _, e := time.Parse("2006-01-02", day); e != nil {
				invalid(w, 422, "Invalid session_date")
				return
			}
		}
		result, err = h.intraday(day)
	default:
		invalid(w, 404, "Not found")
		return
	}
	if err == sql.ErrNoRows {
		invalid(w, 404, "No SVIX calculation is available")
		return
	}
	if err != nil {
		invalid(w, 503, "SVIX data unavailable")
		return
	}
	respond(w, 200, result)
}
