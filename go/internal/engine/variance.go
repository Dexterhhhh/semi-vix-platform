package engine

import (
	"errors"
	"math"
	"sort"
	"time"
)

// OptionQuote is the wire representation of the existing Python OptionQuote.
type OptionQuote struct {
	ContractID string    `json:"contract_id"`
	Symbol     string    `json:"symbol"`
	Expiry     time.Time `json:"expiry"`
	Strike     float64   `json:"strike"`
	OptionType string    `json:"option_type"`
	Bid        *float64  `json:"bid"`
	Ask        *float64  `json:"ask"`
	Last       *float64  `json:"last"`
	Timestamp  time.Time `json:"timestamp"`
	Delayed    *bool     `json:"delayed"`
}

type VarianceResult struct {
	Symbol          string             `json:"symbol"`
	Expiry          time.Time          `json:"expiry"`
	Variance        float64            `json:"variance"`
	DaysToExpiry    float64            `json:"days_to_expiry"`
	ForwardPrice    float64            `json:"forward_price"`
	OptionCount     int                `json:"option_count"`
	QualityMetrics  map[string]float64 `json:"quality_metrics"`
	UsedContractIDs []string           `json:"used_contract_ids"`
	InputTimestamps []time.Time        `json:"input_timestamps"`
}

type optionPrice struct {
	price float64
	bid   *float64
}

type selectedOption struct {
	strike float64
	kind   string
	price  float64
}

func finitePositive(value float64) bool {
	return !math.IsNaN(value) && !math.IsInf(value, 0) && value > 0
}

func midpoint(quote OptionQuote, allowLast bool) (float64, bool) {
	if quote.Bid != nil && quote.Ask != nil && *quote.Bid <= *quote.Ask {
		value := (*quote.Bid + *quote.Ask) / 2
		if finitePositive(value) {
			return value, true
		}
	}
	if allowLast && quote.Last != nil && finitePositive(*quote.Last) {
		return *quote.Last, true
	}
	return 0, false
}

