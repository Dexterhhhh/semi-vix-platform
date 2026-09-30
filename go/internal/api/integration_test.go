package api

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/providers"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/symbols"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/testutil"
)

type fixtureDirectory struct{}

func (fixtureDirectory) Lookup(_ context.Context, name string) (symbols.ListedSymbol, bool, error) {
	return symbols.ListedSymbol{Symbol: name, Name: "Test Company Inc."}, name == "AAPL" || name == "NVDA", nil
}
func TestPostgresAPIs(t *testing.T) {
	db := testutil.Database(t)
	t.Setenv("SECRET_KEY", "go-integration-key")
	t.Setenv("SECRET_ENCRYPTION_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
	t.Setenv("CREDENTIAL_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
	t.Setenv("SVIX_ADMIN_USERNAME", "go-test-admin")
	t.Setenv("SVIX_ADMIN_PASSWORD", "local-test-only")
	a, err := auth.New(strings.Replace(os.Getenv("SVIX_TEST_DATABASE_URL"), "postgresql+psycopg:", "postgresql:", 1))
	if err != nil {
		t.Fatal(err)
	}
	defer a.Database().Close()
	if err = a.Bootstrap(context.Background()); err != nil {
		t.Fatal(err)
	}
	store, err := providers.New(a.Database())
	if err != nil {
		t.Fatal(err)
	}
	cleanup := func() {
		if _, err = db.Exec(`TRUNCATE svix_history,svix_daily,svix_observations,svix_asset_observations,market_collection_runs,custom_indices,custom_index_versions,custom_index_components,custom_index_history,custom_index_daily,provider_credentials,system_settings,calculation_jobs,audit_events CASCADE`); err != nil {
			t.Fatal(err)
		}
	}
	cleanup()
	t.Cleanup(cleanup)
	tokenHeader := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	payload, _ := json.Marshal(map[string]any{"sub": "1", "type": "access", "exp": time.Now().Add(time.Minute).Unix()})
	message := tokenHeader + "." + base64.RawURLEncoding.EncodeToString(payload)
	mac := hmac.New(sha256.New, []byte("go-integration-key"))
	mac.Write([]byte(message))
	token := message + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	call := func(h http.Handler, method, path, body string, expected int) *httptest.ResponseRecorder {
		t.Helper()
		r := httptest.NewRequest(method, path, strings.NewReader(body))
		r.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		if w.Code != expected {
			t.Fatalf("%s %s: expected %d got %d: %s", method, path, expected, w.Code, w.Body.String())
		}
		return w
	}
	t.Run("provider_credentials", func(t *testing.T) {
		h := NewProviderHandler(a, store)
		call(h, "GET", "/api/provider/capabilities", "", 200)
		call(h, "POST", "/api/provider/configure", `{"provider":"ALPACA","host":"https://untrusted.invalid","port":443,"credentials":{"api_key":"fixture-key","secret":"fixture-secret"}}`, 200)
		w := call(h, "GET", "/api/provider/configuration?provider=ALPACA", "", 200)
		if strings.Contains(w.Body.String(), "fixture-key") || strings.Contains(w.Body.String(), "fixture-secret") || strings.Contains(w.Body.String(), "untrusted.invalid") {
			t.Fatal("configuration leaked secret or trusted user URL")
		}
		credential, err := store.Credential("ALPACA")
		if err != nil {
			t.Fatal(err)
		}
		key, err := store.Decrypt(credential.APIKey)
		if err != nil || key != "fixture-key" {
			t.Fatal("credential roundtrip", err)
		}
		call(h, "POST", "/api/provider/configure", `{"provider":"ALPACA","host":"unused","port":443,"credentials":{"secret":""}}`, 422)
		credential, _ = store.Credential("ALPACA")
		secret, _ := store.Decrypt(credential.Secret)
		if secret != "fixture-secret" {
			t.Fatal("invalid update changed secret")
		}
	})
	t.Run("alpaca_edition_rejects_sdk_configuration", func(t *testing.T) {
		previous := providers.BuildEdition
		providers.BuildEdition = "alpaca"
		defer func() { providers.BuildEdition = previous }()
		h := NewProviderHandler(a, store)
		call(h, "POST", "/api/provider/configure", `{"provider":"IBKR","host":"localhost","port":7497}`, 422)
		call(h, "GET", "/api/provider/configuration?provider=FUTU", "", 422)
		w := call(h, "GET", "/api/provider/capabilities", "", 200)
		if strings.Contains(w.Body.String(), "IBKR") || strings.Contains(w.Body.String(), "FUTU") {
			t.Fatal(w.Body.String())
		}
	})
	t.Run("svix_read_fallbacks", func(t *testing.T) {
		h := NewSVIXHandler(a)
		call(h, "GET", "/api/svix/current", "", 404)
		if _, err = db.Exec(`INSERT INTO svix_daily(date,svix_open,svix_high,svix_low,svix_close,core_close,memory_close,ai_close,sample_count,min_calculation_quality,estimated,created_at,updated_at) VALUES('2026-09-28',10,12,10,12,13,14,15,2,0.7,true,now(),now())`); err != nil {
			t.Fatal(err)
		}
		call(h, "GET", "/api/svix/current", "", 200)
		if _, err = db.Exec(`INSERT INTO svix_history(timestamp,svix,core_vol,memory_vol,ai_vol,calculation_quality,estimated,calculation_method,market_data_quality,created_at) VALUES('2026-09-29T14:00:00Z',20,21,22,23,1,false,'test','bbo',now()),('2026-09-29T15:00:00Z',99,21,22,23,0.5,true,'test','bbo',now())`); err != nil {
			t.Fatal(err)
		}
		w := call(h, "GET", "/api/svix/history?start_date=2026-09-28&end_date=2026-09-30", "", 200)
		var points []svixPoint
		if json.Unmarshal(w.Body.Bytes(), &points) != nil || len(points) != 2 || *points[1].SVIX != 20 {
			t.Fatalf("strict priority: %s", w.Body.String())
		}
		w = call(h, "GET", "/api/svix/intraday?session_date=2026-09-29", "", 200)
		var observations []observationPoint
		if json.Unmarshal(w.Body.Bytes(), &observations) != nil || len(observations) != 2 {
			t.Fatal("intraday", w.Body.String())
		}
		if _, err = db.Exec(`INSERT INTO market_collection_runs(session_date,status,interval_minutes,interval_seconds,stock_quotes_saved,option_quotes_saved,symbols_succeeded,symbols_failed,started_at,finished_at,batch_id) VALUES('2026-09-30','COMPLETED',1,60,0,0,0,0,'2026-09-30T14:00:00Z','2026-09-30T14:01:00Z','api-fixture')`); err != nil {
			t.Fatal(err)
		}
		if _, err = db.Exec(`INSERT INTO svix_observations(session_date,valuation_at,batch_id,method_version,core,status,coverage,cached_coverage,details) VALUES('2026-09-30','2026-09-30T14:01:00Z','api-fixture','semivix-observe-v1',30,'PARTIAL_COVERAGE',0.5,0,'{}')`); err != nil {
			t.Fatal(err)
		}
		w = call(h, "GET", "/api/svix/current", "", 200)
		var point observationPoint
		if json.Unmarshal(w.Body.Bytes(), &point) != nil || point.SVIX != nil || point.Core == nil || *point.Core != 30 {
			t.Fatal("nullable observation lost", w.Body.String())
		}
		call(NewMarketStatusHandler(a), "GET", "/api/svix/market-status", "", 200)
	})
	t.Run("custom_versions_and_series", func(t *testing.T) {
		h := NewCustomHandler(a, fixtureDirectory{})
		call(h, "GET", "/api/custom-index", "", 200)
		w := call(h, "PUT", "/api/custom-index", `{"name":"Apple","components":[{"symbol":"aapl","weight_percent":100}]}`, 200)
		var config customConfig
		if json.Unmarshal(w.Body.Bytes(), &config) != nil || config.Version != 1 {
			t.Fatal(w.Body.String())
		}
		call(h, "PUT", "/api/custom-index", `{"name":"Apple","enabled":false,"components":[{"symbol":"AAPL","weight_percent":100}]}`, 200)
		w = call(h, "GET", "/api/custom-index", "", 200)
		if json.Unmarshal(w.Body.Bytes(), &config) != nil || config.Version != 1 {
			t.Fatal("toggle created version")
		}
		call(h, "PUT", "/api/custom-index", `{"name":"Mixed","components":[{"symbol":"AAPL","weight_percent":60},{"symbol":"NVDA","weight_percent":40}]}`, 200)
		w = call(h, "GET", "/api/custom-index", "", 200)
		if json.Unmarshal(w.Body.Bytes(), &config) != nil || config.Version != 2 {
			t.Fatal("weights did not create version")
		}
		call(h, "PUT", "/api/custom-index", `{"name":"Bad","components":[{"symbol":"UNKNOWN","weight_percent":100}]}`, 422)
		var versionID int
		if err = db.QueryRow("SELECT id FROM custom_index_versions WHERE version_number=2").Scan(&versionID); err != nil {
			t.Fatal(err)
		}
		if _, err = db.Exec(`INSERT INTO custom_index_history(custom_index_id,version_id,timestamp,value,calculation_quality,estimated,created_at) VALUES($1,$2,'2026-09-30T14:00:00Z',42,1,false,now())`, config.ID, versionID); err != nil {
			t.Fatal(err)
		}
		call(h, "GET", "/api/custom-index/current", "", 200)
		call(h, "GET", "/api/custom-index/history?start_date=2026-09-30&end_date=2026-09-30", "", 200)
		call(h, "GET", "/api/custom-index/intraday?session_date=2026-09-30", "", 200)
	})
	t.Run("settings_and_queue", func(t *testing.T) {
		h := NewSettingsHandler(a)
		call(h, "PUT", "/api/settings", `{"intraday_refresh_seconds":120}`, 200)
		call(h, "GET", "/api/settings", "", 200)
		call(h, "GET", "/api/settings/data-lifecycle/status", "", 200)
		call(h, "POST", "/api/settings/data-lifecycle/run", "", 202)
		call(h, "GET", "/api/settings/system-status", "", 200)
		j := NewJobsHandler(a)
		call(j, "POST", "/api/jobs/create", `{"start_date":"2025-01-01","end_date":"2025-01-02"}`, 202)
		call(j, "POST", "/api/jobs/create", `{"start_date":"2025-01-01","end_date":"2025-01-02"}`, 409)
		call(j, "GET", "/api/jobs", "", 200)
	})
}
