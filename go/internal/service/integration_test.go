package service

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"testing"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/engine"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/market"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/providers"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/testutil"
)

func TestPostgresWorkflow(t *testing.T) {
	db := testutil.Database(t)
	ctx := context.Background()
	clear := func() {
		_, err := db.Exec(`TRUNCATE option_snapshot,stock_snapshot,svix_history,svix_daily,custom_index_history,custom_index_daily,custom_index_components,custom_index_versions,custom_indices,svix_asset_observations,svix_observations,svix_correlation_cache,market_collection_runs,calculation_jobs,data_maintenance_runs,system_settings,provider_credentials CASCADE`)
		if err != nil {
			t.Fatal(err)
		}
	}
	clear()
	t.Cleanup(clear)
	t.Setenv("CREDENTIAL_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
	store, err := providers.New(db)
	if err != nil {
		t.Fatal(err)
	}
	s := &Service{DB: db, Providers: store}
	t.Setenv("DATA_PROVIDER", "ALPACA")
	day := time.Date(2026, 9, 30, 0, 0, 0, 0, time.UTC)
	quoteAt := day.Add(14 * time.Hour)
	valuation := quoteAt.Add(2 * time.Minute)
	exec := func(query string, args ...any) {
		if _, err := db.Exec(query, args...); err != nil {
			t.Fatal(err)
		}
	}
	// All six assets have prior-session daily closes, with distinct return sequences.
	for asset, symbol := range Universe {
		index := 0
		for stamp := day.AddDate(0, 0, -430); stamp.Before(day); stamp = stamp.AddDate(0, 0, 1) {
			if _, _, ok := market.Bounds(stamp.Format("2006-01-02")); !ok {
				continue
			}
			price := 100 * math.Exp(0.0002*float64(index)+0.08*math.Sin(float64(index)/(6+float64(asset))))
			index++
			exec(`INSERT INTO stock_snapshot(timestamp,provider,symbol,price,price_type,received_at) VALUES($1,'ALPACA',$2,$3,'adjusted_close',$4)`, stamp, symbol, price, day.Add(-time.Hour))
		}
	}
	seedBatch := func(batch string, finished time.Time, onlySOXX, repeat bool) {
		exec(`INSERT INTO market_collection_runs(session_date,status,interval_minutes,interval_seconds,stock_quotes_saved,option_quotes_saved,symbols_succeeded,symbols_failed,started_at,finished_at,batch_id,calculation_status) VALUES($1,'COMPLETED',1,60,6,72,6,0,$2,$3,$4,'PENDING')`, day, finished.Add(-time.Minute), finished, batch)
		for asset, symbol := range Universe {
			if onlySOXX && symbol != "SOXX" {
				continue
			}
			stamp := quoteAt
			if !repeat {
				stamp = finished.Add(-time.Minute)
			}
			exec(`INSERT INTO stock_snapshot(timestamp,provider,symbol,price,price_type,received_at,batch_id,trade_timestamp) VALUES($1,'ALPACA',$2,102,'trade',$3,$4,$1)`, stamp, symbol, finished, batch)
			for _, days := range []int{20, 40} {
				for _, strike := range []float64{90, 100, 110} {
					for _, kind := range []string{"C", "P"} {
						price := 1.0 + float64(asset)*0.1
						if strike == 100 {
							price = 3 + float64(asset)*0.1
						}
						if strike == 90 && kind == "C" {
							price = 13 + float64(asset)*0.1
						}
						if strike == 110 && kind == "P" {
							price = 9 + float64(asset)*0.1
						}
						exec(`INSERT INTO option_snapshot(timestamp,provider,contract_id,symbol,expiry,strike,option_type,bid,ask,last,delayed,feed,price_type,received_at,batch_id) VALUES($1,'ALPACA',$2,$3,$4,$5,$6,$7,$7,$7,true,'indicative','indicative_quote',$8,$9)`, stamp, fmt.Sprintf("%s-%d-%g-%s", symbol, days, strike, kind), symbol, day.AddDate(0, 0, days), strike, kind, price, finished, batch)
					}
				}
			}
		}
	}
	seedBatch("go-test-first", valuation, false, true)
	t.Run("history_and_custom", func(t *testing.T) {
		var index, version int
		if err := db.QueryRow("INSERT INTO custom_indices(name,enabled,missing_policy,created_at,updated_at) VALUES('Test',true,'STRICT',now(),now()) RETURNING id").Scan(&index); err != nil {
			t.Fatal(err)
		}
		if err := db.QueryRow("INSERT INTO custom_index_versions(custom_index_id,version_number,name,missing_policy,created_at) VALUES($1,1,'Test','STRICT',now()) RETURNING id", index).Scan(&version); err != nil {
			t.Fatal(err)
		}
		exec("INSERT INTO custom_index_components(version_id,symbol,weight) VALUES($1,'NVDA',0.6),($1,'AMD',0.4)", version)
		summary, err := s.History(ctx, day, day, "daily", false)
		if err != nil || summary.Records != 1 || summary.Estimated != 1 {
			t.Fatalf("history=%+v err=%v", summary, err)
		}
		var value float64
		// Golden values were calculated independently by the Python reference on this fixture.
		if err := db.QueryRow("SELECT value FROM custom_index_history").Scan(&value); err != nil || math.Abs(value-15.331047246485063) > 1e-8 {
			t.Fatalf("custom=%g err=%v", value, err)
		}
		if err := db.QueryRow("SELECT svix FROM svix_history").Scan(&value); err != nil || math.Abs(value-20.43067981800271) > 1e-8 {
			t.Fatalf("historical reference mismatch: %g %v", value, err)
		}
	})
	t.Run("observation_and_no_lookahead", func(t *testing.T) {
		// This current-session close must never enter intraday correlation.
		exec(`INSERT INTO stock_snapshot(timestamp,provider,symbol,price,price_type,received_at) VALUES($1,'ALPACA','NVDA',99999,'adjusted_close',$2)`, day, valuation)
		ok, err := s.Observation(ctx, "go-test-first")
		if err != nil || !ok {
			t.Fatalf("observation=%v %v", ok, err)
		}
		var value float64
		var coverage float64
		var state string
		if err = db.QueryRow("SELECT svix,coverage,status FROM svix_observations WHERE batch_id='go-test-first'").Scan(&value, &coverage, &state); err != nil {
			t.Fatal(err)
		}
		if math.Abs(value-20.513302170841353) > 1e-8 || math.Abs(coverage-1) > 1e-12 || state != "FREE_ESTIMATE" {
			t.Fatalf("value=%g coverage=%g state=%s", value, coverage, state)
		}
		var asOf time.Time
		if err = db.QueryRow("SELECT max(as_of) FROM svix_correlation_cache").Scan(&asOf); err != nil || !asOf.Before(day) {
			t.Fatalf("correlation includes current session: %s %v", asOf, err)
		}
		ok, err = s.Observation(ctx, "go-test-first")
		if err != nil || !ok {
			t.Fatal("idempotent observation", ok, err)
		}
		seedBatch("go-test-repeat", valuation.Add(time.Minute), false, true)
		ok, err = s.Observation(ctx, "go-test-repeat")
		if err != nil || ok {
			t.Fatalf("repeat should not produce point: %v %v", ok, err)
		}
		if err = db.QueryRow("SELECT calculation_status FROM market_collection_runs WHERE batch_id='go-test-repeat'").Scan(&state); err != nil || state != "NO_NEW_DATA" {
			t.Fatalf("repeat state=%s err=%v", state, err)
		}
		seedBatch("go-test-cached", valuation.Add(2*time.Minute), true, false)
		ok, err = s.Observation(ctx, "go-test-cached")
		if err != nil || !ok {
			t.Fatal("cached", ok, err)
		}
		var cached float64
		if err = db.QueryRow("SELECT status,cached_coverage FROM svix_observations WHERE batch_id='go-test-cached'").Scan(&state, &cached); err != nil || state != "CACHED" || math.Abs(cached-0.5) > 1e-12 {
			t.Fatalf("cache %s %g %v", state, cached, err)
		}
	})
	t.Run("sql_rollup_and_archive_guard", func(t *testing.T) {
		exec(`INSERT INTO system_settings(key,value,updated_at) VALUES('option_cleanup_enabled','true',now())`)
		result, err := s.Maintenance(ctx, day.AddDate(0, 0, 30), true)
		if err != nil {
			t.Fatal(err)
		}
		if result["option_rows_deleted"].(int64) != 0 {
			t.Fatal("deleted unarchived quotes")
		}
		var samples int
		if err = db.QueryRow("SELECT sample_count FROM svix_daily WHERE date=$1", day).Scan(&samples); err != nil || samples != 1 {
			t.Fatalf("samples=%d err=%v", samples, err)
		}
		var count int
		if err = db.QueryRow("SELECT count(*) FROM svix_history").Scan(&count); err != nil || count != 0 {
			t.Fatalf("history rows=%d err=%v", count, err)
		}
		watermark, _ := json.Marshal(day.Format("2006-01-02"))
		exec("INSERT INTO system_settings(key,value,updated_at) VALUES('option_archive_through',$1,now())", string(watermark))
		result, err = s.Maintenance(ctx, day.AddDate(0, 0, 31), true)
		if err != nil || result["option_rows_deleted"].(int64) == 0 {
			t.Fatalf("archive cleanup=%+v err=%v", result, err)
		}
		if err = db.QueryRow("SELECT sample_count FROM svix_daily WHERE date=$1", day).Scan(&samples); err != nil || samples != 1 {
			t.Fatal("rollup counted same data twice", samples, err)
		}
	})
	t.Run("queue_claim_and_recovery", func(t *testing.T) {
		t.Setenv("DATA_PROVIDER", "IBKR")
		exec(`INSERT INTO calculation_jobs(type,start_date,end_date,frequency,status,progress,created_at) VALUES('HISTORICAL_SVIX','2024-01-01','2024-01-02','daily','RUNNING',10,now())`)
		result, err := s.PendingJob(ctx)
		if err != nil || result["status"] != "NO_VALID_DATA" {
			t.Fatalf("recovery=%+v err=%v", result, err)
		}
		result, err = s.PendingJob(ctx)
		if err != nil || result["status"] != "IDLE" {
			t.Fatalf("queue=%+v err=%v", result, err)
		}
	})
}

func TestIdentityUpgradeCompatibility(t *testing.T) {
	if !sameIdentity([][]string{{"c", "2026-09-30T14:00:00Z"}}, [][]string{{"c", "2026-09-30T14:00:00+00:00"}}) {
		t.Fatal("Python timestamps did not match Go timestamps")
	}
}
func TestAlignedHistoryNeedsCommonDates(t *testing.T) {
	histories := map[string]map[string]float64{"A": {}, "B": {}}
	for i := 0; i < 260; i++ {
		histories["A"][fmt.Sprint(i)] = 100 + float64(i)
		histories["B"][fmt.Sprint(i+10)] = 100 + float64(i)
	}
	returns, _ := alignedReturns(histories, []string{"A", "B"})
	if len(returns) != 0 {
		t.Fatal("unaligned 250 common days accepted")
	}
}

func TestPriorAssetPythonDatetimeCompatibility(t *testing.T) {
	var asset engine.AssetObservation
	err := decodePriorAsset(`{"status":"NEW","volatility":30,"oldest_input_at":"2026-09-30 14:00:00+00:00","newest_input_at":"2026-09-30 14:01:00+00:00","term_method":"interpolated"}`, &asset)
	if err != nil || asset.Oldest == nil || asset.Oldest.Hour() != 14 {
		t.Fatalf("Python cached asset failed to decode: %+v %v", asset, err)
	}
}
