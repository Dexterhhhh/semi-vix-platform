package providers

// BuildEdition is set at compilation. Runtime environment variables cannot add absent SDKs.
var BuildEdition = "full"

func Supported() []string {
	if BuildEdition == "alpaca" {
		return []string{"ALPACA"}
	}
	return []string{"ALPACA", "IBKR", "FUTU"}
}

func Available(provider string) bool {
	for _, p := range Supported() {
		if p == provider {
			return true
		}
	}
	return false
}
