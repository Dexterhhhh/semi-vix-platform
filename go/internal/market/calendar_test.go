package market

import (
	"testing"
	"time"
)

func TestNYSEHolidayAndEarlyClose(t *testing.T) {
	if _, _, ok := Bounds("2026-07-03"); ok {
		t.Fatal("observed Independence Day must be closed")
	}
	opened, closed, ok := Bounds("2026-11-27")
	if !ok || closed.Sub(opened) != 4*time.Hour {
		t.Fatalf("Friday after Thanksgiving should have a half-day plus collection window: %v %v %v", opened, closed, ok)
	}
}

func TestMarketStatus(t *testing.T) {
	status, err := Current(time.Date(2026, 9, 30, 14, 0, 0, 0, time.UTC))
	if err != nil || status.State != "OPEN" || !status.IsCollectionWindow || *status.SessionDate != "2026-09-30" {
		t.Fatalf("unexpected market status: %+v %v", status, err)
	}
	status, err = Current(time.Date(2026, 10, 3, 14, 0, 0, 0, time.UTC))
	if err != nil || status.State != "CLOSED" || *status.SessionDate != "2026-10-02" {
		t.Fatalf("unexpected weekend status: %+v %v", status, err)
	}
}
