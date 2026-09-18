package engine

import (
	"errors"
	"math"
	"sort"
)

var windows = []int{60, 120, 252}
var windowWeights = []float64{0.50, 0.30, 0.20}

type CorrelationResult struct {
	Assets       []string    `json:"assets"`
	Matrix       [][]float64 `json:"matrix"`
	Observations int         `json:"observations"`
}

type PortfolioResult struct {
	Variance              float64            `json:"variance"`
	Volatility            float64            `json:"volatility"`
	ComponentContribution map[string]float64 `json:"component_contribution"`
}

func Correlation(series map[string][]float64) (CorrelationResult, error) {
	assets := make([]string, 0, len(series))
	for asset := range series {
		assets = append(assets, asset)
	}
	sort.Strings(assets)
	if len(assets) < 2 {
		return CorrelationResult{}, errors.New("at least two assets are required")
	}
	observations := -1
	for _, asset := range assets {
		if observations < 0 || len(series[asset]) < observations {
			observations = len(series[asset])
		}
	}
	if observations < 252 {
		return CorrelationResult{}, errors.New("at least 252 aligned returns are required")
	}
	matrix := make([][]float64, len(assets))
	for i := range matrix {
		matrix[i] = make([]float64, len(assets))
	}
	for w, window := range windows {
		for i := range assets {
			a := series[assets[i]][len(series[assets[i]])-window:]
			for j := i; j < len(assets); j++ {
				b := series[assets[j]][len(series[assets[j]])-window:]
				value, err := pearson(a, b)
				if err != nil {
					return CorrelationResult{}, err
				}
				matrix[i][j] += windowWeights[w] * value
				if i != j {
					matrix[j][i] += windowWeights[w] * value
				}
			}
		}
	}
	for i := range matrix {
		matrix[i][i] = 1
	}
	return CorrelationResult{Assets: assets, Matrix: matrix, Observations: observations}, nil
}

func pearson(a, b []float64) (float64, error) {
	meanA, meanB := 0.0, 0.0
	for i := range a {
		if math.IsNaN(a[i]) || math.IsInf(a[i], 0) || math.IsNaN(b[i]) || math.IsInf(b[i], 0) {
			return 0, errors.New("returns contain non-finite values")
		}
		meanA += a[i]
		meanB += b[i]
	}
	meanA /= float64(len(a))
	meanB /= float64(len(b))
	cov, varA, varB := 0.0, 0.0, 0.0
	for i := range a {
		da, db := a[i]-meanA, b[i]-meanB
		cov += da * db
		varA += da * da
		varB += db * db
	}
	if varA <= 1e-30 || varB <= 1e-30 {
		return 0, errors.New("returns contain a zero-variance series")
	}
	return cov / math.Sqrt(varA*varB), nil
}

func Portfolio(weights, volatilities map[string]float64, correlation CorrelationResult) (PortfolioResult, error) {
	n := len(correlation.Assets)
	if n == 0 || len(weights) != n || len(volatilities) != n || len(correlation.Matrix) != n {
		return PortfolioResult{}, errors.New("portfolio inputs do not match")
	}
	total := 0.0
	for _, asset := range correlation.Assets {
		if weights[asset] < 0 || volatilities[asset] < 0 {
			return PortfolioResult{}, errors.New("negative portfolio input")
		}
		total += weights[asset]
	}
	if math.Abs(total-1) > 1e-9 {
		return PortfolioResult{}, errors.New("weights must sum to one")
	}
	contributions := make(map[string]float64, n)
	variance := 0.0
	for i, assetI := range correlation.Assets {
		if len(correlation.Matrix[i]) != n {
			return PortfolioResult{}, errors.New("invalid correlation dimensions")
		}
		marginal := 0.0
		for j, assetJ := range correlation.Assets {
			marginal += volatilities[assetI] * volatilities[assetJ] * correlation.Matrix[i][j] * weights[assetJ]
		}
		contributions[assetI] = weights[assetI] * marginal
		variance += contributions[assetI]
	}
	if variance < -1e-12 {
		return PortfolioResult{}, errors.New("negative portfolio variance")
	}
	if variance < 0 {
		variance = 0
	}
	return PortfolioResult{Variance: variance, Volatility: math.Sqrt(variance), ComponentContribution: contributions}, nil
}

func Interpolate(nearDays, nearVariance, farDays, farVariance, targetDays float64) (float64, error) {
	if nearDays >= targetDays || farDays <= targetDays || farDays <= nearDays || nearVariance <= 0 || farVariance <= 0 {
		return 0, errors.New("invalid interpolation inputs")
	}
	a := (farDays - targetDays) / (farDays - nearDays)
	value := (a*nearDays*nearVariance + (1-a)*farDays*farVariance) / targetDays
	if value <= 0 || math.IsNaN(value) || math.IsInf(value, 0) {
		return 0, errors.New("invalid interpolated variance")
	}
	return value, nil
}
