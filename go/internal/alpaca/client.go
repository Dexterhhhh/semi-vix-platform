package alpaca

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

var occSymbol = regexp.MustCompile(`^([A-Z0-9.]{1,6})(\d{6})([CP])(\d{8})$`)

type Credentials struct {
	APIKey  string `json:"api_key"`
	Secret  string `json:"secret"`
	Feed    string `json:"feed"`
	BaseURL string `json:"base_url"`
}

type Contract struct {
	Code       string    `json:"code"`
	Symbol     string    `json:"symbol"`
	Expiry     time.Time `json:"expiry"`
	Strike     float64   `json:"strike"`
	OptionType string    `json:"option_type"`
}

type StockQuote struct {
	Symbol         string     `json:"symbol"`
	Timestamp      time.Time  `json:"timestamp"`
	Price          *float64   `json:"price"`
	Bid            *float64   `json:"bid"`
	Ask            *float64   `json:"ask"`
	Volume         *int64     `json:"volume"`
	TradeTimestamp *time.Time `json:"trade_timestamp"`
	Feed           string     `json:"feed"`
	PriceType      string     `json:"price_type"`
	Delayed        bool       `json:"delayed"`
}

type OptionQuote struct {
	ContractID     string     `json:"contract_id"`
	Symbol         string     `json:"symbol"`
	Expiry         time.Time  `json:"expiry"`
	Strike         float64    `json:"strike"`
	OptionType     string     `json:"option_type"`
	Timestamp      time.Time  `json:"timestamp"`
	Bid            *float64   `json:"bid"`
	Ask            *float64   `json:"ask"`
	Last           *float64   `json:"last"`
	Volume         *int64     `json:"volume"`
	OpenInterest   *int64     `json:"open_interest"`
	ImpliedVol     *float64   `json:"implied_volatility"`
	TradeTimestamp *time.Time `json:"trade_timestamp"`
	Feed           string     `json:"feed"`
	PriceType      string     `json:"price_type"`
	Delayed        bool       `json:"delayed"`
}

type Snapshot struct {
	Stock   *StockQuote   `json:"stock"`
	Options []OptionQuote `json:"options"`
	Errors  []string      `json:"errors"`
}

type Client struct {
	credentials Credentials
	http        *http.Client
}

func (c *Client) Health(ctx context.Context) error {
	feed := "iex"
	if c.credentials.Feed == "opra" {
		feed = "sip"
	}
	_, err := c.get(ctx, "/v2/stocks/SPY/snapshot", url.Values{"feed": {feed}})
	return err
}

func NewClient(credentials Credentials) (*Client, error) {
	if credentials.APIKey == "" || credentials.Secret == "" {
		return nil, errors.New("Alpaca credentials are required")
	}
	if credentials.Feed == "" {
		credentials.Feed = "indicative"
	}
	if credentials.Feed != "indicative" && credentials.Feed != "opra" {
		return nil, errors.New("invalid Alpaca feed")
	}
	if credentials.BaseURL == "" {
		credentials.BaseURL = "https://data.alpaca.markets"
	}
	parsed, err := url.Parse(credentials.BaseURL)
	if err != nil || parsed.Host == "" || (parsed.Scheme != "https" && parsed.Scheme != "http") {
		return nil, errors.New("invalid Alpaca base URL")
	}
	return &Client{credentials: credentials, http: &http.Client{Timeout: 15 * time.Second}}, nil
}

func (c *Client) get(ctx context.Context, path string, params url.Values) (map[string]json.RawMessage, error) {
	return c.getAt(ctx, c.credentials.BaseURL, path, params)
}

