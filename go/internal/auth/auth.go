package auth

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha1"
	"crypto/sha256"
	"database/sql"
	"encoding/base32"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/database"
	_ "github.com/lib/pq"
	"golang.org/x/crypto/argon2"
)

type Handler struct {
	db            *sql.DB
	jwtKey        []byte
	encryptionKey []byte
	accessMinutes int
	refreshDays   int
	secureCookie  bool
}

type admin struct {
	ID       int
	Username string
	Hash     string
	Active   bool
}

func New(databaseURL string) (*Handler, error) {
	if databaseURL == "" {
		return nil, errors.New("DATABASE_URL is required")
	}
	key, err := base64.URLEncoding.DecodeString(strings.NewReplacer("+", "-", "/", "_").Replace(os.Getenv("SECRET_ENCRYPTION_KEY")))
	if err != nil || len(key) != 32 {
		return nil, errors.New("SECRET_ENCRYPTION_KEY must decode to 32 bytes")
	}
	secret := os.Getenv("SECRET_KEY")
	if secret == "" {
		return nil, errors.New("SECRET_KEY is required")
	}
	dsn, err := database.PostgresURL(databaseURL)
	if err != nil {
		return nil, err
	}
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(8)
	db.SetMaxIdleConns(4)
	return &Handler{db: db, jwtKey: []byte(secret), encryptionKey: key,
		accessMinutes: envInt("JWT_EXPIRE_MINUTES", 15), refreshDays: envInt("REFRESH_EXPIRE_DAYS", 7),
		secureCookie: strings.ToLower(os.Getenv("COOKIE_SECURE")) != "false"}, nil
}

func envInt(name string, fallback int) int {
	value, err := strconv.Atoi(os.Getenv(name))
	if err != nil || value <= 0 {
		return fallback
	}
	return value
}

func reply(w http.ResponseWriter, code int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(value)
}

func fail(w http.ResponseWriter, code int, message string) {
	reply(w, code, map[string]string{"detail": message})
}

func decode(w http.ResponseWriter, r *http.Request, value any) bool {
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 16<<10)).Decode(value); err != nil {
		fail(w, http.StatusUnprocessableEntity, "Invalid request")
		return false
	}
	return true
}

func randomToken(bytes int) (string, error) {
	buffer := make([]byte, bytes)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buffer), nil
}

func (h *Handler) sign(payload map[string]any) (string, error) {
	header, _ := json.Marshal(map[string]string{"alg": "HS256", "typ": "JWT"})
	data, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	message := base64.RawURLEncoding.EncodeToString(header) + "." + base64.RawURLEncoding.EncodeToString(data)
	mac := hmac.New(sha256.New, h.jwtKey)
	mac.Write([]byte(message))
	return message + "." + base64.RawURLEncoding.EncodeToString(mac.Sum(nil)), nil
}

func (h *Handler) verify(token, kind, purpose string) (int, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return 0, errors.New("invalid token")
	}
	header, err := base64.RawURLEncoding.DecodeString(parts[0])
	var metadata struct {
		Algorithm string `json:"alg"`
	}
	if err != nil || json.Unmarshal(header, &metadata) != nil || metadata.Algorithm != "HS256" {
		return 0, errors.New("invalid algorithm")
	}
	signature, err := base64.RawURLEncoding.DecodeString(parts[2])
	if err != nil {
		return 0, err
	}
	mac := hmac.New(sha256.New, h.jwtKey)
	mac.Write([]byte(parts[0] + "." + parts[1]))
	if !hmac.Equal(signature, mac.Sum(nil)) {
		return 0, errors.New("invalid signature")
	}
	data, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return 0, err
	}
	var payload struct {
		Sub     string `json:"sub"`
		Type    string `json:"type"`
		Purpose string `json:"purpose"`
		Exp     int64  `json:"exp"`
	}
	if json.Unmarshal(data, &payload) != nil || payload.Type != kind || payload.Exp <= time.Now().Unix() || purpose != "" && payload.Purpose != purpose {
		return 0, errors.New("invalid or expired token")
	}
	id, err := strconv.Atoi(payload.Sub)
	if err != nil || id < 1 {
		return 0, errors.New("invalid subject")
	}
	return id, nil
}

