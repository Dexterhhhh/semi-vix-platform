package service

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"slices"
	"strings"
	"testing"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/providers"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/testutil"
)

type bridgeTransport func(*http.Request) (*http.Response, error)

func (f bridgeTransport) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestVendorCollectionUsesSelectedSymbols(t *testing.T) {
	db := testutil.Database(t)
	if _, err := db.Exec(`TRUNCATE provider_credentials,system_settings,custom_index_components,custom_index_versions,custom_indices CASCADE`); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec(`INSERT INTO provider_credentials(provider,enabled,created_at,updated_at) VALUES('IBKR',true,now(),now());
		INSERT INTO system_settings(key,value,updated_at) VALUES('selected_symbols','["NVDA","AMD"]',now())`); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Exec(`TRUNCATE provider_credentials,system_settings CASCADE`) })
	t.Setenv("CREDENTIAL_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
	store, err := providers.New(db)
	if err != nil {
		t.Fatal(err)
	}
	previous := http.DefaultClient
	t.Cleanup(func() { http.DefaultClient = previous })
	called := false
	http.DefaultClient = &http.Client{Transport: bridgeTransport(func(r *http.Request) (*http.Response, error) {
		called = true
		if r.Method != http.MethodPost || r.URL.String() != "http://127.0.0.1:8000/internal/providers/collect" || r.Header.Get("Content-Type") != "application/json" {
			t.Fatalf("invalid SDK request: %s %s", r.Method, r.URL)
		}
		var payload struct {
			Symbols []string `json:"symbols"`
		}
		if err := json.NewDecoder(r.Body).Decode(&payload); err != nil || !slices.Equal(payload.Symbols, []string{"NVDA", "AMD"}) {
			t.Fatalf("SDK symbol selection: %+v %v", payload, err)
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"provider":"IBKR","symbols_requested":2}`)), Header: make(http.Header)}, nil
	})}
	result, err := (&Service{DB: db, Providers: store}).collectQuotes(context.Background())
	if err != nil || !called || result.Provider != "IBKR" || result.SymbolsRequested != 2 {
		t.Fatalf("collection=%+v called=%v err=%v", result, called, err)
	}
}
