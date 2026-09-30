package engine

import (
	"errors"
	"math"
	"sort"
	"time"
)

var baseWeights = map[string]float64{
	"SOXX": 0.50, "MU": 0.15, "SKHY": 0.15,
	"NVDA": 0.10, "AMD": 0.05, "AVGO": 0.05,
}

type SVIXInput struct {
	Quotes         map[string][]OptionQuote `json:"option_quotes"`
	Returns        map[string][]float64     `json:"historical_returns"`
	ValuationAt    time.Time                `json:"valuation_at"`
	SpotPrices     map[string]float64       `json:"underlying_prices"`
	SOXXExposure   map[string]float64       `json:"soxx_constituent_exposure"`
	Approximate    bool                     `json:"approximate"`
	SourceFeed     *string                  `json:"source_feed"`
	MarketQuality  string                   `json:"market_data_quality"`
	RiskFreeRate   float64                  `json:"risk_free_rate"`
	TargetDays     int                      `json:"target_days"`
	AllowLastPrice bool                     `json:"allow_last_price_fallback"`
}

type SVIXResult struct {
	Timestamp          time.Time          `json:"timestamp"`
	SVIX               float64            `json:"svix"`
	CoreVol            float64            `json:"core_vol"`
	MemoryVol          float64            `json:"memory_vol"`
	AIVol              float64            `json:"ai_vol"`
	Weights            map[string]float64 `json:"weights"`
	CorrelationMatrix  [][]float64        `json:"correlation_matrix"`
	CalculationQuality float64            `json:"calculation_quality"`
	Estimated          bool               `json:"estimated"`
	SourceFeed         *string            `json:"source_feed"`
	CalculationMethod  string             `json:"calculation_method"`
	MarketDataQuality  string             `json:"market_data_quality"`
}

type assetTerm struct {
	volatility float64
	quality    float64
}

func varianceQuality(value VarianceResult) float64 {
	quality := value.QualityMetrics["forward_quality"] * (1 - 0.2*value.QualityMetrics["k0_fallback"])
	if value.QualityMetrics["spot_forward"] > 0 {
		quality *= 0.7
	}
	if value.QualityMetrics["uncorrected_variance"] > 0 {
		quality *= 0.5
	}
	return quality
}

func assetVariance(symbol string, quotes []OptionQuote, input SVIXInput) (assetTerm, error) {
	byExpiry := map[time.Time][]OptionQuote{}
	for _, quote := range quotes {
		if quote.Symbol == symbol {
			byExpiry[quote.Expiry] = append(byExpiry[quote.Expiry], quote)
		}
	}
	results := make([]VarianceResult, 0, len(byExpiry))
	for expiry, chain := range byExpiry {
		var fallback *float64
		if input.Approximate {
			if spot := input.SpotPrices[symbol]; spot > 0 {
				fallback = &spot
			}
		}
		result, err := ExpiryVariance(symbol, expiry, input.ValuationAt, chain,
			input.RiskFreeRate, input.AllowLastPrice || input.Approximate, fallback)
		if err == nil {
			results = append(results, result)
		}
	}
	if len(results) == 0 {
		return assetTerm{}, errors.New("no valid expiry")
	}
	sort.Slice(results, func(i, j int) bool { return results[i].DaysToExpiry < results[j].DaysToExpiry })
	target := float64(input.TargetDays)
	for _, result := range results {
		if math.Abs(result.DaysToExpiry-target) <= 1e-9 {
			return assetTerm{volatility: math.Sqrt(result.Variance), quality: varianceQuality(result)}, nil
		}
	}
	var near, far *VarianceResult
	for i := range results {
		if results[i].DaysToExpiry < target {
			near = &results[i]
		} else if far == nil {
			far = &results[i]
		}
	}
	if near == nil || far == nil {
		if !input.Approximate {
			return assetTerm{}, errors.New("target expiry is not bracketed")
		}
		nearest := results[0]
		for _, result := range results[1:] {
			if math.Abs(result.DaysToExpiry-target) < math.Abs(nearest.DaysToExpiry-target) {
				nearest = result
			}
		}
		if math.Abs(nearest.DaysToExpiry-target) > 7 {
			return assetTerm{}, errors.New("nearest expiry more than seven days from target")
		}
		return assetTerm{volatility: math.Sqrt(nearest.Variance), quality: varianceQuality(nearest) * 0.45}, nil
	}
	variance, err := Interpolate(near.DaysToExpiry, near.Variance, far.DaysToExpiry, far.Variance, target)
	if err != nil {
		return assetTerm{}, err
	}
	weightNear := (far.DaysToExpiry - target) / (far.DaysToExpiry - near.DaysToExpiry)
	return assetTerm{volatility: math.Sqrt(variance), quality: weightNear*varianceQuality(*near) + (1-weightNear)*varianceQuality(*far)}, nil
}

func normalized(weights map[string]float64) (map[string]float64, error) {
	total := 0.0
	for _, weight := range weights {
		total += weight
	}
	if !finitePositive(total) {
		return nil, errors.New("no positive component weight")
	}
	result := make(map[string]float64, len(weights))
	for symbol, weight := range weights {
		result[symbol] = weight / total
	}
	return result, nil
}

