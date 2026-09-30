package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/market"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/symbols"
)

type CustomHandler struct {
	auth      *auth.Handler
	directory SymbolDirectory
}

type SymbolDirectory interface {
	Lookup(context.Context, string) (symbols.ListedSymbol, bool, error)
}

func NewCustomHandler(a *auth.Handler, d SymbolDirectory) *CustomHandler {
	return &CustomHandler{a, d}
}

type componentInput struct {
	Symbol string  `json:"symbol"`
	Weight float64 `json:"weight_percent"`
}
type customInput struct {
	Name       string           `json:"name"`
	Enabled    bool             `json:"enabled"`
	Policy     string           `json:"missing_policy"`
	Components []componentInput `json:"components"`
}
type customConfig struct {
	customInput
	ID        int       `json:"id"`
	Version   int       `json:"version"`
	Updated   time.Time `json:"updated_at"`
	versionID int
}
type customPoint struct {
	Timestamp time.Time `json:"timestamp"`
	Value     float64   `json:"value"`
	Quality   float64   `json:"calculation_quality"`
	Estimated bool      `json:"estimated"`
	Source    *string   `json:"source_feed"`
	Version   int       `json:"version"`
}

var componentSymbol = regexp.MustCompile(`^[A-Z][A-Z0-9.-]{0,15}$`)

func validateCustom(p *customInput) error {
	p.Name = strings.TrimSpace(p.Name)
	if utf8.RuneCountInString(p.Name) < 1 || utf8.RuneCountInString(p.Name) > 64 || (p.Policy != "STRICT" && p.Policy != "RENORMALIZE") || len(p.Components) < 1 || len(p.Components) > 20 {
		return errors.New("invalid custom index")
	}
	seen := map[string]bool{}
	total := 0.0
	for i := range p.Components {
		c := &p.Components[i]
		c.Symbol = strings.ToUpper(strings.TrimSpace(c.Symbol))
		if !componentSymbol.MatchString(c.Symbol) || seen[c.Symbol] || math.IsNaN(c.Weight) || math.IsInf(c.Weight, 0) || c.Weight <= 0 || c.Weight > 100 {
			return errors.New("invalid components")
		}
		seen[c.Symbol] = true
		total += c.Weight
	}
	if math.Abs(total-100) > 0.01 {
		return errors.New("component weights must total 100%")
	}
	return nil
}

type queryer interface {
	QueryRowContext(context.Context, string, ...any) *sql.Row
	QueryContext(context.Context, string, ...any) (*sql.Rows, error)
}

