package engine

import (
	"math"
	"testing"
	"time"
)

func TestFullSVIXMatchesPythonReference(t *testing.T) {
	valuation := time.Date(2026, 1, 2, 16, 0, 0, 0, time.UTC)
	symbols := []string{"SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO"}
	strikes := []float64{90, 90, 100, 100, 110, 110}
	kinds := []string{"C", "P", "C", "P", "C", "P"}
	bids := []float64{10.5, 0.8, 5.8, 3.8, 0.8, 10.5}
	asks := []float64{11.5, 1.2, 6.2, 4.2, 1.2, 11.5}
	input := SVIXInput{ValuationAt: valuation, TargetDays: 30, Quotes: map[string][]OptionQuote{}, Returns: map[string][]float64{}}
	for symbolIndex, symbol := range symbols {
		for _, term := range []struct {
			days  int
			scale float64
		}{{20, 1}, {40, 1.2}} {
			expiry := valuation.Add(time.Duration(term.days) * 24 * time.Hour)
			for index := range strikes {
				bid, ask := bids[index]*term.scale, asks[index]*term.scale
				input.Quotes[symbol] = append(input.Quotes[symbol], OptionQuote{
					ContractID: symbol, Symbol: symbol, Expiry: expiry, Strike: strikes[index],
					OptionType: kinds[index], Bid: &bid, Ask: &ask, Timestamp: valuation,
				})
			}
		}
		for index := 0; index < 260; index++ {
			input.Returns[symbol] = append(input.Returns[symbol], 0.001*math.Sin(float64(index)/float64(symbolIndex+2))+0.0001*float64(symbolIndex))
		}
	}
	result, err := CalculateSVIX(input)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(result.SVIX-24.22658593637076) > 1e-8 ||
		math.Abs(result.CoreVol-42.78580133770128) > 1e-8 ||
		math.Abs(result.MemoryVol-32.24598415967619) > 1e-8 ||
		math.Abs(result.AIVol-30.395180845213364) > 1e-8 {
		t.Fatalf("full calculation differs from Python reference: %+v", result)
	}
}
