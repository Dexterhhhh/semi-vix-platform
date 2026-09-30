package alpaca

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestParseOCC(t *testing.T) {
	contract, err := ParseOCC("AAPL261016C00150000")
	if err != nil || contract.Symbol != "AAPL" || contract.Strike != 150 || contract.OptionType != "C" || contract.Expiry.Day() != 16 {
		t.Fatalf("parsed contract: %+v %v", contract, err)
	}
	if _, err := ParseOCC("bad"); err == nil {
		t.Fatal("invalid symbol accepted")
	}
}

func TestMissingQuoteValuesRemainMissing(t *testing.T) {
	for _, encoded := range []json.RawMessage{nil, json.RawMessage("null"), json.RawMessage("-1")} {
		if optionalFloat(encoded) != nil || optionalInt(encoded) != nil {
			t.Fatalf("missing/invalid value became a zero quote: %s", encoded)
		}
	}
	if v := optionalFloat(json.RawMessage("0")); v == nil || *v != 0 {
		t.Fatal("zero bid must be retained for wing cutoff")
	}
}

func TestSnapshotUsesCachedOptionQuotes(t *testing.T) {
	now := time.Date(2026, 9, 30, 14, 0, 0, 0, time.UTC)
	requests := 0
	transport := roundTripFunc(func(r *http.Request) (*http.Response, error) {
		requests++
		if r.Header.Get("APCA-API-KEY-ID") != "key" || r.Header.Get("APCA-API-SECRET-KEY") != "secret" {
			t.Error("missing credentials")
		}
		var body string
		if r.URL.Path == "/v2/stocks/AAPL/snapshot" {
			body = `{"latestTrade":{"p":150,"t":"2026-09-30T14:00:00Z"},"latestQuote":{"bp":149.9,"ap":150.1,"t":"2026-09-30T14:00:00Z"}}`
		}
		if r.URL.Path == "/v1beta1/options/snapshots/AAPL" {
			encoded, _ := json.Marshal(map[string]any{"snapshots": map[string]any{"AAPL261030C00150000": map[string]any{"latestQuote": map[string]any{"bp": 2.0, "ap": 2.2, "t": "2026-09-30T14:00:00Z"}}}})
			body = string(encoded)
		}
		if body == "" {
			t.Errorf("unexpected request: %s", r.URL.Path)
			return &http.Response{StatusCode: 404, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(""))}, nil
		}
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": {"application/json"}}, Body: io.NopCloser(strings.NewReader(body))}, nil
	})
	client, err := NewClient(Credentials{APIKey: "key", Secret: "secret", Feed: "indicative", BaseURL: "https://example.test"})
	if err != nil {
		t.Fatal(err)
	}
	client.http.Transport = transport
	result, err := client.Snapshot(context.Background(), "AAPL", 120, now)
	if err != nil || result.Stock == nil || len(result.Options) != 1 || requests != 2 {
		t.Fatalf("snapshot: %+v, requests=%d, err=%v", result, requests, err)
	}
	if result.Options[0].ContractID != "ALPACA:AAPL261030C00150000" || !result.Options[0].Delayed {
		t.Fatalf("option normalization: %+v", result.Options[0])
	}
}

func TestHistoricalMarketEndpoints(t *testing.T) {
	client, err := NewClient(Credentials{APIKey: "key", Secret: "secret", Feed: "indicative", BaseURL: "https://data.test"})
	if err != nil {
		t.Fatal(err)
	}
	requests := map[string]int{}
	client.http.Transport = roundTripFunc(func(r *http.Request) (*http.Response, error) {
		requests[r.URL.Path]++
		var body string
		switch r.URL.Path {
		case "/v2/stocks/bars":
			if r.URL.Query().Get("feed") != "iex" || r.URL.Query().Get("adjustment") != "all" {
				t.Error("stock history query differs from existing provider")
			}
			body = `{"bars":{"AAPL":[{"t":"2025-01-02T21:00:00Z","c":150,"v":10}]}}`
		case "/v2/options/contracts":
			body = `{"option_contracts":[{"symbol":"AAPL250221C00150000"},{"symbol":"AAPL250221P00150000"}]}`
		case "/v1beta1/options/bars":
			if r.URL.Query().Has("feed") {
				t.Error("option-bars request must omit indicative feed")
			}
			body = `{"bars":{"AAPL250221C00150000":[{"t":"2025-01-02T21:00:00Z","c":2.5,"v":20}]}}`
		default:
			t.Errorf("unexpected endpoint %s", r.URL.Path)
			body = `{}`
		}
		return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(body))}, nil
	})
	start := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	bars, err := client.stockBars(context.Background(), []string{"AAPL"}, start, start.AddDate(0, 0, 31))
	if err != nil || len(bars["AAPL"]) != 1 {
		t.Fatalf("stock bars: %+v %v", bars, err)
	}
	codes, err := client.contracts(context.Background(), "AAPL", start, start.AddDate(0, 0, 60), 150, "https://paper.test")
	if err != nil || len(codes) != 2 {
		t.Fatalf("contracts: %+v %v", codes, err)
	}
	options, err := client.optionBars(context.Background(), codes, start, start.AddDate(0, 0, 31))
	if err != nil || len(options["AAPL250221C00150000"]) != 1 || requests["/v2/options/contracts"] != 2 {
		t.Fatalf("option history: %+v %v, requests=%+v", options, err, requests)
	}
}