// ExpiryVariance replicates one expiry using the same parity, K0 and zero-bid
// rules as the original implementation. All timestamps are treated as UTC.
func ExpiryVariance(symbol string, expiry, valuationAt time.Time, quotes []OptionQuote, rate float64, allowLast bool, fallbackSpot *float64) (VarianceResult, error) {
	var result VarianceResult
	if symbol == "" || expiry.IsZero() || valuationAt.IsZero() {
		return result, errors.New("symbol, expiry and valuation_at are required")
	}
	T := expiry.Sub(valuationAt).Seconds() / (365 * 24 * 60 * 60)
	if !finitePositive(T) {
		return result, errors.New("expiry must be after valuation time")
	}
	if math.IsNaN(rate) || math.IsInf(rate, 0) {
		return result, errors.New("invalid risk-free rate")
	}
	pairs := map[float64]map[string]optionPrice{}
	allStrikes := map[float64]bool{}
	for _, quote := range quotes {
		if !finitePositive(quote.Strike) {
			continue
		}
		allStrikes[quote.Strike] = true
		price, valid := midpoint(quote, allowLast)
		if !valid {
			continue
		}
		if pairs[quote.Strike] == nil {
			pairs[quote.Strike] = map[string]optionPrice{}
		}
		if _, exists := pairs[quote.Strike][quote.OptionType]; exists {
			return result, errors.New("duplicate option quote at strike")
		}
		pairs[quote.Strike][quote.OptionType] = optionPrice{price: price, bid: quote.Bid}
	}
	strikes := make([]float64, 0, len(allStrikes))
	for strike := range allStrikes {
		strikes = append(strikes, strike)
	}
	sort.Float64s(strikes)
	if len(strikes) == 0 {
		return result, errors.New("no valid strikes")
	}
	parityCount := 0
	reference, call, put, bestDifference := 0.0, 0.0, 0.0, math.Inf(1)
	for _, strike := range strikes {
		c, hasCall := pairs[strike]["C"]
		p, hasPut := pairs[strike]["P"]
		if !hasCall || !hasPut {
			continue
		}
		parityCount++
		difference := math.Abs(c.price - p.price)
		if difference < bestDifference {
			reference, call, put, bestDifference = strike, c.price, p.price, difference
		}
	}
	spotForward := false
	forwardQuality := math.Min(1, float64(parityCount)/3)
	forward := reference + math.Exp(rate*T)*(call-put)
	if parityCount == 0 || !finitePositive(forward) {
		if fallbackSpot == nil || !finitePositive(*fallbackSpot) {
			return result, errors.New("no valid parity forward or fallback spot")
		}
		spotForward = true
		forward, reference, forwardQuality, parityCount = *fallbackSpot, *fallbackSpot, 0.25, 0
	}
	k0 := strikes[0]
	k0Fallback := true
	for _, strike := range strikes {
		if strike <= forward {
			k0, k0Fallback = strike, false
		}
	}
	if k0Fallback {
		for _, strike := range strikes {
			if math.Abs(strike-forward) < math.Abs(k0-forward) {
				k0 = strike
			}
		}
	}
	k0Call, hasK0Call := pairs[k0]["C"]
	k0Put, hasK0Put := pairs[k0]["P"]
	if !spotForward && (!hasK0Call || !hasK0Put) {
		return result, errors.New("K0 requires a valid call-put pair")
	}
	selected := map[float64]selectedOption{}
	addWing := func(reverse bool, kind string) {
		zeroBids := 0
		for i := 0; i < len(strikes); i++ {
			index := i
			if reverse {
				index = len(strikes) - 1 - i
			}
			strike := strikes[index]
			if reverse && strike >= k0 || !reverse && strike <= k0 {
				continue
			}
			option, exists := pairs[strike][kind]
			if !exists {
				continue
			}
			if option.bid != nil && *option.bid <= 0 {
				zeroBids++
				if zeroBids >= 2 {
					break
				}
				continue
			}
			zeroBids = 0
			selected[strike] = selectedOption{strike: strike, kind: kind, price: option.price}
		}
	}
	addWing(true, "P")
	addWing(false, "C")
	if hasK0Call && hasK0Put {
		selected[k0] = selectedOption{strike: k0, kind: "K0", price: (k0Call.price + k0Put.price) / 2}
	} else if spotForward {
		if hasK0Call {
			selected[k0] = selectedOption{strike: k0, kind: "K0-C", price: k0Call.price}
		} else if hasK0Put {
			selected[k0] = selectedOption{strike: k0, kind: "K0-P", price: k0Put.price}
		}
	}
	selectedStrikes := make([]float64, 0, len(selected))
	for strike := range selected {
		selectedStrikes = append(selectedStrikes, strike)
	}
	sort.Float64s(selectedStrikes)
	if len(selectedStrikes) < 2 {
		return result, errors.New("insufficient OTM option prices")
	}
	sum := 0.0
	for i, strike := range selectedStrikes {
		var delta float64
		switch i {
		case 0:
			delta = selectedStrikes[1] - strike
		case len(selectedStrikes) - 1:
			delta = strike - selectedStrikes[i-1]
		default:
			delta = (selectedStrikes[i+1] - selectedStrikes[i-1]) / 2
		}
		sum += delta / (strike * strike) * math.Exp(rate*T) * selected[strike].price
	}
	variance := 2/T*sum - math.Pow(forward/k0-1, 2)/T
	if !finitePositive(variance) {
		return result, errors.New("variance replication produced a non-positive variance")
	}
	usedIDs := make([]string, 0)
	usedTimes := make([]time.Time, 0)
	for _, quote := range quotes {
		option, used := selected[quote.Strike]
		usedForForward := parityCount > 0 && quote.Strike == reference
		usedForWing := used && quote.OptionType == option.kind
		usedForK0 := quote.Strike == k0 && used && (option.kind == "K0" || option.kind == "K0-"+quote.OptionType)
		if usedForForward || usedForWing || usedForK0 {
			usedIDs = append(usedIDs, quote.ContractID)
			usedTimes = append(usedTimes, quote.Timestamp)
		}
	}
	spot, nearest := 0.0, 0.0
	if spotForward {
		spot = 1
	}
	if k0Fallback {
		nearest = 1
	}
	return VarianceResult{
		Symbol: symbol, Expiry: expiry, Variance: variance, DaysToExpiry: T * 365,
		ForwardPrice: forward, OptionCount: len(selectedStrikes),
		QualityMetrics:  map[string]float64{"forward_quality": forwardQuality, "k0_fallback": nearest, "parity_pairs": float64(parityCount), "spot_forward": spot},
		UsedContractIDs: usedIDs, InputTimestamps: usedTimes,
	}, nil
}
