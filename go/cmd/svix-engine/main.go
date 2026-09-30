package main

import (
	"encoding/json"
	"log"
	"net"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/api"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/providers"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/service"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/symbols"
)

func main() {
	mux := http.NewServeMux()
	directory := symbols.NewDirectory()
	symbolPattern := regexp.MustCompile(`^[A-Z][A-Z0-9.-]{0,15}$`)
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})
	if databaseURL := os.Getenv("DATABASE_URL"); databaseURL != "" {
		authHandler, err := auth.New(databaseURL)
		if err != nil {
			log.Fatalf("Go authentication setup failed: %v", err)
		}
		mux.Handle("/api/auth/", authHandler)
		mux.HandleFunc("/ready", func(w http.ResponseWriter, r *http.Request) {
			var initialized bool
			err := authHandler.Database().QueryRowContext(r.Context(), "SELECT EXISTS(SELECT 1 FROM admin_security WHERE admin_id=1)").Scan(&initialized)
			if err != nil || !initialized {
				http.Error(w, "database initialization incomplete", 503)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
		})
		credentialStore, err := providers.New(authHandler.Database())
		if err != nil {
			log.Fatalf("Go credential setup failed: %v", err)
		}
		mux.Handle("/api/provider/", api.NewProviderHandler(authHandler, credentialStore))
		services := &service.Service{DB: authHandler.Database(), Providers: credentialStore}
		mux.HandleFunc("/internal/scheduler/", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodPost {
				http.Error(w, "method not allowed", 405)
				return
			}
			var result map[string]any
			var err error
			switch strings.TrimPrefix(r.URL.Path, "/internal/scheduler/") {
			case "market":
				result, err = services.Collect(r.Context(), time.Now().UTC())
			case "jobs":
				result, err = services.PendingJob(r.Context())
			case "maintenance":
				result, err = services.Maintenance(r.Context(), time.Now().UTC(), false)
			default:
				http.NotFound(w, r)
				return
			}
			if err != nil {
				log.Printf("task failed: %v", err)
				http.Error(w, "task failed", 500)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(result)
		})
		mux.HandleFunc("/api/svix/calculate", func(w http.ResponseWriter, r *http.Request) {
			if !authHandler.Authorize(w, r) {
				return
			}
			if r.Method != http.MethodPost {
				http.Error(w, "method not allowed", 405)
				return
			}
			var input struct {
				Start     string `json:"start_date"`
				End       string `json:"end_date"`
				Frequency string `json:"frequency"`
			}
			decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16384))
			decoder.DisallowUnknownFields()
			if decoder.Decode(&input) != nil {
				http.Error(w, "invalid calculation request", 422)
				return
			}
			start, e1 := time.Parse("2006-01-02", input.Start)
			end, e2 := time.Parse("2006-01-02", input.End)
			if input.Frequency == "" {
				input.Frequency = "daily"
			}
			if e1 != nil || e2 != nil || end.Before(start) || (input.Frequency != "daily" && input.Frequency != "weekly") {
				http.Error(w, "invalid dates or frequency", 422)
				return
			}
			result, err := services.History(r.Context(), start, end, input.Frequency, false)
			if err != nil {
				log.Printf("history calculation failed: %v", err)
				http.Error(w, "history calculation failed", 503)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(map[string]any{"status": "completed", "records_calculated": result.Records})
		})
		customHandler := api.NewCustomHandler(authHandler, directory)
		mux.Handle("/api/custom-index", customHandler)
		mux.Handle("/api/custom-index/", customHandler)

		settingsHandler := api.NewSettingsHandler(authHandler)
		mux.Handle("/api/settings", settingsHandler)
		mux.Handle("/api/settings/", settingsHandler)
		jobsHandler := api.NewJobsHandler(authHandler)
		mux.Handle("/api/jobs", jobsHandler)
		mux.Handle("/api/jobs/", jobsHandler)
		mux.Handle("/api/svix/market-status", api.NewMarketStatusHandler(authHandler))
		svixHandler := api.NewSVIXHandler(authHandler)
		for _, path := range []string{"current", "history", "intraday", "components"} {
			mux.Handle("/api/svix/"+path, svixHandler)
		}
		mux.HandleFunc("/api/custom-index/symbols/", func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet {
				http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
				return
			}
			if !authHandler.Authorize(w, r) {
				return
			}
			symbol := strings.ToUpper(strings.TrimSpace(strings.TrimPrefix(r.URL.Path, "/api/custom-index/symbols/")))
			if !symbolPattern.MatchString(symbol) {
				http.Error(w, "invalid symbol", http.StatusUnprocessableEntity)
				return
			}
			value, found, err := directory.Lookup(r.Context(), symbol)
			if err != nil {
				http.Error(w, "symbol directory unavailable", http.StatusServiceUnavailable)
				return
			}
			if !found {
				http.Error(w, "symbol not found", http.StatusNotFound)
				return
			}
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(value)
		})
	}
	address := os.Getenv("SVIX_GO_ENGINE_ADDRESS")
	if address == "" {
		address = "127.0.0.1:8090"
	}
	server := &http.Server{Addr: address, Handler: api.CORS(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasPrefix(r.URL.Path, "/internal/") {
			host, _, err := net.SplitHostPort(r.RemoteAddr)
			ip := net.ParseIP(host)
			if err != nil || ip == nil || !ip.IsLoopback() {
				http.Error(w, "forbidden", 403)
				return
			}
		}
		mux.ServeHTTP(w, r)
	}), providers.Env("CORS_ORIGINS", "http://localhost:3000")), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, IdleTimeout: 60 * time.Second}
	log.Printf("svix Go engine listening on %s", address)
	log.Fatal(server.ListenAndServe())
}
