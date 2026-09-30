package providers

import "testing"

func TestEditionProviderBoundary(t *testing.T) {
	previous := BuildEdition
	t.Cleanup(func() { BuildEdition = previous })
	BuildEdition = "alpaca"
	t.Setenv("DATA_PROVIDER", "IBKR")
	if DefaultProvider() != "ALPACA" || !Available("ALPACA") || Available("IBKR") || Available("FUTU") {
		t.Fatal("Alpaca edition exposed unsupported SDKs")
	}
	BuildEdition = "full"
	if !Available("ALPACA") || !Available("IBKR") || !Available("FUTU") {
		t.Fatal("full edition lost providers")
	}
}
