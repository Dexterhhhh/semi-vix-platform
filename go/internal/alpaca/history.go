package alpaca

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/url"
	"sort"
	"strings"
	"time"

	_ "github.com/lib/pq"
)

type Bar struct {
	Timestamp string  `json:"t"`
	Close     float64 `json:"c"`
	Volume    int64   `json:"v"`
}

type BackfillSummary struct {
	StockRows  int `json:"stock_rows"`
	OptionRows int `json:"option_rows"`
}

func utcMidnight(day time.Time) string { return day.UTC().Format("2006-01-02T15:04:05Z") }

func dateOnly(day time.Time) time.Time {
	return time.Date(day.Year(), day.Month(), day.Day(), 0, 0, 0, 0, time.UTC)
}

func parseBarTime(value string) (time.Time, error) {
	return time.Parse(time.RFC3339Nano, value)
}

func finitePositive(value float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0) && value > 0
}

func (c *Client) getRetry(ctx context.Context, baseURL, path string, params url.Values) (map[string]json.RawMessage, error) {
	var last error
	for attempt := 0; attempt < 6; attempt++ {
		result, err := c.getAt(ctx, baseURL, path, params)
		if err == nil {
			return result, nil
		}
		last = err
		if strings.Contains(err.Error(), "credentials or market-data") {
			return nil, err
		}
		pause := time.Duration(1<<min(attempt, 4)) * time.Second
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(pause):
		}
	}
	return nil, last
}

func (c *Client) stockBars(ctx context.Context, symbols []string, start, end time.Time) (map[string][]Bar, error) {
	feed := "iex"
	if c.credentials.Feed == "opra" {
		feed = "sip"
	}
	params := url.Values{"symbols": {strings.Join(symbols, ",")}, "timeframe": {"1Day"},
		"start": {utcMidnight(start)}, "end": {utcMidnight(end.AddDate(0, 0, 1))},
		"feed": {feed}, "adjustment": {"all"}, "limit": {"10000"}}
	collected := map[string][]Bar{}
	for page := 0; page < 100; page++ {
		payload, err := c.getRetry(ctx, c.credentials.BaseURL, "/v2/stocks/bars", params)
		if err != nil {
			return nil, err
		}
		var bars map[string][]Bar
		if err := json.Unmarshal(payload["bars"], &bars); err != nil {
			return nil, errors.New("invalid Alpaca stock bars")
		}
		for symbol, rows := range bars {
			collected[symbol] = append(collected[symbol], rows...)
		}
		var next string
		_ = json.Unmarshal(payload["next_page_token"], &next)
		if next == "" {
			return collected, nil
		}
		params.Set("page_token", next)
	}
	return nil, errors.New("Alpaca stock pagination limit exceeded")
}

