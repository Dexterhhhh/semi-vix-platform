package engine

import (
	"math"
	"testing"
	"time"
)

func TestExpiryVarianceMatchesReferenceChain(t *testing.T) {
	valuation := time.Date(2026, 1, 2, 16, 0, 0, 0, time.UTC)
	expiry := valuation.Add(30 * 24 * time.Hour)
	quote := func(strike, bid, ask float64, kind string) OptionQuote {
		return OptionQuote{ContractID: kind, Strike: strike, OptionType: kind, Bid: &bid, Ask: &ask, Timestamp: valuation}
	}
	chain := []OptionQuote{
		quote(90, 10.5, 11.5, "C"), quote(90, 0.8, 1.2, "P"),
		quote(100, 5.8, 6.2, "C"), quote(100, 3.8, 4.2, "P"),
		quote(110, 0.8, 1.2, "C"), quote(110, 10.5, 11.5, "P"),
	}
	result, err := ExpiryVariance("NVDA", expiry, valuation, chain, 0, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(result.Variance-0.16695134510084006) > 1e-12 || result.OptionCount != 3 || result.ForwardPrice != 102 {
		t.Fatalf("reference mismatch: %+v", result)
	}
}

func TestExpiryVarianceRejectsUnpairedK0(t *testing.T) {
	valuation := time.Date(2026, 1, 2, 16, 0, 0, 0, time.UTC)
	expiry := valuation.Add(30 * 24 * time.Hour)
	quote := func(strike, bid, ask float64, kind string) OptionQuote {
		return OptionQuote{Strike: strike, OptionType: kind, Bid: &bid, Ask: &ask, Timestamp: valuation}
	}
	chain := []OptionQuote{quote(100, 9.8, 10.2, "C"), quote(100, 3.8, 4.2, "P"), quote(105, 2, 2.2, "P")}
	if _, err := ExpiryVariance("NVDA", expiry, valuation, chain, 0, false, nil); err == nil {
		t.Fatal("expected unpaired K0 rejection")
	}
}
