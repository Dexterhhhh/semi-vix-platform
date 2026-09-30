package providers

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"database/sql"
	"encoding/base64"
	"errors"
	"os"
	"strconv"
	"strings"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/alpaca"
)

type Credential struct {
	Provider                string
	APIKey, Secret, Account sql.NullString
	Host                    sql.NullString
	Port, ClientID          sql.NullInt64
	Feed                    sql.NullString
}

type Store struct {
	DB  *sql.DB
	key []byte
}

func New(db *sql.DB) (*Store, error) {
	key, err := base64.URLEncoding.DecodeString(strings.NewReplacer("+", "-", "/", "_").Replace(os.Getenv("CREDENTIAL_MASTER_KEY")))
	if err != nil || len(key) != 32 {
		return nil, errors.New("CREDENTIAL_MASTER_KEY must decode to 32 bytes")
	}
	return &Store{DB: db, key: key}, nil
}
func (s *Store) Encrypt(value string) (string, error) {
	block, err := aes.NewCipher(s.key)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err = rand.Read(nonce); err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(gcm.Seal(nonce, nonce, []byte(value), nil)), nil
}
func (s *Store) Decrypt(value sql.NullString) (string, error) {
	if !value.Valid || value.String == "" {
		return "", nil
	}
	data, err := base64.URLEncoding.DecodeString(value.String)
	if err != nil {
		return "", err
	}
	block, err := aes.NewCipher(s.key)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	if len(data) < gcm.NonceSize() {
		return "", errors.New("invalid encrypted credential")
	}
	plain, err := gcm.Open(nil, data[:gcm.NonceSize()], data[gcm.NonceSize():], nil)
	return string(plain), err
}
func (s *Store) Credential(provider string) (*Credential, error) {
	query := `SELECT provider,api_key_encrypted,secret_encrypted,account_identifier_encrypted,host,port,client_id,data_feed FROM provider_credentials `
	var row *sql.Row
	if provider == "" {
		row = s.DB.QueryRow(query + "WHERE enabled=true ORDER BY id LIMIT 1")
	} else {
		row = s.DB.QueryRow(query+"WHERE provider=$1", provider)
	}
	c := &Credential{}
	err := row.Scan(&c.Provider, &c.APIKey, &c.Secret, &c.Account, &c.Host, &c.Port, &c.ClientID, &c.Feed)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	return c, err
}
func Env(name, fallback string) string {
	if v := os.Getenv(name); v != "" {
		return v
	}
	return fallback
}
func EnvInt(name string, fallback int) int {
	v, err := strconv.Atoi(os.Getenv(name))
	if err != nil {
		return fallback
	}
	return v
}
func DefaultProvider() string {
	if BuildEdition == "alpaca" {
		return "ALPACA"
	}
	return strings.ToUpper(Env("DATA_PROVIDER", "IBKR"))
}
func (s *Store) Alpaca(c *Credential) (alpaca.Credentials, error) {
	if c == nil || c.Provider != "ALPACA" {
		return alpaca.Credentials{}, errors.New("Alpaca is not configured")
	}
	key, err := s.Decrypt(c.APIKey)
	if err != nil {
		return alpaca.Credentials{}, err
	}
	secret, err := s.Decrypt(c.Secret)
	if err != nil {
		return alpaca.Credentials{}, err
	}
	feed := Env("ALPACA_FEED", "indicative")
	if c.Feed.Valid {
		feed = c.Feed.String
	}
	return alpaca.Credentials{APIKey: key, Secret: secret, Feed: feed, BaseURL: Env("ALPACA_BASE_URL", "https://data.alpaca.markets")}, nil
}
