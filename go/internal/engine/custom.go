package engine

import (
	"errors"
	"math"
)

type CustomResult struct {
	Value   float64
	Quality float64
}

func CalculateCustom(input SVIXInput, weights map[string]float64, policy string) (CustomResult, error) {
	if input.TargetDays == 0 {
		input.TargetDays = 30
	}
	terms := map[string]assetTerm{}
	vols := map[string]float64{}
	selected := map[string]float64{}
	coverage, quality := 0.0, 1.0
	for symbol, weight := range weights {
		_, hasReturns := input.Returns[symbol]
		quotes, hasQuotes := input.Quotes[symbol]
		if !hasReturns || !hasQuotes {
			continue
		}
		term, err := assetVariance(symbol, quotes, input)
		if err != nil {
			if !input.Approximate && policy == "STRICT" {
				return CustomResult{}, err
			}
			continue
		}
		terms[symbol] = term
		vols[symbol] = term.volatility
		selected[symbol] = weight
		coverage += weight
		quality = math.Min(quality, term.quality)
	}
	if policy == "STRICT" && len(terms) != len(weights) {
		return CustomResult{}, errors.New("custom index missing required symbols")
	}
	if len(terms) == 0 || policy == "RENORMALIZE" && coverage < 0.5 {
		return CustomResult{}, errors.New("custom index has less than 50% usable weight")
	}
	normalizedWeights, err := normalized(selected)
	if err != nil {
		return CustomResult{}, err
	}
	assets := make([]string, 0, len(terms))
	for symbol := range terms {
		assets = append(assets, symbol)
	}
	volatility := vols[assets[0]]
	if len(assets) > 1 {
		corr, err := Correlation(subsetReturns(assets, input.Returns))
		if err != nil {
			return CustomResult{}, err
		}
		p, err := Portfolio(normalizedWeights, vols, corr)
		if err != nil {
			return CustomResult{}, err
		}
		volatility = p.Volatility
	}
	sourceQuality := 1.0
	for symbol := range terms {
		for _, q := range input.Quotes[symbol] {
			if q.Delayed != nil && *q.Delayed {
				sourceQuality = 0.65
			}
		}
	}
	return CustomResult{Value: volatility * 100, Quality: quality * coverage * sourceQuality}, nil
}