func subsetReturns(symbols []string, returns map[string][]float64) map[string][]float64 {
	selected := make(map[string][]float64, len(symbols))
	for _, symbol := range symbols {
		selected[symbol] = returns[symbol]
	}
	return selected
}

func component(symbols []string, weights, vols map[string]float64, returns map[string][]float64) (float64, error) {
	available := make([]string, 0, len(symbols))
	selectedWeights := map[string]float64{}
	selectedVols := map[string]float64{}
	for _, symbol := range symbols {
		if weight, ok := weights[symbol]; ok {
			available = append(available, symbol)
			selectedWeights[symbol] = weight
			selectedVols[symbol] = vols[symbol]
		}
	}
	if len(available) == 0 {
		return 0, errors.New("missing component")
	}
	if len(available) == 1 {
		return vols[available[0]], nil
	}
	selectedWeights, err := normalized(selectedWeights)
	if err != nil {
		return 0, err
	}
	correlation, err := Correlation(subsetReturns(available, returns))
	if err != nil {
		return 0, err
	}
	portfolio, err := Portfolio(selectedWeights, selectedVols, correlation)
	return portfolio.Volatility, err
}

// CalculateSVIX executes the full provider-independent SVIX math in Go.
func CalculateSVIX(input SVIXInput) (SVIXResult, error) {
	var empty SVIXResult
	if input.ValuationAt.IsZero() {
		return empty, errors.New("valuation_at is required")
	}
	if input.TargetDays == 0 {
		input.TargetDays = 30
	}
	terms := map[string]assetTerm{}
	for symbol := range baseWeights {
		quotes, hasQuotes := input.Quotes[symbol]
		_, hasReturns := input.Returns[symbol]
		if !hasQuotes || !hasReturns {
			continue
		}
		term, err := assetVariance(symbol, quotes, input)
		if err != nil {
			if !input.Approximate {
				return empty, err
			}
			continue
		}
		terms[symbol] = term
	}
	if _, ok := terms["SOXX"]; !ok {
		return empty, errors.New("core component unavailable")
	}
	if _, mu := terms["MU"]; !mu {
		if _, skhy := terms["SKHY"]; !skhy {
			return empty, errors.New("memory component unavailable")
		}
	}
	if _, nvda := terms["NVDA"]; !nvda {
		if _, amd := terms["AMD"]; !amd {
			if _, avgo := terms["AVGO"]; !avgo {
				return empty, errors.New("AI component unavailable")
			}
		}
	}
	selected := map[string]float64{}
	coverage := 0.0
	vols := map[string]float64{}
	quality := 1.0
	for symbol, term := range terms {
		selected[symbol] = baseWeights[symbol]
		coverage += baseWeights[symbol]
		vols[symbol] = term.volatility
		quality = math.Min(quality, term.quality)
	}
	weights, err := normalized(selected)
	if err != nil {
		return empty, err
	}
	if etfWeight, present := weights["SOXX"]; present && len(input.SOXXExposure) > 0 {
		for symbol, exposure := range input.SOXXExposure {
			if symbol == "SOXX" {
				continue
			}
			if weight, exists := weights[symbol]; exists {
				weights[symbol] -= math.Min(weight, math.Max(0, etfWeight*exposure))
			}
		}
		weights, err = normalized(weights)
		if err != nil {
			return empty, err
		}
	}
	assets := make([]string, 0, len(weights))
	for symbol := range weights {
		assets = append(assets, symbol)
	}
	correlation, err := Correlation(subsetReturns(assets, input.Returns))
	if err != nil {
		return empty, err
	}
	portfolio, err := Portfolio(weights, vols, correlation)
	if err != nil {
		return empty, err
	}
	memory, err := component([]string{"MU", "SKHY"}, weights, vols, input.Returns)
	if err != nil {
		return empty, err
	}
	ai, err := component([]string{"NVDA", "AMD", "AVGO"}, weights, vols, input.Returns)
	if err != nil {
		return empty, err
	}
	for symbol := range terms {
		for _, quote := range input.Quotes[symbol] {
			if quote.Delayed != nil && *quote.Delayed {
				quality *= 0.65
				goto qualityDone
			}
		}
	}
qualityDone:
	quality *= coverage
	method := "svix-v2-cumulative-variance"
	if input.Approximate {
		method = "svix-v2-proxy-estimate"
	}
	marketQuality := input.MarketQuality
	if marketQuality == "" {
		marketQuality = "unknown"
	}
	return SVIXResult{Timestamp: input.ValuationAt, SVIX: portfolio.Volatility * 100,
		CoreVol: vols["SOXX"] * 100, MemoryVol: memory * 100, AIVol: ai * 100,
		Weights: weights, CorrelationMatrix: correlation.Matrix, CalculationQuality: quality,
		Estimated: input.Approximate, SourceFeed: input.SourceFeed,
		CalculationMethod: method, MarketDataQuality: marketQuality}, nil
}
