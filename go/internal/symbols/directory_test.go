package symbols

import (
	"strings"
	"testing"
)

func TestParse(t *testing.T) {
	input := "Symbol|Security Name|Test Issue\nAAPL|Apple Inc. - Common Stock|N\nFAKE|Example|Y\n"
	entries, err := Parse(strings.NewReader(input))
	if err != nil || entries["AAPL"].Name != "Apple Inc." || len(entries) != 1 {
		t.Fatalf("unexpected entries: %v %v", entries, err)
	}
}