// Bootstrap preserves existing accounts and encrypted MFA data on upgrades.
func (h *Handler) Bootstrap(ctx context.Context) error {
	tx, err := h.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(ctx, "SELECT pg_advisory_xact_lock(hashtext('svix_bootstrap'))"); err != nil {
		return err
	}
	var exists bool
	if err = tx.QueryRowContext(ctx, "SELECT EXISTS(SELECT 1 FROM admin_account)").Scan(&exists); err != nil {
		return err
	}
	if !exists {
		username, password := os.Getenv("SVIX_ADMIN_USERNAME"), os.Getenv("SVIX_ADMIN_PASSWORD")
		if username == "" || password == "" {
			return errors.New("initial administrator credentials are required")
		}
		salt := make([]byte, 16)
		if _, err = rand.Read(salt); err != nil {
			return err
		}
		key := argon2.IDKey([]byte(password), salt, 3, 65536, 4, 32)
		hash := fmt.Sprintf("$argon2id$v=19$m=65536,t=3,p=4$%s$%s", base64.RawStdEncoding.EncodeToString(salt), base64.RawStdEncoding.EncodeToString(key))
		if _, err = tx.ExecContext(ctx, "INSERT INTO admin_account(id,username,password_hash,is_active,created_at) VALUES(1,$1,$2,true,now())", username, hash); err != nil {
			return err
		}
		if _, err = tx.ExecContext(ctx, "INSERT INTO admin_security(admin_id,mfa_enabled,created_at) VALUES(1,false,now())"); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (h *Handler) token(id int, kind, purpose string, duration time.Duration) (string, error) {
	payload := map[string]any{"sub": strconv.Itoa(id), "type": kind, "exp": time.Now().Add(duration).Unix()}
	if purpose != "" {
		payload["purpose"] = purpose
	}
	return h.sign(payload)
}

func VerifyPassword(password, encoded string) bool {
	parts := strings.Split(encoded, "$")
	if len(parts) != 6 || parts[0] != "" || (parts[1] != "argon2id" && parts[1] != "argon2i") || parts[2] != "v=19" {
		return false
	}
	var memory, iterations, parallelism uint32
	if _, err := fmt.Sscanf(parts[3], "m=%d,t=%d,p=%d", &memory, &iterations, &parallelism); err != nil || memory == 0 || iterations == 0 || parallelism == 0 || memory > 1<<20 || parallelism > 32 {
		return false
	}
	salt, err := base64.RawStdEncoding.DecodeString(parts[4])
	if err != nil {
		return false
	}
	want, err := base64.RawStdEncoding.DecodeString(parts[5])
	if err != nil || len(want) == 0 || len(want) > 64 {
		return false
	}
	var actual []byte
	if parts[1] == "argon2i" {
		actual = argon2.Key([]byte(password), salt, iterations, memory, uint8(parallelism), uint32(len(want)))
	} else {
		actual = argon2.IDKey([]byte(password), salt, iterations, memory, uint8(parallelism), uint32(len(want)))
	}
	return hmac.Equal(actual, want)
}

func (h *Handler) encrypt(value string) (string, error) {
	block, err := aes.NewCipher(h.encryptionKey)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(gcm.Seal(nonce, nonce, []byte(value), nil)), nil
}

func (h *Handler) decrypt(value string) (string, error) {
	payload, err := base64.URLEncoding.DecodeString(value)
	if err != nil {
		return "", err
	}
	block, err := aes.NewCipher(h.encryptionKey)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil || len(payload) < gcm.NonceSize() {
		return "", errors.New("invalid encrypted value")
	}
	plain, err := gcm.Open(nil, payload[:gcm.NonceSize()], payload[gcm.NonceSize():], nil)
	return string(plain), err
}

func totp(secret, code string, now time.Time) bool {
	if len(code) != 6 {
		return false
	}
	key, err := base32.StdEncoding.WithPadding(base32.NoPadding).DecodeString(strings.ToUpper(secret))
	if err != nil {
		return false
	}
	for offset := int64(-1); offset <= 1; offset++ {
		counter := uint64(now.Unix()/30 + offset)
		var buffer [8]byte
		binary.BigEndian.PutUint64(buffer[:], counter)
		mac := hmac.New(sha1.New, key)
		mac.Write(buffer[:])
		result := mac.Sum(nil)
		index := result[len(result)-1] & 0x0f
		value := binary.BigEndian.Uint32(result[index:index+4]) & 0x7fffffff
		if hmac.Equal([]byte(code), []byte(fmt.Sprintf("%06d", value%1000000))) {
			return true
		}
	}
	return false
}

func (h *Handler) adminByID(id int) (admin, error) {
	var value admin
	err := h.db.QueryRow("SELECT id, username, password_hash, is_active FROM admin_account WHERE id=$1", id).Scan(&value.ID, &value.Username, &value.Hash, &value.Active)
	return value, err
}

func (h *Handler) authenticated(w http.ResponseWriter, r *http.Request) (admin, bool) {
	field := r.Header.Get("Authorization")
	if !strings.HasPrefix(strings.ToLower(field), "bearer ") {
		fail(w, http.StatusUnauthorized, "Authentication required")
		return admin{}, false
	}
	id, err := h.verify(strings.TrimSpace(field[7:]), "access", "")
	if err != nil {
		fail(w, http.StatusUnauthorized, "Invalid or expired access token")
		return admin{}, false
	}
	value, err := h.adminByID(id)
	if err != nil || !value.Active {
		fail(w, http.StatusUnauthorized, "Account unavailable")
		return admin{}, false
	}
	return value, true
}

// Authorize validates a bearer token against the active administrator record.
func (h *Handler) Authorize(w http.ResponseWriter, r *http.Request) bool {
	_, ok := h.authenticated(w, r)
	return ok
}

func (h *Handler) Database() *sql.DB { return h.db }

func (h *Handler) issue(w http.ResponseWriter, r *http.Request, value admin) {
	raw, err := randomToken(48)
	if err != nil {
		fail(w, 500, "Session creation failed")
		return
	}
	hash := sha256.Sum256([]byte(raw))
	now := time.Now().UTC()
	ip, _, splitError := net.SplitHostPort(r.RemoteAddr)
	if splitError != nil {
		ip = r.RemoteAddr
	}
	if len(ip) > 64 {
		ip = ""
	}
	if _, err := h.db.Exec("INSERT INTO sessions (refresh_token_hash, created_at, expires_at, ip_address) VALUES ($1,$2,$3,$4)", hex.EncodeToString(hash[:]), now, now.AddDate(0, 0, h.refreshDays), ip); err != nil {
		fail(w, 500, "Session creation failed")
		return
	}
	http.SetCookie(w, &http.Cookie{Name: "svix_refresh", Value: raw, Path: "/api/auth", HttpOnly: true, Secure: h.secureCookie, SameSite: http.SameSiteStrictMode, MaxAge: h.refreshDays * 86400})
	access, err := h.token(value.ID, "access", "", time.Duration(h.accessMinutes)*time.Minute)
	if err != nil {
		fail(w, 500, "Token creation failed")
		return
	}
	reply(w, 200, map[string]any{"access_token": access, "token_type": "bearer", "expires_in": h.accessMinutes * 60})
}

func (h *Handler) clear(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{Name: "svix_refresh", Value: "", Path: "/api/auth", HttpOnly: true, Secure: h.secureCookie, SameSite: http.SameSiteStrictMode, MaxAge: -1})
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	origin := r.Header.Get("Origin")
	for _, allowed := range strings.Split(os.Getenv("CORS_ORIGINS"), ",") {
		if origin != "" && origin == strings.TrimSpace(allowed) {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Access-Control-Allow-Credentials", "true")
			w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
			w.Header().Set("Vary", "Origin")
			break
		}
	}
	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	switch r.URL.Path {
	case "/api/auth/login":
		if r.Method != http.MethodPost {
			break
		}
		var body struct {
			Username string `json:"username"`
			Password string `json:"password"`
		}
		if !decode(w, r, &body) {
			return
		}
		var value admin
		err := h.db.QueryRow("SELECT id, username, password_hash, is_active FROM admin_account WHERE username=$1", body.Username).Scan(&value.ID, &value.Username, &value.Hash, &value.Active)
		if err != nil || !value.Active || !VerifyPassword(body.Password, value.Hash) {
			fail(w, 401, "Invalid username or password")
			return
		}
		var enabled bool
		if h.db.QueryRow("SELECT mfa_enabled FROM admin_security WHERE admin_id=$1", value.ID).Scan(&enabled) != nil {
			fail(w, 500, "Security settings unavailable")
			return
		}
		purpose := "setup"
		key := "mfa_setup_required"
		if enabled {
			purpose, key = "verify", "mfa_required"
		}
		token, err := h.token(value.ID, "temporary", purpose, 5*time.Minute)
		if err != nil {
			fail(w, 500, "Token creation failed")
			return
		}
		reply(w, 200, map[string]any{key: true, "temporary_token": token})
		return
	case "/api/auth/setup-mfa":
		if r.Method != http.MethodPost {
			break
		}
		var body struct {
			Token string  `json:"temporary_token"`
			Code  *string `json:"totp_code"`
		}
		if !decode(w, r, &body) {
			return
		}
		id, err := h.verify(body.Token, "temporary", "setup")
		if err != nil {
			fail(w, 401, "Invalid or expired temporary token")
			return
		}
		value, err := h.adminByID(id)
		if err != nil || !value.Active {
			fail(w, 401, "Account unavailable")
			return
		}
		var encrypted sql.NullString
		var enabled bool
		if h.db.QueryRow("SELECT totp_secret_encrypted,mfa_enabled FROM admin_security WHERE admin_id=$1", id).Scan(&encrypted, &enabled) != nil {
			fail(w, 500, "Security settings unavailable")
			return
		}
		if enabled {
			fail(w, 409, "MFA already enabled")
			return
		}
		if body.Code == nil {
			secretBytes := make([]byte, 20)
			if _, err := io.ReadFull(rand.Reader, secretBytes); err != nil {
				fail(w, 500, "MFA setup failed")
				return
			}
			secret := base32.StdEncoding.WithPadding(base32.NoPadding).EncodeToString(secretBytes)
			stored, err := h.encrypt(secret)
			if err != nil {
				fail(w, 500, "MFA setup failed")
				return
			}
			if _, err := h.db.Exec("UPDATE admin_security SET totp_secret_encrypted=$1 WHERE admin_id=$2", stored, id); err != nil {
				fail(w, 500, "MFA setup failed")
				return
			}
			uri := "otpauth://totp/Semi-VIX:" + url.QueryEscape(value.Username) + "?secret=" + secret + "&issuer=Semi-VIX"
			reply(w, 200, map[string]any{"provisioning_uri": uri, "verification_required": true})
			return
		}
		secret, err := h.decrypt(encrypted.String)
		if err != nil || !totp(secret, *body.Code, time.Now()) {
			fail(w, 400, "Invalid TOTP code")
			return
		}
		backup := make([]string, 8)
		for i := range backup {
			backup[i], err = randomToken(8)
			if err != nil {
				fail(w, 500, "MFA setup failed")
				return
			}
			backup[i] = strings.ToUpper(backup[i])
		}
		backupJSON, _ := json.Marshal(backup)
		backupEncrypted, err := h.encrypt(string(backupJSON))
		if err != nil {
			fail(w, 500, "MFA setup failed")
			return
		}
		if _, err := h.db.Exec("UPDATE admin_security SET mfa_enabled=true, backup_codes_encrypted=$1 WHERE admin_id=$2", backupEncrypted, id); err != nil {
			fail(w, 500, "MFA setup failed")
			return
		}
		_, _ = h.db.Exec("UPDATE admin_account SET last_login=$1 WHERE id=$2", time.Now().UTC(), id)
		h.issue(w, r, value)
		return
	case "/api/auth/verify-mfa":
		if r.Method != http.MethodPost {
			break
		}
		var body struct {
			Token string `json:"temporary_token"`
			Code  string `json:"totp_code"`
		}
		if !decode(w, r, &body) {
			return
		}
		id, err := h.verify(body.Token, "temporary", "verify")
		if err != nil {
			fail(w, 401, "Invalid or expired temporary token")
			return
		}
		value, err := h.adminByID(id)
		if err != nil || !value.Active {
			fail(w, 401, "Account unavailable")
			return
		}
		var encrypted sql.NullString
		var enabled bool
		if h.db.QueryRow("SELECT totp_secret_encrypted,mfa_enabled FROM admin_security WHERE admin_id=$1", id).Scan(&encrypted, &enabled) != nil || !enabled {
			fail(w, 401, "Invalid TOTP code")
			return
		}
		secret, err := h.decrypt(encrypted.String)
		if err != nil || !totp(secret, body.Code, time.Now()) {
			fail(w, 401, "Invalid TOTP code")
			return
		}
		_, _ = h.db.Exec("UPDATE admin_account SET last_login=$1 WHERE id=$2", time.Now().UTC(), id)
		h.issue(w, r, value)
		return
	case "/api/auth/refresh":
		if r.Method != http.MethodPost {
			break
		}
		cookie, err := r.Cookie("svix_refresh")
		if err != nil {
			fail(w, 401, "Refresh session is unavailable")
			return
		}
		hash := sha256.Sum256([]byte(cookie.Value))
		var expiry time.Time
		err = h.db.QueryRow("DELETE FROM sessions WHERE refresh_token_hash=$1 RETURNING expires_at", hex.EncodeToString(hash[:])).Scan(&expiry)
		if err != nil || !expiry.After(time.Now()) {
			h.clear(w)
			fail(w, 401, "Refresh session is invalid or expired")
			return
		}
		var value admin
		err = h.db.QueryRow("SELECT id,username,password_hash,is_active FROM admin_account WHERE is_active=true LIMIT 1").Scan(&value.ID, &value.Username, &value.Hash, &value.Active)
		if err != nil {
			h.clear(w)
			fail(w, 401, "Account unavailable")
			return
		}
		h.issue(w, r, value)
		return
	case "/api/auth/logout":
		if r.Method != http.MethodPost {
			break
		}
		if cookie, err := r.Cookie("svix_refresh"); err == nil {
			hash := sha256.Sum256([]byte(cookie.Value))
			_, _ = h.db.Exec("DELETE FROM sessions WHERE refresh_token_hash=$1", hex.EncodeToString(hash[:]))
		}
		h.clear(w)
		reply(w, 200, map[string]string{"status": "logged_out"})
		return
	case "/api/auth/me":
		if r.Method != http.MethodGet {
			break
		}
		value, ok := h.authenticated(w, r)
		if ok {
			reply(w, 200, map[string]string{"username": value.Username})
		}
		return
	}
	fail(w, http.StatusMethodNotAllowed, "Method not allowed")
}
