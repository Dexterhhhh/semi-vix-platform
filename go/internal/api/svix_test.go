package api

import (
	"net/http/httptest"
	"testing"
	"time"
)

func TestObservationComparableKey(t *testing.T) {
	p := observationPoint{svixPoint: svixPoint{Method: "semivix-observe-v1"}}
	err := observationMetadata(&p, `{"assets":{"NVDA":{"status":"NEW","term_method":"INTERPOLATED"},"AMD":{"status":"CACHED","term_method":"NEAREST"},"MU":{"status":"MISSING"}},"oldest_input_at":"2026-09-30T14:00:00Z"}`)
	if err != nil || *p.ComparableKey != `["semivix-observe-v1", [["AMD", "NEAREST"], ["NVDA", "INTERPOLATED"]]]` {
		t.Fatalf("key=%v err=%v", p.ComparableKey, err)
	}
}

func TestWeeklySelectionAcrossYear(t *testing.T) {
	points := []svixPoint{}
	for _, day := range []string{"2025-12-29", "2026-01-02", "2026-01-05"} {
		date, _ := time.Parse("2006-01-02", day)
		points = append(points, svixPoint{Timestamp: date})
	}
	got := weeklyPoints(points)
	if len(got) != 2 || got[0].Timestamp.Format("2006-01-02") != "2026-01-02" {
		t.Fatalf("unexpected weekly points: %+v", got)
	}
}

func TestDateRangeValidation(t *testing.T) {
	for _, query := range []string{"start_date=2026-02-30&end_date=2026-03-01", "start_date=2026-03-02&end_date=2026-03-01", "start_date=2026-03-01&end_date=2026-03-02&frequency=hourly"} {
		_, _, _, err := dateRange(httptest.NewRequest("GET", "/?"+query, nil))
		if err == nil {
			t.Fatal("accepted invalid range", query)
		}
	}
}
