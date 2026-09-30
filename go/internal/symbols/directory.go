package symbols

import (
	"context"
	"encoding/csv"
	"errors"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

var urls = []string{
	"https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
	"https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
}

type ListedSymbol struct {
	Symbol string `json:"symbol"`
	Name   string `json:"name"`
}

type Directory struct {
	mu      sync.Mutex
	entries map[string]ListedSymbol
	expires time.Time
	client  *http.Client
}

func NewDirectory() *Directory {
	return &Directory{client: &http.Client{Timeout: 12 * time.Second}}
}

func Parse(contents io.Reader) (map[string]ListedSymbol, error) {
	reader := csv.NewReader(contents)
	reader.Comma = '|'
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil || len(rows) == 0 {
		return nil, errors.New("invalid symbol directory")
	}
	columns := map[string]int{}
	for index, header := range rows[0] {
		columns[strings.TrimSpace(header)] = index
	}
	field := func(row []string, name string) string {
		if index, ok := columns[name]; ok && index < len(row) {
			return strings.TrimSpace(row[index])
		}
		return ""
	}
	entries := map[string]ListedSymbol{}
	for _, row := range rows[1:] {
		symbol := strings.ToUpper(field(row, "Symbol"))
		if symbol == "" {
			symbol = strings.ToUpper(field(row, "ACT Symbol"))
		}
		name := field(row, "Security Name")
		if symbol == "" || name == "" || strings.EqualFold(field(row, "Test Issue"), "Y") {
			continue
		}
		if strings.HasSuffix(strings.ToLower(name), " - common stock") {
			name = name[:len(name)-len(" - Common Stock")]
		}
		entries[symbol] = ListedSymbol{Symbol: symbol, Name: name}
	}
	return entries, nil
}

func (d *Directory) Lookup(ctx context.Context, symbol string) (ListedSymbol, bool, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	if time.Now().After(d.expires) {
		fresh := map[string]ListedSymbol{}
		for _, url := range urls {
			request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
			if err != nil {
				return ListedSymbol{}, false, err
			}
			response, err := d.client.Do(request)
			if err == nil && response.StatusCode == http.StatusOK {
				var parsed map[string]ListedSymbol
				parsed, err = Parse(response.Body)
				for key, value := range parsed {
					fresh[key] = value
				}
			}
			if response != nil {
				response.Body.Close()
			}
			if err != nil || response == nil || response.StatusCode != http.StatusOK {
				if len(d.entries) == 0 {
					return ListedSymbol{}, false, errors.New("symbol directory unavailable")
				}
				d.expires = time.Now().Add(time.Minute)
				value, ok := d.entries[strings.ToUpper(strings.TrimSpace(symbol))]
				return value, ok, nil
			}
		}
		if len(fresh) == 0 {
			return ListedSymbol{}, false, errors.New("empty symbol directory")
		}
		d.entries = fresh
		d.expires = time.Now().Add(6 * time.Hour)
	}
	value, ok := d.entries[strings.ToUpper(strings.TrimSpace(symbol))]
	return value, ok, nil
}
