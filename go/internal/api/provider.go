package api

import (
	"context"
	"database/sql"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/alpaca"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/providers"
)

type ProviderHandler struct {
	auth  *auth.Handler
	store *providers.Store
}

func NewProviderHandler(a *auth.Handler, s *providers.Store) *ProviderHandler {
	return &ProviderHandler{a, s}
}

type providerInput struct {
	Provider    string  `json:"provider"`
	Host        string  `json:"host"`
	Port        int     `json:"port"`
	ClientID    *int    `json:"client_id"`
	Feed        *string `json:"data_feed"`
	Credentials struct {
		APIKey  *string `json:"api_key"`
		Secret  *string `json:"secret"`
		Account *string `json:"account_identifier"`
	} `json:"credentials"`
}

func validProvider(p string) bool { return providers.Available(p) }
func (h *ProviderHandler) configuration(p string, c *providers.Credential) map[string]any {
	host, port, clientID, feed := providers.Env("IBKR_HOST", "127.0.0.1"), providers.EnvInt("IBKR_PORT", 7497), any(providers.EnvInt("IBKR_CLIENT_ID", 19)), any(nil)
	if p == "FUTU" {
		host = providers.Env("FUTU_HOST", "127.0.0.1")
		port = providers.EnvInt("FUTU_PORT", 11111)
		clientID = nil
	}
	if p == "ALPACA" {
		host = providers.Env("ALPACA_BASE_URL", "https://data.alpaca.markets")
		port = 443
		clientID = nil
		feed = providers.Env("ALPACA_FEED", "indicative")
	}
	present := false
	if c != nil {
		if c.Host.Valid && c.Host.String != "" {
			host = c.Host.String
		}
		if c.Port.Valid && p != "ALPACA" {
			port = int(c.Port.Int64)
		}
		if c.ClientID.Valid && p == "IBKR" {
			clientID = int(c.ClientID.Int64)
		}
		present = c.APIKey.Valid || c.Secret.Valid || c.Account.Valid
		if p == "ALPACA" {
			present = c.APIKey.Valid && c.APIKey.String != "" && c.Secret.Valid && c.Secret.String != ""
			if c.Feed.Valid {
				feed = c.Feed.String
			}
		}
	}
	ready := p != "ALPACA" || feed == "opra"
	var warning any
	if p == "ALPACA" && feed == "indicative" {
		warning = "Alpaca 免费 indicative 报价经过修改；可用于 SVIX，但结果会标记较低数据质量。"
	}
	return map[string]any{"provider": p, "configured": c != nil, "host": host, "port": port, "client_id": clientID, "credentials_present": present, "data_feed": feed, "production_ready": ready, "warning": warning}
}
func (h *ProviderHandler) configure(w http.ResponseWriter, r *http.Request) {
	var input providerInput
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&input) != nil || !validProvider(input.Provider) || len(input.Host) < 1 || len(input.Host) > 255 || input.Port < 1 || input.Port > 65535 || (input.ClientID != nil && (*input.ClientID < 0 || *input.ClientID > 2147483647)) || (input.Feed != nil && *input.Feed != "indicative" && *input.Feed != "opra") {
		invalid(w, 422, "Invalid provider configuration")
		return
	}
	for _, v := range []*string{input.Credentials.APIKey, input.Credentials.Secret, input.Credentials.Account} {
		if v != nil {
			*v = strings.TrimSpace(*v)
			if len(*v) > 2048 {
				invalid(w, 422, "Credential too long")
				return
			}
		}
	}
	tx, err := h.auth.Database().BeginTx(r.Context(), nil)
	if err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(r.Context(), "SELECT pg_advisory_xact_lock(hashtext('svix_provider_configuration'))"); err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	var key, secret, account sql.NullString
	err = tx.QueryRowContext(r.Context(), "SELECT api_key_encrypted,secret_encrypted,account_identifier_encrypted FROM provider_credentials WHERE provider=$1", input.Provider).Scan(&key, &secret, &account)
	if err != nil && err != sql.ErrNoRows {
		invalid(w, 503, "Database unavailable")
		return
	}
	for _, pair := range []struct {
		input  *string
		stored *sql.NullString
	}{{input.Credentials.APIKey, &key}, {input.Credentials.Secret, &secret}, {input.Credentials.Account, &account}} {
		if pair.input != nil {
			encrypted, e := h.store.Encrypt(*pair.input)
			if e != nil {
				invalid(w, 503, "Credential encryption unavailable")
				return
			}
			*pair.stored = sql.NullString{String: encrypted, Valid: true}
		}
	}
	if input.Provider == "ALPACA" {
		// Validate the resulting credentials, including partial updates of an existing pair.
		k, e1 := h.store.Decrypt(key)
		s, e2 := h.store.Decrypt(secret)
		if e1 != nil || e2 != nil || k == "" || s == "" {
			invalid(w, 422, "Alpaca API Key 和 API Secret 必须同时设置")
			return
		}
		input.Host = providers.Env("ALPACA_BASE_URL", "https://data.alpaca.markets")
		if input.Feed == nil {
			f := "indicative"
			input.Feed = &f
		}
	} else {
		input.Feed = nil
	}
	if input.Provider != "IBKR" {
		input.ClientID = nil
	}
	if _, err = tx.ExecContext(r.Context(), "UPDATE provider_credentials SET enabled=false"); err == nil {
		_, err = tx.ExecContext(r.Context(), `INSERT INTO provider_credentials(provider,api_key_encrypted,secret_encrypted,account_identifier_encrypted,host,port,client_id,data_feed,enabled,created_at,updated_at)
   VALUES($1,$2,$3,$4,$5,$6,$7,$8,true,now(),now()) ON CONFLICT(provider) DO UPDATE SET api_key_encrypted=$2,secret_encrypted=$3,account_identifier_encrypted=$4,host=$5,port=$6,client_id=$7,data_feed=$8,enabled=true,updated_at=now()`, input.Provider, key, secret, account, input.Host, input.Port, input.ClientID, input.Feed)
	}
	if err == nil {
		_, err = tx.ExecContext(r.Context(), "INSERT INTO audit_events(admin_id,action,provider,created_at) VALUES(1,'provider.configure',$1,now())", input.Provider)
	}
	if err != nil || tx.Commit() != nil {
		invalid(w, 503, "Provider configuration could not be saved")
		return
	}
	respond(w, 200, map[string]any{"provider": input.Provider, "enabled": true})
}
func (h *ProviderHandler) status(w http.ResponseWriter, r *http.Request, p string, c *providers.Credential) {
	config := h.configuration(p, c)
	result := map[string]any{"provider": p, "configured": c != nil, "connected": false, "last_checked_at": nil, "error": nil, "data_feed": config["data_feed"], "production_ready": config["production_ready"], "warning": config["warning"]}
	if c == nil {
		respond(w, 200, result)
		return
	}
	result["last_checked_at"] = time.Now().UTC()
	ctx, cancel := context.WithTimeout(r.Context(), 17*time.Second)
	defer cancel()
	if p == "ALPACA" {
		credentials, err := h.store.Alpaca(c)
		if err == nil {
			var client *alpaca.Client
			client, err = alpaca.NewClient(credentials)
			if err == nil {
				err = client.Health(ctx)
			}
		}
		if err == nil {
			result["connected"] = true
		} else {
			result["error"] = "Provider unavailable"
		}
	} else {
		// Only the vendor SDK connection is kept behind the loopback Python bridge.
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, "http://127.0.0.1:8000/internal/providers/status", nil)
		if err == nil {
			var response *http.Response
			response, err = http.DefaultClient.Do(req)
			if err == nil {
				defer response.Body.Close()
				if response.StatusCode == 200 {
					err = json.NewDecoder(response.Body).Decode(&result)
				} else {
					result["error"] = "Provider unavailable"
				}
			}
		}
		if err != nil {
			result["error"] = "Provider unavailable"
		}
	}
	respond(w, 200, result)
}
func (h *ProviderHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !h.auth.Authorize(w, r) {
		return
	}
	path := strings.TrimSuffix(r.URL.Path, "/")
	if path == "/api/provider/capabilities" && r.Method == http.MethodGet {
		respond(w, 200, map[string]any{"edition": providers.BuildEdition, "providers": providers.Supported()})
		return
	}
	if path == "/api/provider/configure" && r.Method == http.MethodPost {
		h.configure(w, r)
		return
	}
	if (path == "/api/provider/configuration" || path == "/api/provider/status") && r.Method != http.MethodGet || path == "/api/provider/test-connection" && r.Method != http.MethodPost {
		invalid(w, 405, "Method not allowed")
		return
	}
	selected := ""
	if path == "/api/provider/configuration" {
		selected = r.URL.Query().Get("provider")
		if selected != "" && !validProvider(selected) {
			invalid(w, 422, "Invalid provider")
			return
		}
	}
	c, err := h.store.Credential(selected)
	if err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	p := selected
	if p == "" {
		p = providers.DefaultProvider()
		if c != nil {
			p = c.Provider
		}
	}
	if !providers.Available(p) {
		// Preserve other-edition credentials, but never call absent SDKs.
		p, c = providers.DefaultProvider(), nil
	}
	switch path {
	case "/api/provider/configuration":
		respond(w, 200, h.configuration(p, c))
	case "/api/provider/status", "/api/provider/test-connection":
		h.status(w, r, p, c)
	default:
		invalid(w, 404, "Not found")
	}
}
