package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"

	core "github.com/Dexterhhhh/semi-vix-platform/go/internal/engine"
)

type request struct {
	Returns      map[string][]float64   `json:"returns"`
	Weights      map[string]float64     `json:"weights"`
	Volatilities map[string]float64     `json:"volatilities"`
	Correlation  core.CorrelationResult `json:"correlation"`
	NearDays     float64                `json:"near_days"`
	NearVariance float64                `json:"near_variance"`
	FarDays      float64                `json:"far_days"`
	FarVariance  float64                `json:"far_variance"`
	TargetDays   float64                `json:"target_days"`
}

func endpoint(fn func(request) (any, error)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		defer r.Body.Close()
		var input request
		if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<20)).Decode(&input); err != nil {
			http.Error(w, "invalid json", http.StatusBadRequest)
			return
		}
		result, err := fn(input)
		if err != nil {
			http.Error(w, err.Error(), http.StatusUnprocessableEntity)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(result)
	}
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte("ok")) })
	mux.HandleFunc("/v1/correlation", endpoint(func(r request) (any, error) { return core.Correlation(r.Returns) }))
	mux.HandleFunc("/v1/portfolio", endpoint(func(r request) (any, error) { return core.Portfolio(r.Weights, r.Volatilities, r.Correlation) }))
	mux.HandleFunc("/v1/interpolate", endpoint(func(r request) (any, error) {
		value, err := core.Interpolate(r.NearDays, r.NearVariance, r.FarDays, r.FarVariance, r.TargetDays)
		return map[string]float64{"variance": value}, err
	}))
	address := os.Getenv("SVIX_GO_ENGINE_ADDRESS")
	if address == "" {
		address = "127.0.0.1:8090"
	}
	server := &http.Server{Addr: address, Handler: mux, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 15 * time.Second, IdleTimeout: 60 * time.Second}
	log.Printf("svix Go engine listening on %s", address)
	log.Fatal(server.ListenAndServe())
}
