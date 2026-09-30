package service

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"sort"
	"strings"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/engine"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/market"
)

const ObservationMethod = "semivix-observe-v1"

var Groups = map[string][]string{"core": {"SOXX"}, "memory": {"MU", "SKHY"}, "ai": {"NVDA", "AMD", "AVGO"}}

func (s *Service) observationCorrelation(ctx context.Context, tx *sql.Tx, provider, session string, valuation time.Time, names []string) (*engine.CorrelationResult, *string, string, error) {
	previous, ok := market.Previous(session)
	if !ok {
		return nil, nil, "NO_PREVIOUS_SESSION", nil
	}
	rows, err := tx.QueryContext(ctx, `SELECT as_of,assets,matrix FROM svix_correlation_cache WHERE provider=$1 AND as_of <= $2 AND available_at <= $3 ORDER BY as_of DESC,available_at DESC`, provider, previous, valuation)
	if err != nil {
		return nil, nil, "", err
	}
	for rows.Next() {
		var day time.Time
		var encodedNames, encodedMatrix string
		if err = rows.Scan(&day, &encodedNames, &encodedMatrix); err != nil {
			rows.Close()
			return nil, nil, "", err
		}
		var stored []string
		var matrix [][]float64
		if json.Unmarshal([]byte(encodedNames), &stored) != nil || json.Unmarshal([]byte(encodedMatrix), &matrix) != nil || len(matrix) != len(stored) {
			continue
		}
		indices := make([]int, 0, len(names))
		for _, name := range names {
			for i, v := range stored {
				if name == v {
					indices = append(indices, i)
					break
				}
			}
		}
		date := day.Format("2006-01-02")
		if len(indices) != len(names) || market.SessionsAgo(previous, date) > 5 {
			continue
		}
		subset := make([][]float64, len(names))
		valid := true
		for i, index := range indices {
			subset[i] = make([]float64, len(names))
			for j, col := range indices {
				if col >= len(matrix[index]) {
					valid = false
					break
				}
				subset[i][j] = matrix[index][col]
			}
		}
		if valid {
			rows.Close()
			return &engine.CorrelationResult{Assets: names, Matrix: subset, Observations: 252}, &date, "", nil
		}
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, nil, "", err
	}
	day, _ := time.Parse("2006-01-02", session)
	histories, err := s.Prices(ctx, provider, day.AddDate(0, 0, -450), day, valuation, true)
	if err != nil {
		return nil, nil, "", err
	}
	returns, asOf := alignedReturns(histories, names)
	if len(returns) != len(names) {
		return nil, nil, "INSUFFICIENT_DAILY_HISTORY", nil
	}
	corr, err := engine.Correlation(returns)
	if err != nil {
		return nil, nil, "INVALID_CORRELATION_HISTORY", nil
	}
	if market.SessionsAgo(previous, asOf) > 5 {
		return nil, nil, "CORRELATION_TOO_OLD", nil
	}
	encodedNames, _ := json.Marshal(corr.Assets)
	encodedMatrix, _ := json.Marshal(corr.Matrix)
	_, err = tx.ExecContext(ctx, `INSERT INTO svix_correlation_cache(provider,as_of,available_at,assets,matrix) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING`, provider, asOf, valuation, string(encodedNames), string(encodedMatrix))
	if err != nil {
		return nil, nil, "", err
	}
	return &corr, &asOf, "", nil
}
func (s *Service) observeComponent(ctx context.Context, tx *sql.Tx, provider, session string, valuation time.Time, names []string, assets map[string]engine.AssetObservation) (*float64, *string, string, error) {
	present := make([]string, 0)
	for _, name := range names {
		if _, ok := assets[name]; ok {
			present = append(present, name)
		}
	}
	sort.Strings(present)
	if len(present) == 0 {
		return nil, nil, "NO_ASSETS", nil
	}
	if len(present) == 1 {
		return assets[present[0]].Volatility, nil, "", nil
	}
	corr, day, reason, err := s.observationCorrelation(ctx, tx, provider, session, valuation, present)
	if err != nil || corr == nil {
		return nil, day, reason, err
	}
	weights := engine.Weights()
	total := 0.0
	for _, name := range present {
		total += weights[name]
	}
	selected, vols := map[string]float64{}, map[string]float64{}
	for _, name := range present {
		selected[name] = weights[name] / total
		vols[name] = *assets[name].Volatility / 100
	}
	p, err := engine.Portfolio(selected, vols, *corr)
	if err != nil {
		return nil, day, "INVALID_PORTFOLIO_COVARIANCE", nil
	}
	v := p.Volatility * 100
	return &v, day, "", nil
}
func (s *Service) Observation(ctx context.Context, batch string) (bool, error) {
	tx, err := s.DB.BeginTx(ctx, nil)
	if err != nil {
		return false, err
	}
	defer tx.Rollback()
	// Serialize observations across batches because same-session cache reuse depends on order.
	if _, err = tx.ExecContext(ctx, "SELECT pg_advisory_xact_lock(hashtext('svix_observation'))"); err != nil {
		return false, err
	}
	var session time.Time
	var finished sql.NullTime
	var status string
	err = tx.QueryRowContext(ctx, "SELECT session_date,finished_at,status FROM market_collection_runs WHERE batch_id=$1", batch).Scan(&session, &finished, &status)
	if err != nil || !finished.Valid || status == "RUNNING" {
		return false, errors.New("completed collection batch required")
	}
	var exists bool
	if err = tx.QueryRowContext(ctx, "SELECT EXISTS(SELECT 1 FROM svix_observations WHERE batch_id=$1 AND method_version=$2)", batch, ObservationMethod).Scan(&exists); err != nil {
		return false, err
	}
	if exists {
		return true, nil
	}
	if err = tx.QueryRowContext(ctx, "SELECT EXISTS(SELECT 1 FROM svix_asset_observations WHERE batch_id=$1 AND method_version=$2)", batch, ObservationMethod).Scan(&exists); err != nil {
		return false, err
	}
	if exists {
		return false, nil
	}
	rows, err := tx.QueryContext(ctx, "SELECT "+quoteColumns+" FROM option_snapshot WHERE batch_id=$1 ORDER BY id", batch)
	if err != nil {
		return false, err
	}
	quotes := map[string][]engine.ObservationQuote{}
	provider := "ALPACA"
	for rows.Next() {
		q, e := scanQuote(rows)
		if e != nil {
			rows.Close()
			return false, e
		}
		provider = q.Provider
		quotes[q.Symbol] = append(quotes[q.Symbol], engine.ObservationQuote{OptionQuote: q.OptionQuote, Feed: strings.ToLower(q.Provider) + ":" + strings.ToLower(q.Feed), PriceType: q.PriceType})
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return false, err
	}
	valuation, sessionDate := finished.Time.UTC(), session.Format("2006-01-02")
	assets, diagnostics := map[string]engine.AssetObservation{}, map[string]engine.AssetObservation{}
	newCount := 0
	weights := engine.Weights()
	for _, symbol := range Universe {
		current := engine.AssetObservation{Status: "NO_BATCH_QUOTES"}
		if len(quotes[symbol]) > 0 {
			var spot *float64
			var tradeTime *time.Time
			e := tx.QueryRowContext(ctx, `SELECT price,trade_timestamp FROM stock_snapshot WHERE batch_id=$1 AND symbol=$2 AND provider=$3 AND price > 0 AND trade_timestamp <= $4 AND trade_timestamp >= $4::timestamptz - interval '15 minutes' ORDER BY id DESC LIMIT 1`, batch, symbol, provider, valuation).Scan(&spot, &tradeTime)
			if e != nil && e != sql.ErrNoRows {
				return false, e
			}
			current = engine.ObserveAsset(symbol, quotes[symbol], valuation, spot, tradeTime)
		}
		var priorBatch, encoded string
		var priorValuation time.Time
		var oldest sql.NullTime
		e := tx.QueryRowContext(ctx, `SELECT batch_id,valuation_at,oldest_input_at,details FROM svix_asset_observations WHERE symbol=$1 AND session_date=$2 AND method_version=$3 AND status='NEW' AND valuation_at < $4 ORDER BY valuation_at DESC,id DESC LIMIT 1`, symbol, sessionDate, ObservationMethod, valuation).Scan(&priorBatch, &priorValuation, &oldest, &encoded)
		if e != nil && e != sql.ErrNoRows {
			return false, e
		}
		var previous engine.AssetObservation
		hasPrevious := e == nil && decodePriorAsset(encoded, &previous) == nil
		if hasPrevious && current.Status == "NEW" && sameIdentity(current.Identity, previous.Identity) {
			current = engine.AssetObservation{Status: "UNCHANGED_QUOTES"}
		}
		if current.Status == "NEW" {
			newCount++
			current.SourceBatch = batch
			current.SourceValuation = &valuation
		} else if hasPrevious && oldest.Valid && valuation.Sub(priorValuation) >= 0 && valuation.Sub(priorValuation) <= 10*time.Minute && valuation.Sub(oldest.Time) >= 0 && valuation.Sub(oldest.Time) <= 15*time.Minute {
			reason := current.Status
			current = previous
			current.Status = "CACHED"
			current.Reason = &reason
			current.SourceBatch = priorBatch
			current.SourceValuation = &priorValuation
			current.Age = valuation.Sub(oldest.Time).Minutes()
		}
		diagnostics[symbol] = current
		if current.Status == "NEW" || current.Status == "CACHED" {
			assets[symbol] = current
		}
		details, _ := json.Marshal(current)
		_, err = tx.ExecContext(ctx, `INSERT INTO svix_asset_observations(session_date,valuation_at,batch_id,method_version,symbol,volatility,oldest_input_at,newest_input_at,term_method,status,details) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)`, sessionDate, valuation, batch, ObservationMethod, symbol, current.Volatility, current.Oldest, current.Newest, current.TermMethod, current.Status, string(details))
		if err != nil {
			return false, err
		}
	}
	if newCount == 0 {
		_, err = tx.ExecContext(ctx, "UPDATE market_collection_runs SET calculation_status='NO_NEW_DATA' WHERE batch_id=$1", batch)
		if err != nil {
			return false, err
		}
		return false, tx.Commit()
	}
	values := map[string]*float64{}
	reasons, matrixDates, counts, componentStatus := map[string]string{}, map[string]string{}, map[string]string{}, map[string]string{}
	for group, names := range Groups {
		value, day, reason, e := s.observeComponent(ctx, tx, provider, sessionDate, valuation, names, assets)
		if e != nil {
			return false, e
		}
		values[group] = value
		if day != nil {
			matrixDates[group] = *day
		}
		if reason != "" {
			reasons[group] = reason
		}
		count := 0
		for _, name := range names {
			if _, ok := assets[name]; ok {
				count++
			}
		}
		counts[group] = fmt.Sprintf("%d/%d", count, len(names))
	}
	coverage, cached := 0.0, 0.0
	hasOld, indicative := false, false
	var oldest *time.Time
	var feed *string
	for symbol, a := range assets {
		coverage += weights[symbol]
		if a.Status == "CACHED" {
			cached += weights[symbol]
		}
		if a.Age > 5 {
			hasOld = true
		}
		if a.Feed != nil && strings.HasSuffix(*a.Feed, ":indicative") {
			indicative = true
		}
		if a.Oldest != nil && (oldest == nil || a.Oldest.Before(*oldest)) {
			oldest = a.Oldest
		}
	}
	// Stable source selection follows the universe order used by the reference implementation.
	for _, name := range Universe {
		if a, ok := assets[name]; ok && a.Feed != nil {
			feed = a.Feed
			break
		}
	}
	if _, ok := assets["SOXX"]; !ok {
		reasons["svix"] = "SOXX_UNAVAILABLE"
	} else if coverage+1e-12 < 0.7 {
		reasons["svix"] = "INSUFFICIENT_COVERAGE"
	} else {
		v, day, reason, e := s.observeComponent(ctx, tx, provider, sessionDate, valuation, Universe, assets)
		if e != nil {
			return false, e
		}
		values["svix"] = v
		if day != nil {
			matrixDates["svix"] = *day
		}
		if reason != "" {
			reasons["svix"] = reason
		}
	}
	finalStatus := "ESTIMATE"
	switch {
	case cached > 0:
		finalStatus = "CACHED"
	case hasOld:
		finalStatus = "OLD_QUOTES"
	case coverage < 1:
		finalStatus = "PARTIAL_COVERAGE"
	case indicative:
		finalStatus = "FREE_ESTIMATE"
	}
	validCount := 0
	partial := false
	for _, name := range []string{"svix", "core", "memory", "ai"} {
		if values[name] != nil {
			validCount++
			componentStatus[name] = "AVAILABLE"
		} else {
			partial = true
			reason := reasons[name]
			if reason == "" {
				reason = "NO_VALID_DATA"
			}
			componentStatus[name] = reason
		}
	}
	if validCount == 0 {
		finalStatus = "NO_VALID_DATA"
	}
	actualWeights := map[string]float64{}
	for name := range assets {
		actualWeights[name] = weights[name] / coverage
	}
	details, _ := json.Marshal(map[string]any{"assets": diagnostics, "component_counts": counts, "component_status": componentStatus, "actual_weights": actualWeights, "reasons": reasons, "matrix_dates": matrixDates, "oldest_input_at": oldest, "new_count": newCount, "rules": map[string]any{"method_version": ObservationMethod, "fresh_minutes": 5, "max_quote_minutes": 15, "max_cache_minutes": 10, "min_coverage": 0.7, "max_single_expiry_distance_days": 7.0, "max_correlation_trading_days": 5}})
	_, err = tx.ExecContext(ctx, `INSERT INTO svix_observations(session_date,valuation_at,batch_id,method_version,svix,core,memory,ai,status,coverage,cached_coverage,source_feed,details) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)`, sessionDate, valuation, batch, ObservationMethod, values["svix"], values["core"], values["memory"], values["ai"], finalStatus, coverage, cached, feed, string(details))
	if err != nil {
		return false, err
	}
	calculationStatus := "COMPLETED"
	if partial {
		calculationStatus = "PARTIAL"
	}
	_, err = tx.ExecContext(ctx, "UPDATE market_collection_runs SET calculation_status=$1 WHERE batch_id=$2", calculationStatus, batch)
	if err != nil {
		return false, err
	}
	return true, tx.Commit()
}
func sameIdentity(a, b [][]string) bool {
	normalize := func(input [][]string) [][]string {
		out := make([][]string, 0, len(input))
		for _, item := range input {
			if len(item) != 2 {
				continue
			}
			stamp := item[1]
			if t, err := time.Parse(time.RFC3339Nano, stamp); err == nil {
				stamp = t.UTC().Format(time.RFC3339Nano)
			}
			out = append(out, []string{item[0], stamp})
		}
		sort.Slice(out, func(i, j int) bool { return strings.Join(out[i], "\x00") < strings.Join(out[j], "\x00") })
		return out
	}
	return reflect.DeepEqual(normalize(a), normalize(b))
}

// Python's default datetime serializer used a space between date and time.
func decodePriorAsset(encoded string, target *engine.AssetObservation) error {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal([]byte(encoded), &fields); err != nil {
		return err
	}
	for _, name := range []string{"oldest_input_at", "newest_input_at", "spot_timestamp", "source_valuation_at"} {
		var value string
		if json.Unmarshal(fields[name], &value) == nil && len(value) > 10 && value[10] == ' ' {
			value = value[:10] + "T" + value[11:]
			fields[name], _ = json.Marshal(value)
		}
	}
	normalized, err := json.Marshal(fields)
	if err != nil {
		return err
	}
	return json.Unmarshal(normalized, target)
}
