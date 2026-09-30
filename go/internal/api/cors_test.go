package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestCORSPreflight(t *testing.T) {
	called := false
	handler := CORS(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { called = true; w.WriteHeader(401) }), "http://localhost:3000")
	r := httptest.NewRequest("OPTIONS", "/api/settings", nil)
	r.Header.Set("Origin", "http://localhost:3000")
	r.Header.Set("Access-Control-Request-Method", "PUT")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, r)
	if w.Code != 204 || called || w.Header().Get("Access-Control-Allow-Origin") != "http://localhost:3000" {
		t.Fatal("settings preflight failed", w.Code, w.Header())
	}
	r.Header.Set("Origin", "https://untrusted.invalid")
	w = httptest.NewRecorder()
	handler.ServeHTTP(w, r)
	if w.Code != 403 || called {
		t.Fatal("untrusted preflight accepted")
	}
}
