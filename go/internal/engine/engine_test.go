package engine

import (
	"math"
	"testing"
)

func TestCumulativeVarianceInterpolation(t *testing.T) {
	value, err := Interpolate(20, .04, 40, .16, 30)
	if err != nil || math.Abs(value-.12) > 1e-12 {
		t.Fatalf("got %v, %v", value, err)
	}
}

func TestPortfolio(t *testing.T) {
	c := CorrelationResult{Assets: []string{"A", "B"}, Matrix: [][]float64{{1, .5}, {.5, 1}}, Observations: 252}
	result, err := Portfolio(map[string]float64{"A": .5, "B": .5}, map[string]float64{"A": .2, "B": .4}, c)
	if err != nil || math.Abs(result.Variance-.07) > 1e-12 {
		t.Fatalf("got %#v, %v", result, err)
	}
}
