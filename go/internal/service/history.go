package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"math"
	"sort"
	"strings"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/engine"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/providers"
)

var Universe = []string{"SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO"}

type Service struct {
	DB        *sql.DB
	Providers *providers.Store
}
type Definition struct {
	ID, Version int
	Policy      string
	Weights     map[string]float64
}
type quoteRow struct {
	engine.OptionQuote
	Provider, Feed, PriceType string
	Batch                     sql.NullString
}

func (s *Service) Definitions(ctx context.Context) ([]Definition, error) {
	rows, err := s.DB.QueryContext(ctx, `SELECT i.id,v.id,v.missing_policy,c.symbol,c.weight FROM custom_indices i
 JOIN LATERAL (SELECT id,missing_policy FROM custom_index_versions WHERE custom_index_id=i.id ORDER BY version_number DESC LIMIT 1) v ON true
 JOIN custom_index_components c ON c.version_id=v.id WHERE i.enabled=true ORDER BY i.id,c.symbol`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]Definition, 0)
	for rows.Next() {
		var id, version int
		var policy, symbol string
		var weight float64
		if err := rows.Scan(&id, &version, &policy, &symbol, &weight); err != nil {
			return nil, err
		}
		if len(out) == 0 || out[len(out)-1].ID != id {
			out = append(out, Definition{ID: id, Version: version, Policy: policy, Weights: map[string]float64{}})
		}
		out[len(out)-1].Weights[symbol] = weight
	}
	return out, rows.Err()
}
func (s *Service) Symbols(ctx context.Context, selected bool) ([]string, error) {
	names := append([]string{}, Universe...)
	if selected {
		var encoded string
		err := s.DB.QueryRowContext(ctx, "SELECT value FROM system_settings WHERE key='selected_symbols'").Scan(&encoded)
		if err != nil && err != sql.ErrNoRows {
			return nil, err
		}
		var chosen []string
		if err == nil && json.Unmarshal([]byte(encoded), &chosen) == nil && len(chosen) > 0 {
			names = chosen
		}
	}
	definitions, err := s.Definitions(ctx)
	if err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	for _, name := range names {
		seen[name] = true
	}
	for _, d := range definitions {
		for name := range d.Weights {
			if !seen[name] {
				names = append(names, name)
				seen[name] = true
			}
		}
	}
	return names, nil
}
func (s *Service) Provider(ctx context.Context) (string, error) {
	c, err := s.Providers.Credential("")
	if err != nil {
		return "", err
	}
	if c != nil {
		if !providers.Available(c.Provider) {
			return "", errors.New("configured provider is unavailable in this edition")
		}
		return c.Provider, nil
	}
	return providers.DefaultProvider(), nil
}
func scanQuote(row interface{ Scan(...any) error }) (quoteRow, error) {
	var q quoteRow
	err := row.Scan(&q.ContractID, &q.Symbol, &q.Expiry, &q.Strike, &q.OptionType, &q.Bid, &q.Ask, &q.Last, &q.Timestamp, &q.Delayed, &q.Provider, &q.Feed, &q.PriceType, &q.Batch)
	if q.Provider == "ALPACA" {
		d := q.Expiry.UTC()
		q.Expiry = time.Date(d.Year(), d.Month(), d.Day(), 21, 0, 0, 0, time.UTC)
	}
	return q, err
}

const quoteColumns = `contract_id,symbol,expiry,strike,option_type,bid,ask,last,timestamp,delayed,provider,COALESCE(feed,'unknown'),price_type,batch_id`

