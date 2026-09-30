package engine

import (
	"math"
	"sort"
	"strings"
	"time"
)

type ObservationQuote struct {
	OptionQuote
	Feed      string
	PriceType string
}
type AssetObservation struct {
	Status          string         `json:"status"`
	Volatility      *float64       `json:"volatility,omitempty"`
	Quality         float64        `json:"quality,omitempty"`
	Oldest          *time.Time     `json:"oldest_input_at,omitempty"`
	Newest          *time.Time     `json:"newest_input_at,omitempty"`
	TermMethod      *string        `json:"term_method,omitempty"`
	ActualDays      *float64       `json:"actual_days"`
	UsedContracts   []string       `json:"used_contract_ids,omitempty"`
	Identity        [][]string     `json:"used_input_identity,omitempty"`
	UsesSpot        bool           `json:"used_spot_forward"`
	SpotTimestamp   *time.Time     `json:"spot_timestamp"`
	Feed            *string        `json:"feed,omitempty"`
	Age             float64        `json:"quote_age_minutes"`
	Span            float64        `json:"quote_span_minutes"`
	Rejected        map[string]int `json:"rejected,omitempty"`
	ExpiryErrors    []string       `json:"expiry_errors,omitempty"`
	Reason          *string        `json:"reason,omitempty"`
	SourceBatch     string         `json:"source_batch_id,omitempty"`
	SourceValuation *time.Time     `json:"source_valuation_at,omitempty"`
}

func PythonTime(t time.Time) string { return t.UTC().Format("2006-01-02T15:04:05.999999+00:00") }
func Weights() map[string]float64 {
	out := map[string]float64{}
	for k, v := range baseWeights {
		out[k] = v
	}
	return out
}
func ObserveAsset(symbol string, quotes []ObservationQuote, valuation time.Time, spot *float64, spotTime *time.Time) AssetObservation {
	out := AssetObservation{Status: "MISSINGEXPIRY", Rejected: map[string]int{}, ExpiryErrors: make([]string, 0)}
	byExpiry := map[time.Time][]OptionQuote{}
	feeds := map[string]bool{}
	for _, q := range quotes {
		age := valuation.Sub(q.Timestamp).Minutes()
		reason := ""
		switch {
		case q.PriceType != "bbo" && q.PriceType != "indicative_quote":
			reason = "UNSUPPORTED_PRICE_TYPE"
		case age < 0 || age > 15:
			reason = "QUOTE_TIME_OUT_OF_RANGE"
		case !q.Expiry.After(valuation):
			reason = "EXPIRED_CONTRACT"
		case q.Bid == nil || q.Ask == nil || math.IsNaN(*q.Bid) || math.IsNaN(*q.Ask) || math.IsInf(*q.Bid, 0) || math.IsInf(*q.Ask, 0) || *q.Bid < 0 || *q.Ask < 0 || *q.Bid > *q.Ask:
			reason = "INVALID_SPREAD"
		}
		if reason != "" {
			out.Rejected[reason]++
			continue
		}
		byExpiry[q.Expiry] = append(byExpiry[q.Expiry], q.OptionQuote)
		feeds[q.Feed] = true
	}
	if len(feeds) > 1 {
		out.Status = "MIXED_FEED"
		return out
	}
	variances := make([]VarianceResult, 0, len(byExpiry))
	expiries := make([]time.Time, 0, len(byExpiry))
	for expiry := range byExpiry {
		expiries = append(expiries, expiry)
	}
	sort.Slice(expiries, func(i, j int) bool { return expiries[i].Before(expiries[j]) })
	for _, expiry := range expiries {
		v, err := ExpiryVariance(symbol, expiry, valuation, byExpiry[expiry], 0, false, spot)
		if err != nil {
			out.ExpiryErrors = append(out.ExpiryErrors, expiry.Format("2006-01-02")+": InvalidOptionChain")
		} else {
			variances = append(variances, v)
		}
	}
	if len(variances) == 0 {
		return out
	}
	var near, far, exact *VarianceResult
	for i := range variances {
		v := &variances[i]
		if math.Abs(v.DaysToExpiry-30) <= 1e-9 {
			exact = v
		}
		if v.DaysToExpiry < 30 {
			near = v
		} else if v.DaysToExpiry > 30 && far == nil {
			far = v
		}
	}
	selected := []VarianceResult{}
	variance, quality := 0.0, 0.0
	if exact != nil {
		selected = append(selected, *exact)
		variance = exact.Variance
		quality = varianceQuality(*exact)
	} else if near != nil && far != nil {
		selected = append(selected, *near, *far)
		var err error
		variance, err = Interpolate(near.DaysToExpiry, near.Variance, far.DaysToExpiry, far.Variance, 30)
		if err != nil {
			return out
		}
		weight := (far.DaysToExpiry - 30) / (far.DaysToExpiry - near.DaysToExpiry)
		quality = weight*varianceQuality(*near) + (1-weight)*varianceQuality(*far)
	} else {
		if len(variances) > 1 {
			out.Status = "MISSING_BRACKETING_EXPIRY"
			return out
		}
		v := variances[0]
		if math.Abs(v.DaysToExpiry-30) > 7 {
			return out
		}
		selected = append(selected, v)
		variance = v.Variance
		quality = varianceQuality(v) * 0.45
	}
	method := "interpolated"
	if len(selected) == 1 {
		method = "single_expiry"
		days := selected[0].DaysToExpiry
		out.ActualDays = &days
	}
	out.TermMethod = &method
	times := make([]time.Time, 0)
	used := map[string]bool{}
	for _, v := range selected {
		times = append(times, v.InputTimestamps...)
		for _, id := range v.UsedContractIDs {
			used[id] = true
		}
		if v.QualityMetrics["spot_forward"] > 0 {
			out.UsesSpot = true
		}
	}
	if out.UsesSpot && spotTime != nil {
		times = append(times, *spotTime)
		out.SpotTimestamp = spotTime
	}
	if len(times) == 0 || len(used) == 0 {
		out.Status = "NO_USED_QUOTES"
		return out
	}
	sort.Slice(times, func(i, j int) bool { return times[i].Before(times[j]) })
	oldest, newest := times[0], times[len(times)-1]
	out.Age = valuation.Sub(oldest).Minutes()
	if out.Age < 0 || out.Age > 15 {
		out.Status = "USED_QUOTE_EXPIRED"
		return out
	}
	out.Status = "NEW"
	vol := math.Sqrt(variance) * 100
	out.Volatility = &vol
	out.Quality = quality
	out.Oldest = &oldest
	out.Newest = &newest
	out.Span = newest.Sub(oldest).Minutes()
	for id := range used {
		out.UsedContracts = append(out.UsedContracts, id)
	}
	sort.Strings(out.UsedContracts)
	for _, q := range quotes {
		if used[q.ContractID] {
			out.Identity = append(out.Identity, []string{q.ContractID, PythonTime(q.Timestamp)})
		}
	}
	sort.Slice(out.Identity, func(i, j int) bool {
		return strings.Join(out.Identity[i], "\x00") < strings.Join(out.Identity[j], "\x00")
	})
	for feed := range feeds {
		f := feed
		out.Feed = &f
	}
	return out
}
