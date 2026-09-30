package auth

import (
	"bytes"
	"os"
	"testing"
	"time"
)

func TestVerifyPasslibArgon2Hash(t *testing.T) {
	const encoded = "$argon2id$v=19$m=65536,t=3,p=4$dW7N2VvLuVcKobQWgrC2dg$NJETwGvz+/9nyzjLBys5CTzuG5nK+GAbriklv9tt9sc"
	if !VerifyPassword("example", encoded) || VerifyPassword("wrong", encoded) {
		t.Fatal("Go password verification differs from existing Passlib hash")
	}
}

func TestJWTAndEncryptionRoundTrip(t *testing.T) {
	h := &Handler{jwtKey: []byte("test-key"), encryptionKey: bytes.Repeat([]byte{7}, 32)}
	token, err := h.token(1, "temporary", "setup", time.Minute)
	if err != nil {
		t.Fatal(err)
	}
	if id, err := h.verify(token, "temporary", "setup"); err != nil || id != 1 {
		t.Fatalf("temporary token: %d %v", id, err)
	}
	if _, err := h.verify(token, "access", ""); err == nil {
		t.Fatal("temporary token accepted as access token")
	}
	encoded, err := h.encrypt("JBSWY3DPEHPK3PXP")
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := h.decrypt(encoded)
	if err != nil || decoded != "JBSWY3DPEHPK3PXP" {
		t.Fatalf("encrypted secret: %q %v", decoded, err)
	}
}

func TestTOTPMatchesPyOTP(t *testing.T) {
	if !totp("JBSWY3DPEHPK3PXP", "742275", time.Unix(1234567890, 0)) ||
		totp("JBSWY3DPEHPK3PXP", "000000", time.Unix(1234567890, 0)) {
		t.Fatal("TOTP compatibility failure")
	}
}

func TestExistingAdminPasswordIntegration(t *testing.T) {
	if os.Getenv("SVIX_TEST_DATABASE_URL") == "" {
		t.Skip("set SVIX_TEST_DATABASE_URL for PostgreSQL integration")
	}
	h, err := New(os.Getenv("SVIX_TEST_DATABASE_URL"))
	if err != nil {
		t.Fatal(err)
	}
	value, err := h.adminByID(1)
	if err != nil {
		t.Fatal(err)
	}
	if !value.Active || !VerifyPassword(os.Getenv("SVIX_TEST_ADMIN_PASSWORD"), value.Hash) {
		t.Fatalf("existing administrator password not accepted: active=%v", value.Active)
	}
}