func (s *Service) dayQuotes(ctx context.Context, provider string, day time.Time, strict bool) (map[string][]quoteRow, error) {
	query := `SELECT DISTINCT ON (contract_id) ` + quoteColumns + ` FROM option_snapshot WHERE provider=$1 AND timestamp >= $2 AND timestamp < $3`
	if strict {
		query += ` AND price_type='bbo' AND delayed IS NOT TRUE AND batch_id=(SELECT batch_id FROM option_snapshot WHERE provider=$1 AND timestamp >= $2 AND timestamp < $3 AND batch_id IS NOT NULL AND price_type='bbo' AND delayed IS NOT TRUE ORDER BY timestamp DESC LIMIT 1)`
	}
	rows, err := s.DB.QueryContext(ctx, query+" ORDER BY contract_id,timestamp DESC,id DESC", provider, day, day.AddDate(0, 0, 1))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string][]quoteRow{}
	for rows.Next() {
		q, err := scanQuote(rows)
		if err != nil {
			return nil, err
		}
		out[q.Symbol] = append(out[q.Symbol], q)
	}
	return out, rows.Err()
}
func (s *Service) Prices(ctx context.Context, provider string, start, end, available time.Time, dailyOnly bool) (map[string]map[string]float64, error) {
	query := `SELECT DISTINCT ON (symbol,(timestamp AT TIME ZONE 'UTC')::date) symbol,(timestamp AT TIME ZONE 'UTC')::date,price FROM stock_snapshot WHERE provider=$1 AND timestamp >= $2 AND timestamp < $3 AND price IS NOT NULL`
	args := []any{provider, start, end}
	if dailyOnly {
		query += " AND price_type IN ('adjusted_close','raw_close') AND received_at <= $4 AND price > 0"
		args = append(args, available)
	}
	rows, err := s.DB.QueryContext(ctx, query+" ORDER BY symbol,(timestamp AT TIME ZONE 'UTC')::date,timestamp DESC,id DESC", args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	histories := map[string]map[string]float64{}
	for rows.Next() {
		var symbol string
		var day time.Time
		var price float64
		if err := rows.Scan(&symbol, &day, &price); err != nil {
			return nil, err
		}
		if histories[symbol] == nil {
			histories[symbol] = map[string]float64{}
		}
		histories[symbol][day.Format("2006-01-02")] = price
	}
	return histories, rows.Err()
}
func alignedReturns(histories map[string]map[string]float64, symbols []string) (map[string][]float64, string) {
	usable := make([]string, 0)
	for _, name := range symbols {
		if len(histories[name]) >= 253 {
			usable = append(usable, name)
		}
	}
	result := map[string][]float64{}
	if len(usable) == 0 {
		return result, ""
	}
	days := make([]string, 0)
	for day := range histories[usable[0]] {
		common := true
		for _, name := range usable[1:] {
			if _, ok := histories[name][day]; !ok {
				common = false
				break
			}
		}
		if common {
			days = append(days, day)
		}
	}
	sort.Strings(days)
	if len(days) < 253 {
		return result, ""
	}
	for _, name := range usable {
		returns := make([]float64, 0, len(days)-1)
		valid := true
		for i := 1; i < len(days); i++ {
			previous, current := histories[name][days[i-1]], histories[name][days[i]]
			if previous <= 0 || current <= 0 || math.IsNaN(current) || math.IsInf(current, 0) {
				valid = false
				break
			}
			returns = append(returns, math.Log(current/previous))
		}
		if valid {
			result[name] = returns
		}
	}
	return result, days[len(days)-1]
}
func historyInput(quotes map[string][]quoteRow, histories map[string]map[string]float64, names []string, strict bool) (engine.SVIXInput, error) {
	candidates := make([]string, 0)
	for _, name := range names {
		if len(quotes[name]) > 0 && len(histories[name]) > 0 {
			candidates = append(candidates, name)
		}
	}
	returns, _ := alignedReturns(histories, candidates)
	input := engine.SVIXInput{Quotes: map[string][]engine.OptionQuote{}, Returns: returns, SpotPrices: map[string]float64{}, TargetDays: 30}
	feed, quality, batch := "", "", ""
	var earliest time.Time
	delayed := false
	for name := range returns {
		days := make([]string, 0, len(histories[name]))
		for day := range histories[name] {
			days = append(days, day)
		}
		sort.Strings(days)
		input.SpotPrices[name] = histories[name][days[len(days)-1]]
		for _, q := range quotes[name] {
			identity := strings.ToLower(q.Provider) + ":" + strings.ToLower(q.Feed)
			b := ""
			if q.Batch.Valid {
				b = q.Batch.String
			}
			if feed == "" {
				feed = identity
				quality = q.PriceType
				batch = b
			} else if feed != identity || quality != q.PriceType || batch != b {
				return input, errors.New("mixed provider, feed, price type or batch")
			}
			input.Quotes[name] = append(input.Quotes[name], q.OptionQuote)
			if q.Timestamp.After(input.ValuationAt) {
				input.ValuationAt = q.Timestamp
			}
			if earliest.IsZero() || q.Timestamp.Before(earliest) {
				earliest = q.Timestamp
			}
			if q.Delayed != nil && *q.Delayed {
				delayed = true
			}
		}
	}
	if feed == "" {
		return input, errors.New("no option quotes")
	}
	if input.ValuationAt.Sub(earliest) > 5*time.Minute {
		return input, errors.New("incoherent valuation window")
	}
	input.SourceFeed = &feed
	input.MarketQuality = quality
	input.Approximate = !strict && (quality != "bbo" || delayed)
	return input, nil
}

type HistorySummary struct {
	Records   int `json:"records_calculated"`
	Estimated int `json:"estimated_records"`
	Attempted int `json:"attempted_records"`
	Skipped   int `json:"skipped_records"`
}

func (s *Service) History(ctx context.Context, start, end time.Time, frequency string, strict bool) (HistorySummary, error) {
	var summary HistorySummary
	if end.Before(start) || (frequency != "daily" && frequency != "weekly") {
		return summary, errors.New("invalid history range")
	}
	provider, err := s.Provider(ctx)
	if err != nil {
		return summary, err
	}
	definitions, err := s.Definitions(ctx)
	if err != nil {
		return summary, err
	}
	rows, err := s.DB.QueryContext(ctx, `SELECT DISTINCT (timestamp AT TIME ZONE 'UTC')::date FROM option_snapshot WHERE provider=$1 AND timestamp >= $2 AND timestamp < $3 ORDER BY 1`, provider, start, end.AddDate(0, 0, 1))
	if err != nil {
		return summary, err
	}
	dates := make([]time.Time, 0)
	for rows.Next() {
		var day time.Time
		if err := rows.Scan(&day); err != nil {
			rows.Close()
			return summary, err
		}
		dates = append(dates, day)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return summary, err
	}
	if frequency == "weekly" {
		weekly := make([]time.Time, 0)
		for _, day := range dates {
			y, w := day.ISOWeek()
			if len(weekly) > 0 {
				py, pw := weekly[len(weekly)-1].ISOWeek()
				if y == py && w == pw {
					weekly[len(weekly)-1] = day
					continue
				}
			}
			weekly = append(weekly, day)
		}
		dates = weekly
	}
	summary.Attempted = len(dates)
	for _, day := range dates {
		if err := ctx.Err(); err != nil {
			return summary, err
		}
		quotes, err := s.dayQuotes(ctx, provider, day, strict)
		if err != nil {
			return summary, err
		}
		prices, err := s.Prices(ctx, provider, day.AddDate(0, 0, -400), day.AddDate(0, 0, 1), time.Time{}, false)
		if err != nil {
			return summary, err
		}
		input, inputErr := historyInput(quotes, prices, Universe, strict)
		tx, err := s.DB.BeginTx(ctx, nil)
		if err != nil {
			return summary, err
		}
		if inputErr == nil {
			if result, e := engine.CalculateSVIX(input); e == nil {
				_, err = tx.ExecContext(ctx, `INSERT INTO svix_history(timestamp,svix,core_vol,memory_vol,ai_vol,calculation_quality,estimated,source_feed,calculation_method,market_data_quality,created_at)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,now()) ON CONFLICT(timestamp) DO UPDATE SET svix=$2,core_vol=$3,memory_vol=$4,ai_vol=$5,calculation_quality=$6,estimated=$7,source_feed=$8,calculation_method=$9,market_data_quality=$10
    WHERE svix_history.estimated OR NOT EXCLUDED.estimated`, result.Timestamp, result.SVIX, result.CoreVol, result.MemoryVol, result.AIVol, result.CalculationQuality, result.Estimated, result.SourceFeed, result.CalculationMethod, result.MarketDataQuality)
				if err == nil {
					summary.Records++
					if result.Estimated {
						summary.Estimated++
					}
				}
			}
		}
		if err != nil {
			tx.Rollback()
			return summary, err
		}
		for _, d := range definitions {
			names := make([]string, 0, len(d.Weights))
			for name := range d.Weights {
				names = append(names, name)
			}
			input, e := historyInput(quotes, prices, names, strict)
			if e != nil {
				continue
			}
			result, e := engine.CalculateCustom(input, d.Weights, d.Policy)
			if e != nil {
				continue
			}
			_, err = tx.ExecContext(ctx, `INSERT INTO custom_index_history(custom_index_id,version_id,timestamp,value,calculation_quality,estimated,source_feed,created_at)
    VALUES($1,$2,$3,$4,$5,$6,$7,now()) ON CONFLICT(custom_index_id,version_id,timestamp) DO UPDATE SET value=$4,calculation_quality=$5,estimated=$6,source_feed=$7 WHERE custom_index_history.estimated OR NOT EXCLUDED.estimated`, d.ID, d.Version, input.ValuationAt, result.Value, result.Quality, input.Approximate, input.SourceFeed)
			if err != nil {
				tx.Rollback()
				return summary, err
			}
		}
		if err = tx.Commit(); err != nil {
			return summary, err
		}
	}
	summary.Skipped = summary.Attempted - summary.Records
	return summary, nil
}