func (c *Client) getAt(ctx context.Context, baseURL, path string, params url.Values) (map[string]json.RawMessage, error) {
	address := strings.TrimRight(baseURL, "/") + path
	if len(params) > 0 {
		address += "?" + params.Encode()
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, address, nil)
	if err != nil {
		return nil, err
	}
	request.Header.Set("APCA-API-KEY-ID", c.credentials.APIKey)
	request.Header.Set("APCA-API-SECRET-KEY", c.credentials.Secret)
	response, err := c.http.Do(request)
	if err != nil {
		return nil, fmt.Errorf("Alpaca request failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode == http.StatusUnauthorized || response.StatusCode == http.StatusForbidden {
		return nil, errors.New("Alpaca credentials or market-data subscription were rejected")
	}
	if response.StatusCode == http.StatusTooManyRequests {
		return nil, errors.New("Alpaca rate limit exceeded")
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, fmt.Errorf("Alpaca returned HTTP %d", response.StatusCode)
	}
	var payload map[string]json.RawMessage
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil || payload == nil {
		return nil, errors.New("invalid Alpaca response")
	}
	return payload, nil
}

func object(value json.RawMessage) map[string]json.RawMessage {
	var result map[string]json.RawMessage
	_ = json.Unmarshal(value, &result)
	return result
}

func optionalFloat(value json.RawMessage) *float64 {
	if len(value) == 0 || strings.TrimSpace(string(value)) == "null" {
		return nil
	}
	var number float64
	if json.Unmarshal(value, &number) != nil || math.IsNaN(number) || math.IsInf(number, 0) || number < 0 {
		return nil
	}
	return &number
}

func optionalInt(value json.RawMessage) *int64 {
	if len(value) == 0 || strings.TrimSpace(string(value)) == "null" {
		return nil
	}
	var number int64
	if json.Unmarshal(value, &number) != nil || number < 0 {
		return nil
	}
	return &number
}

func optionalTime(value json.RawMessage) *time.Time {
	var raw string
	if json.Unmarshal(value, &raw) != nil {
		return nil
	}
	parsed, err := time.Parse(time.RFC3339Nano, raw)
	if err != nil {
		return nil
	}
	parsed = parsed.UTC()
	return &parsed
}

func ParseOCC(symbol string) (Contract, error) {
	symbol = strings.ToUpper(symbol)
	parts := occSymbol.FindStringSubmatch(symbol)
	if parts == nil {
		return Contract{}, errors.New("invalid OCC symbol")
	}
	day, err := time.Parse("060102", parts[2])
	if err != nil {
		return Contract{}, err
	}
	strike, err := strconv.Atoi(parts[4])
	if err != nil {
		return Contract{}, err
	}
	return Contract{Code: symbol, Symbol: parts[1], Expiry: time.Date(day.Year(), day.Month(), day.Day(), 21, 0, 0, 0, time.UTC), Strike: float64(strike) / 1000, OptionType: parts[3]}, nil
}

func (c *Client) Stock(ctx context.Context, symbol string) (StockQuote, error) {
	feed := "iex"
	if c.credentials.Feed == "opra" {
		feed = "sip"
	}
	payload, err := c.get(ctx, "/v2/stocks/"+url.PathEscape(symbol)+"/snapshot", url.Values{"feed": {feed}})
	if err != nil {
		return StockQuote{}, err
	}
	quote, trade, daily := object(payload["latestQuote"]), object(payload["latestTrade"]), object(payload["dailyBar"])
	quotedAt, tradedAt := optionalTime(quote["t"]), optionalTime(trade["t"])
	if quotedAt == nil {
		quotedAt = tradedAt
	}
	if quotedAt == nil {
		return StockQuote{}, errors.New("stock market timestamp is missing")
	}
	bid, ask := optionalFloat(quote["bp"]), optionalFloat(quote["ap"])
	if bid != nil && ask != nil && *bid > *ask {
		bid, ask = nil, nil
	}
	priceType := "bbo"
	if tradedAt != nil {
		priceType = "trade"
	}
	return StockQuote{Symbol: symbol, Timestamp: *quotedAt, Price: optionalFloat(trade["p"]), Bid: bid, Ask: ask, Volume: optionalInt(daily["v"]), TradeTimestamp: tradedAt, Feed: c.credentials.Feed, PriceType: priceType, Delayed: c.credentials.Feed == "indicative"}, nil
}

func selectExpiries(contracts []Contract, now time.Time) []Contract {
	today := now.UTC().Truncate(24 * time.Hour)
	target := today.AddDate(0, 0, 30)
	days := map[time.Time]bool{}
	for _, contract := range contracts {
		day := contract.Expiry.Truncate(24 * time.Hour)
		if day.After(today) {
			days[day] = true
		}
	}
	ordered := make([]time.Time, 0, len(days))
	for day := range days {
		ordered = append(ordered, day)
	}
	sort.Slice(ordered, func(i, j int) bool { return ordered[i].Before(ordered[j]) })
	var lower, upper time.Time
	for _, day := range ordered {
		if !day.After(target) {
			lower = day
		}
		if !day.Before(target) && upper.IsZero() {
			upper = day
		}
	}
	selected := map[time.Time]bool{}
	if !lower.IsZero() {
		selected[lower] = true
	}
	if !upper.IsZero() {
		selected[upper] = true
	}
	if len(selected) < 2 && len(ordered) > 1 {
		sort.Slice(ordered, func(i, j int) bool {
			return math.Abs(ordered[i].Sub(target).Hours()) < math.Abs(ordered[j].Sub(target).Hours())
		})
		selected = map[time.Time]bool{ordered[0]: true, ordered[1]: true}
	}
	result := make([]Contract, 0)
	for _, contract := range contracts {
		if selected[contract.Expiry.Truncate(24*time.Hour)] {
			result = append(result, contract)
		}
	}
	return result
}

func (c *Client) Chain(ctx context.Context, symbol string, referencePrice float64, now time.Time) ([]Contract, map[string]map[string]json.RawMessage, error) {
	today := now.UTC().Truncate(24 * time.Hour)
	params := url.Values{"feed": {c.credentials.Feed}, "limit": {"1000"}, "expiration_date_gte": {today.AddDate(0, 0, 20).Format("2006-01-02")}, "expiration_date_lte": {today.AddDate(0, 0, 45).Format("2006-01-02")}}
	contracts := make([]Contract, 0)
	snapshots := map[string]map[string]json.RawMessage{}
	for page := 0; page < 10; page++ {
		payload, err := c.get(ctx, "/v1beta1/options/snapshots/"+url.PathEscape(symbol), params)
		if err != nil {
			return nil, nil, err
		}
		var raw map[string]json.RawMessage
		if json.Unmarshal(payload["snapshots"], &raw) != nil {
			return nil, nil, errors.New("Alpaca returned an invalid option chain")
		}
		for code, snapshot := range raw {
			contract, err := ParseOCC(code)
			if err != nil || contract.Symbol != symbol {
				continue
			}
			if _, exists := snapshots[code]; !exists {
				contracts = append(contracts, contract)
			}
			snapshots[code] = object(snapshot)
		}
		var next string
		_ = json.Unmarshal(payload["next_page_token"], &next)
		if next == "" {
			break
		}
		params.Set("page_token", next)
	}
	contracts = selectExpiries(contracts, now)
	if referencePrice <= 0 && len(contracts) > 0 {
		strikes := make([]float64, 0, len(contracts))
		for _, contract := range contracts {
			strikes = append(strikes, contract.Strike)
		}
		sort.Float64s(strikes)
		referencePrice = strikes[len(strikes)/2]
	}
	sort.Slice(contracts, func(i, j int) bool {
		a, b := math.Abs(contracts[i].Strike-referencePrice), math.Abs(contracts[j].Strike-referencePrice)
		if a != b {
			return a < b
		}
		if !contracts[i].Expiry.Equal(contracts[j].Expiry) {
			return contracts[i].Expiry.Before(contracts[j].Expiry)
		}
		return contracts[i].OptionType < contracts[j].OptionType
	})
	return contracts, snapshots, nil
}

func SelectContracts(contracts []Contract, reference float64, limit int, now time.Time) []Contract {
	if len(contracts) <= limit {
		return contracts
	}
	contracts = selectExpiries(contracts, now)
	byDay := map[time.Time]map[float64][]Contract{}
	for _, contract := range contracts {
		day := contract.Expiry.Truncate(24 * time.Hour)
		if byDay[day] == nil {
			byDay[day] = map[float64][]Contract{}
		}
		byDay[day][contract.Strike] = append(byDay[day][contract.Strike], contract)
	}
	days := make([]time.Time, 0, len(byDay))
	for day := range byDay {
		days = append(days, day)
	}
	sort.Slice(days, func(i, j int) bool { return days[i].Before(days[j]) })
	strikeBudget := limit / max(2, len(days)*2)
	if strikeBudget < 1 {
		strikeBudget = 1
	}
	result := make([]Contract, 0, limit)
	for _, day := range days {
		strikes := make([]float64, 0, len(byDay[day]))
		for strike := range byDay[day] {
			strikes = append(strikes, strike)
		}
		if reference <= 0 {
			sort.Float64s(strikes)
			reference = strikes[len(strikes)/2]
		}
		sort.Slice(strikes, func(i, j int) bool {
			a, b := math.Abs(strikes[i]-reference), math.Abs(strikes[j]-reference)
			if a != b {
				return a < b
			}
			return strikes[i] < strikes[j]
		})
		if len(strikes) > strikeBudget {
			strikes = strikes[:strikeBudget]
		}
		sort.Float64s(strikes)
		for _, strike := range strikes {
			pair := byDay[day][strike]
			sort.Slice(pair, func(i, j int) bool { return pair[i].OptionType < pair[j].OptionType })
			result = append(result, pair...)
		}
	}
	if len(result) > limit {
		result = result[:limit]
	}
	return result
}

func (c *Client) Quote(contract Contract, snapshot map[string]json.RawMessage) (OptionQuote, error) {
	quote, trade, daily := object(snapshot["latestQuote"]), object(snapshot["latestTrade"]), object(snapshot["dailyBar"])
	quotedAt := optionalTime(quote["t"])
	if quotedAt == nil {
		return OptionQuote{}, errors.New("option quote timestamp is missing")
	}
	priceType := "indicative_quote"
	if c.credentials.Feed == "opra" {
		priceType = "bbo"
	}
	bid, ask := optionalFloat(quote["bp"]), optionalFloat(quote["ap"])
	if bid != nil && ask != nil && *bid > *ask {
		bid, ask = nil, nil
	}
	return OptionQuote{ContractID: "ALPACA:" + contract.Code, Symbol: contract.Symbol, Expiry: contract.Expiry,
		Strike: contract.Strike, OptionType: contract.OptionType, Timestamp: *quotedAt, Bid: bid, Ask: ask,
		Last: optionalFloat(trade["p"]), Volume: optionalInt(daily["v"]), OpenInterest: optionalInt(snapshot["openInterest"]),
		ImpliedVol: optionalFloat(snapshot["impliedVolatility"]), TradeTimestamp: optionalTime(trade["t"]),
		Feed: c.credentials.Feed, PriceType: priceType, Delayed: c.credentials.Feed == "indicative"}, nil
}

func (c *Client) Snapshot(ctx context.Context, symbol string, maxContracts int, now time.Time) (Snapshot, error) {
	if maxContracts < 1 || maxContracts > 1000 {
		return Snapshot{}, errors.New("invalid contract limit")
	}
	symbol = strings.ToUpper(strings.TrimSpace(symbol))
	if symbol == "" || len(symbol) > 16 {
		return Snapshot{}, errors.New("invalid symbol")
	}
	result := Snapshot{Options: []OptionQuote{}, Errors: []string{}}
	stock, err := c.Stock(ctx, symbol)
	reference := 0.0
	if err != nil {
		result.Errors = append(result.Errors, "STOCK_QUOTE_UNAVAILABLE")
	} else {
		result.Stock = &stock
		if stock.Price != nil {
			reference = *stock.Price
		}
	}
	contracts, snapshots, err := c.Chain(ctx, symbol, reference, now)
	if err != nil {
		return result, err
	}
	for _, contract := range SelectContracts(contracts, reference, maxContracts, now) {
		quote, err := c.Quote(contract, snapshots[contract.Code])
		if err != nil {
			result.Errors = append(result.Errors, "OPTION_QUOTE_UNAVAILABLE")
			continue
		}
		result.Options = append(result.Options, quote)
	}
	return result, nil
}
