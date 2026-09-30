package api

import "testing"

func TestCustomValidationAndVersionIdentity(t *testing.T) {
	p := customInput{Name: " Test ", Enabled: true, Policy: "STRICT", Components: []componentInput{{"aapl", 60}, {" nvda ", 40}}}
	if err := validateCustom(&p); err != nil || p.Name != "Test" || p.Components[0].Symbol != "AAPL" {
		t.Fatalf("normalization failed: %+v %v", p, err)
	}
	old := &customConfig{customInput: p, Version: 2}
	p.Enabled = false
	if !sameCustom(old, p) {
		t.Fatal("enable toggle must preserve calculation version")
	}
	p.Components = []componentInput{{"NVDA", 40}, {"AAPL", 60}}
	if !sameCustom(old, p) {
		t.Fatal("component order must preserve version")
	}
	p.Components[0].Weight = 41
	if sameCustom(old, p) {
		t.Fatal("weight update must create version")
	}
	p.Components = []componentInput{{"AAPL", 50}, {"aapl", 50}}
	if validateCustom(&p) == nil {
		t.Fatal("duplicate symbols accepted")
	}
}
