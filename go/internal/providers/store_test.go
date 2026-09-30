package providers

import (
	"bytes"
	"database/sql"
	"encoding/base64"
	"testing"
)

func TestCredentialsCiphertextCompatibility(t *testing.T) {
	t.Setenv("CREDENTIAL_MASTER_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
	store, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	// Fixed Python AESGCM output: all-zero key and nonce, no associated data.
	plain, err := store.Decrypt(sql.NullString{String: "AAAAAAAAAAAAAAAAusIzSWATDg11K7EyCj2r_UM5ibWKX5LJ1-Zw", Valid: true})
	if err != nil || plain != "test-secret" {
		t.Fatalf("Python credential compatibility: %q %v", plain, err)
	}
	encrypted, err := store.Encrypt("test-secret")
	if err != nil {
		t.Fatal(err)
	}
	plain, err = store.Decrypt(sql.NullString{String: encrypted, Valid: true})
	if err != nil || plain != "test-secret" {
		t.Fatalf("roundtrip %q %v", plain, err)
	}
	_, err = store.Decrypt(sql.NullString{String: "AAAA", Valid: true})
	if err == nil {
		t.Fatal("accepted truncated ciphertext")
	}
}

func TestExistingStandardBase64Key(t *testing.T) {
	t.Setenv("CREDENTIAL_MASTER_KEY", base64.StdEncoding.EncodeToString(bytes.Repeat([]byte{255}, 32)))
	if _, err := New(nil); err != nil {
		t.Fatalf("Python-compatible standard base64 key rejected: %v", err)
	}
}