func (c *Client) contracts(ctx context.Context, symbol string, start, end time.Time, reference float64, contractBase string) ([]string, error) {
	contracts := map[string]bool{}
	for _, status := range []string{"active", "inactive"} {
		params := url.Values{"underlying_symbols": {symbol}, "status": {status},
			"expiration_date_gte": {start.Format("2006-01-02")}, "expiration_date_lte": {end.Format("2006-01-02")},
			"strike_price_gte": {fmt.Sprintf("%.2f", math.Round(reference*50)/100)},
			"strike_price_lte": {fmt.Sprintf("%.2f", math.Round(reference*150)/100)}, "limit": {"10000"}}
		for page := 0; page < 20; page++ {
			payload, err := c.getRetry(ctx, contractBase, "/v2/options/contracts", params)
			if err != nil {
				return nil, err
			}
			var rows []struct {
				Symbol string `json:"symbol"`
			}
			if err := json.Unmarshal(payload["option_contracts"], &rows); err != nil && string(payload["option_contracts"]) != "null" {
				return nil, errors.New("invalid Alpaca contract list")
			}
			for _, row := range rows {
				if row.Symbol != "" {
					contracts[row.Symbol] = true
				}
			}
			var next string
			_ = json.Unmarshal(payload["next_page_token"], &next)
			if next == "" {
				_ = json.Unmarshal(payload["page_token"], &next)
			}
			if next == "" {
				break
			}
			params.Set("page_token", next)
		}
	}
	byExpiry := map[time.Time]map[float64][]string{}
	for code := range contracts {
		parsed, err := ParseOCC(code)
		if err != nil || parsed.Symbol != symbol {
			continue
		}
		day := dateOnly(parsed.Expiry)
		if byExpiry[day] == nil {
			byExpiry[day] = map[float64][]string{}
		}
		byExpiry[day][parsed.Strike] = append(byExpiry[day][parsed.Strike], code)
	}
	days := make([]time.Time, 0, len(byExpiry))
	for day := range byExpiry {
		days = append(days, day)
	}
	sort.Slice(days, func(i, j int) bool { return days[i].Before(days[j]) })
	selected := []string{}
	for _, day := range days {
		strikes := make([]float64, 0, len(byExpiry[day]))
		for strike := range byExpiry[day] {
			strikes = append(strikes, strike)
		}
		sort.Slice(strikes, func(i, j int) bool { return math.Abs(strikes[i]-reference) < math.Abs(strikes[j]-reference) })
		if len(strikes) > 40 {
			strikes = strikes[:40]
		}
		for _, strike := range strikes {
			codes := byExpiry[day][strike]
			sort.Strings(codes)
			selected = append(selected, codes...)
		}
	}
	return selected, nil
}

func (c *Client) optionBars(ctx context.Context, codes []string, start, end time.Time) (map[string][]Bar, error) {
	collected := map[string][]Bar{}
	for index := 0; index < len(codes); index += 100 {
		stop := min(index+100, len(codes))
		params := url.Values{"symbols": {strings.Join(codes[index:stop], ",")}, "timeframe": {"1Day"},
			"start": {utcMidnight(start)}, "end": {utcMidnight(end.AddDate(0, 0, 1))}, "limit": {"10000"}}
		for page := 0; page < 100; page++ {
			payload, err := c.getRetry(ctx, c.credentials.BaseURL, "/v1beta1/options/bars", params)
			if err != nil {
				return nil, err
			}
			var bars map[string][]Bar
			if err := json.Unmarshal(payload["bars"], &bars); err != nil {
				return nil, errors.New("invalid Alpaca option bars")
			}
			for symbol, rows := range bars {
				collected[symbol] = append(collected[symbol], rows...)
			}
			var next string
			_ = json.Unmarshal(payload["next_page_token"], &next)
			if next == "" {
				break
			}
			params.Set("page_token", next)
		}
	}
	return collected, nil
}

func saveStocks(ctx context.Context, db *sql.DB, bars map[string][]Bar, feed string) (map[string]map[time.Time]float64, error) {
	prices := map[string]map[time.Time]float64{}
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer tx.Rollback()
	for symbol, rows := range bars {
		prices[symbol] = map[time.Time]float64{}
		for _, bar := range rows {
			if !finitePositive(bar.Close) {
				continue
			}
			at, err := parseBarTime(bar.Timestamp)
			if err != nil {
				continue
			}
			prices[symbol][dateOnly(at)] = bar.Close
			_, err = tx.ExecContext(ctx, `INSERT INTO stock_snapshot
                (timestamp,provider,symbol,price,volume,delayed,feed,price_type,received_at)
				SELECT $1::timestamptz,'ALPACA',$2::varchar(16),$3::double precision,$4::integer,true,$5::varchar(32),'adjusted_close',now()
				WHERE NOT EXISTS (SELECT 1 FROM stock_snapshot WHERE provider='ALPACA' AND symbol=$2::varchar(16) AND timestamp=$1::timestamptz)`,
				at, symbol, bar.Close, bar.Volume, feed)
			if err != nil {
				return nil, err
			}
		}
	}
	return prices, tx.Commit()
}