func loadCustom(ctx context.Context, db queryer) (*customConfig, error) {
	c := &customConfig{}
	err := db.QueryRowContext(ctx, `SELECT i.id,i.name,i.enabled,i.missing_policy,i.updated_at,v.id,v.version_number
 FROM custom_indices i JOIN LATERAL (SELECT id,version_number FROM custom_index_versions WHERE custom_index_id=i.id ORDER BY version_number DESC LIMIT 1) v ON true ORDER BY i.id LIMIT 1`).Scan(&c.ID, &c.Name, &c.Enabled, &c.Policy, &c.Updated, &c.versionID, &c.Version)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	rows, err := db.QueryContext(ctx, "SELECT symbol,weight*100 FROM custom_index_components WHERE version_id=$1 ORDER BY id", c.versionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	c.Components = make([]componentInput, 0)
	for rows.Next() {
		var p componentInput
		if err := rows.Scan(&p.Symbol, &p.Weight); err != nil {
			return nil, err
		}
		c.Components = append(c.Components, p)
	}
	return c, rows.Err()
}
func sameCustom(old *customConfig, p customInput) bool {
	if old == nil || old.Name != p.Name || old.Policy != p.Policy || len(old.Components) != len(p.Components) {
		return false
	}
	weights := map[string]float64{}
	for _, c := range old.Components {
		weights[c.Symbol] = c.Weight
	}
	for _, c := range p.Components {
		w, ok := weights[c.Symbol]
		if !ok || math.Abs(w-c.Weight) > 1e-10 {
			return false
		}
	}
	return true
}
func (h *CustomHandler) save(w http.ResponseWriter, r *http.Request) {
	p := customInput{Enabled: true, Policy: "STRICT"}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 32<<10))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&p) != nil || validateCustom(&p) != nil {
		invalid(w, 422, "Invalid custom index or component weights")
		return
	}
	for _, c := range p.Components {
		_, found, err := h.directory.Lookup(r.Context(), c.Symbol)
		if err != nil {
			invalid(w, 503, "标的目录暂时不可用，请稍后重试")
			return
		}
		if !found {
			invalid(w, 422, "未找到标的代码 "+c.Symbol)
			return
		}
	}
	tx, err := h.auth.Database().BeginTx(r.Context(), nil)
	if err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(r.Context(), "SELECT pg_advisory_xact_lock(hashtext('svix_custom_configuration'))"); err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	old, err := loadCustom(r.Context(), tx)
	if err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	id, number := 0, 1
	if old == nil {
		err = tx.QueryRowContext(r.Context(), "INSERT INTO custom_indices(name,enabled,missing_policy,created_at,updated_at) VALUES($1,$2,$3,now(),now()) RETURNING id", p.Name, p.Enabled, p.Policy).Scan(&id)
	} else {
		id = old.ID
		number = old.Version + 1
		_, err = tx.ExecContext(r.Context(), "UPDATE custom_indices SET name=$1,enabled=$2,missing_policy=$3,updated_at=now() WHERE id=$4", p.Name, p.Enabled, p.Policy, id)
	}
	if err == nil && !sameCustom(old, p) {
		var versionID int
		err = tx.QueryRowContext(r.Context(), "INSERT INTO custom_index_versions(custom_index_id,version_number,name,missing_policy,created_at) VALUES($1,$2,$3,$4,now()) RETURNING id", id, number, p.Name, p.Policy).Scan(&versionID)
		if err == nil {
			for _, c := range p.Components {
				_, err = tx.ExecContext(r.Context(), "INSERT INTO custom_index_components(version_id,symbol,weight) VALUES($1,$2,$3)", versionID, c.Symbol, c.Weight/100)
				if err != nil {
					break
				}
			}
		}
	}
	if err == nil {
		_, err = tx.ExecContext(r.Context(), "INSERT INTO audit_events(admin_id,action,created_at) VALUES(1,'custom_index.updated',now())")
	}
	if err != nil || tx.Commit() != nil {
		invalid(w, 503, "Custom index could not be saved")
		return
	}
	c, err := loadCustom(r.Context(), h.auth.Database())
	if err != nil {
		invalid(w, 503, "Custom index unavailable")
		return
	}
	respond(w, 200, c)
}

const customHistoryColumns = `timestamp,value,calculation_quality,estimated,source_feed`
const customDailyColumns = `COALESCE(close_timestamp,date::timestamp AT TIME ZONE 'UTC'),value_close,min_calculation_quality,estimated,source_feed`