func saveOptions(ctx context.Context, db *sql.DB, symbol string, bars map[string][]Bar) (int, error) {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()
	count := 0
	for code, rows := range bars {
		contract, err := ParseOCC(code)
		if err != nil || contract.Symbol != symbol {
			continue
		}
		for _, bar := range rows {
			if !finitePositive(bar.Close) {
				continue
			}
			at, err := parseBarTime(bar.Timestamp)
			if err != nil {
				continue
			}
			result, err := tx.ExecContext(ctx, `INSERT INTO option_snapshot
                (timestamp,provider,contract_id,symbol,expiry,strike,option_type,bid,ask,last,volume,delayed,feed,price_type,received_at)
				SELECT $1::timestamptz,'ALPACA',$2::varchar(256),$3::varchar(16),$4::timestamptz,$5::double precision,$6::varchar(4),$7::double precision,$7::double precision,$7::double precision,$8::integer,true,'historical','trade_close_proxy',now()
				WHERE NOT EXISTS (SELECT 1 FROM option_snapshot WHERE provider='ALPACA' AND contract_id=$2::varchar(256) AND timestamp=$1::timestamptz)`,
				at, "ALPACA:"+code, symbol, contract.Expiry, contract.Strike, contract.OptionType, bar.Close, bar.Volume)
			if err != nil {
				return 0, err
			}
			affected, _ := result.RowsAffected()
			count += int(affected)
		}
	}
	return count, tx.Commit()
}

// Backfill downloads completed daily bars and stores them with the existing
// adjusted-close and trade-close-proxy provenance used by historical SVIX.
func (c *Client) Backfill(ctx context.Context, db *sql.DB, start, end time.Time, symbols []string, contractBase string) (BackfillSummary, error) {
	var summary BackfillSummary
	lockConnection, err := db.Conn(ctx)
	if err != nil {
		return summary, err
	}
	defer lockConnection.Close()
	if _, err := lockConnection.ExecContext(ctx, "SELECT pg_advisory_lock(hashtext('svix_alpaca_backfill'))"); err != nil {
		return summary, err
	}
	defer lockConnection.ExecContext(context.Background(), "SELECT pg_advisory_unlock(hashtext('svix_alpaca_backfill'))")
	start, end = dateOnly(start), dateOnly(end)
	latest := dateOnly(time.Now().UTC()).AddDate(0, 0, -1)
	if end.After(latest) {
		end = latest
	}
	if end.Before(start) {
		return summary, nil
	}
	if contractBase == "" {
		contractBase = "https://paper-api.alpaca.markets"
	}
	bars, err := c.stockBars(ctx, symbols, start.AddDate(0, 0, -420), end)
	if err != nil {
		return summary, err
	}
	for _, rows := range bars {
		summary.StockRows += len(rows)
	}
	feed := "iex"
	if c.credentials.Feed == "opra" {
		feed = "sip"
	}
	prices, err := saveStocks(ctx, db, bars, feed)
	if err != nil {
		return summary, err
	}
	for month := time.Date(start.Year(), start.Month(), 1, 0, 0, 0, 0, time.UTC); !month.After(end); month = month.AddDate(0, 1, 0) {
		monthEnd := month.AddDate(0, 1, -1)
		windowStart, windowEnd := month, monthEnd
		if windowStart.Before(start) {
			windowStart = start
		}
		if windowEnd.After(end) {
			windowEnd = end
		}
		for _, symbol := range symbols {
			monthPrices := []float64{}
			for day, price := range prices[symbol] {
				if !day.Before(windowStart) && !day.After(windowEnd) {
					monthPrices = append(monthPrices, price)
				}
			}
			if len(monthPrices) == 0 {
				continue
			}
			sort.Float64s(monthPrices)
			reference := monthPrices[len(monthPrices)/2]
			codes, err := c.contracts(ctx, symbol, windowStart.AddDate(0, 0, 20), windowEnd.AddDate(0, 0, 45), reference, contractBase)
			if err != nil {
				return summary, err
			}
			if len(codes) == 0 {
				continue
			}
			optionBars, err := c.optionBars(ctx, codes, windowStart, windowEnd)
			if err != nil {
				return summary, err
			}
			written, err := saveOptions(ctx, db, symbol, optionBars)
			if err != nil {
				return summary, err
			}
			summary.OptionRows += written
		}
	}
	return summary, nil
}