func scanCustom(row scanner, version int) (customPoint, error) {
	p := customPoint{Version: version}
	err := row.Scan(&p.Timestamp, &p.Value, &p.Quality, &p.Estimated, &p.Source)
	return p, err
}
func (h *CustomHandler) series(r *http.Request, c *customConfig, path string) (any, error) {
	db := h.auth.Database()
	if path == "/api/custom-index/current" {
		if c == nil {
			return nil, sql.ErrNoRows
		}
		p, err := scanCustom(db.QueryRowContext(r.Context(), "SELECT "+customHistoryColumns+" FROM custom_index_history WHERE custom_index_id=$1 AND version_id=$2 ORDER BY timestamp DESC LIMIT 1", c.ID, c.versionID), c.Version)
		if err == sql.ErrNoRows {
			p, err = scanCustom(db.QueryRowContext(r.Context(), "SELECT "+customDailyColumns+" FROM custom_index_daily WHERE custom_index_id=$1 AND version_id=$2 ORDER BY date DESC LIMIT 1", c.ID, c.versionID), c.Version)
		}
		return p, err
	}
	points := make([]customPoint, 0)
	var rows *sql.Rows
	var err error
	if path == "/api/custom-index/history" {
		start, end, _, e := dateRange(r)
		if e != nil {
			return nil, e
		}
		if c == nil {
			return points, nil
		}
		rows, err = db.QueryContext(r.Context(), `WITH selected AS (SELECT DISTINCT ON ((timestamp AT TIME ZONE 'UTC')::date) `+customHistoryColumns+`
   FROM custom_index_history WHERE custom_index_id=$1 AND version_id=$2 AND timestamp >= $3 AND timestamp < $4
   ORDER BY (timestamp AT TIME ZONE 'UTC')::date,estimated ASC,timestamp DESC)
   SELECT `+customHistoryColumns+` FROM selected UNION ALL SELECT `+customDailyColumns+` FROM custom_index_daily d
   WHERE custom_index_id=$1 AND version_id=$2 AND date >= $3::timestamptz::date AND date < $4::timestamptz::date
   AND NOT EXISTS(SELECT 1 FROM selected s WHERE (s.timestamp AT TIME ZONE 'UTC')::date=d.date) ORDER BY 1`, c.ID, c.versionID, start, end.AddDate(0, 0, 1))
	} else {
		day := r.URL.Query().Get("session_date")
		if day != "" {
			if _, e := time.Parse("2006-01-02", day); e != nil {
				return nil, e
			}
		} else {
			status, e := market.Current(time.Now())
			if e != nil {
				return nil, e
			}
			if status.SessionDate != nil {
				day = *status.SessionDate
			}
		}
		if c == nil || day == "" {
			return points, nil
		}
		start, end, ok := market.Bounds(day)
		if !ok {
			return points, nil
		}
		rows, err = db.QueryContext(r.Context(), "SELECT "+customHistoryColumns+" FROM custom_index_history WHERE custom_index_id=$1 AND version_id=$2 AND timestamp >= $3 AND timestamp <= $4 ORDER BY timestamp", c.ID, c.versionID, start, end)
	}
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		p, err := scanCustom(rows, c.Version)
		if err != nil {
			return nil, err
		}
		points = append(points, p)
	}
	return points, rows.Err()
}
func (h *CustomHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !h.auth.Authorize(w, r) {
		return
	}
	path := strings.TrimSuffix(r.URL.Path, "/")
	if path == "/api/custom-index" && r.Method == http.MethodPut {
		h.save(w, r)
		return
	}
	if r.Method != http.MethodGet {
		invalid(w, 405, "Method not allowed")
		return
	}
	if path != "/api/custom-index" && path != "/api/custom-index/current" && path != "/api/custom-index/history" && path != "/api/custom-index/intraday" {
		invalid(w, 404, "Not found")
		return
	}
	// Reject invalid date input before running database queries.
	if path == "/api/custom-index/history" {
		if _, _, _, err := dateRange(r); err != nil {
			invalid(w, 422, err.Error())
			return
		}
	}
	if path == "/api/custom-index/intraday" && r.URL.Query().Get("session_date") != "" {
		if _, err := time.Parse("2006-01-02", r.URL.Query().Get("session_date")); err != nil {
			invalid(w, 422, "Invalid session_date")
			return
		}
	}
	c, err := loadCustom(r.Context(), h.auth.Database())
	if err != nil {
		invalid(w, 503, "Custom index unavailable")
		return
	}
	if path == "/api/custom-index" {
		respond(w, 200, c)
		return
	}
	result, err := h.series(r, c, path)
	if err == sql.ErrNoRows {
		invalid(w, 404, "No custom index calculation is available")
		return
	}
	if err != nil {
		invalid(w, 503, "Custom index data unavailable")
		return
	}
	respond(w, 200, result)
}
