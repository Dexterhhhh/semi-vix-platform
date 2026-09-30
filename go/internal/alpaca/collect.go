package alpaca

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

type CollectionError struct {
	Symbol  string `json:"symbol"`
	Code    string `json:"code"`
	Message string `json:"message"`
}

type CollectionSummary struct {
	Provider          string                       `json:"provider"`
	StartedAt         time.Time                    `json:"started_at"`
	FinishedAt        time.Time                    `json:"finished_at"`
	SymbolsRequested  int                          `json:"symbols_requested"`
	BatchID           string                       `json:"batch_id"`
	SymbolsSucceeded  int                          `json:"symbols_succeeded"`
	SymbolsFailed     int                          `json:"symbols_failed"`
	StockQuotesSaved  int                          `json:"stock_quotes_saved"`
	OptionQuotesSaved int                          `json:"option_quotes_saved"`
	Errors            []CollectionError            `json:"errors"`
	SymbolStatus      map[string]map[string]string `json:"symbol_status"`
	RetryAfterSeconds *int                         `json:"retry_after_seconds"`
}

func batchID() (string, error) {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "", err
	}
	value[6] = value[6]&0x0f | 0x40
	value[8] = value[8]&0x3f | 0x80
	encoded := hex.EncodeToString(value)
	return fmt.Sprintf("%s-%s-%s-%s-%s", encoded[:8], encoded[8:12], encoded[12:16], encoded[16:20], encoded[20:]), nil
}

func saveStockSnapshot(ctx context.Context, db *sql.DB, quote StockQuote, batch string) error {
	_, err := db.ExecContext(ctx, `INSERT INTO stock_snapshot
        (timestamp,provider,symbol,price,bid,ask,volume,delayed,feed,price_type,received_at,batch_id,trade_timestamp)
        VALUES ($1,'ALPACA',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)`,
		quote.Timestamp, quote.Symbol, quote.Price, quote.Bid, quote.Ask, quote.Volume,
		quote.Delayed, quote.Feed, quote.PriceType, time.Now().UTC(), batch, quote.TradeTimestamp)
	return err
}

func saveOptionSnapshots(ctx context.Context, db *sql.DB, quotes []OptionQuote, batch string) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	statement, err := tx.PrepareContext(ctx, `INSERT INTO option_snapshot
        (timestamp,provider,contract_id,symbol,expiry,strike,option_type,bid,ask,last,volume,open_interest,implied_volatility,delayed,feed,price_type,received_at,batch_id,trade_timestamp)
        VALUES ($1,'ALPACA',$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)`)
	if err != nil {
		return err
	}
	defer statement.Close()
	for _, quote := range quotes {
		_, err := statement.ExecContext(ctx, quote.Timestamp, quote.ContractID, quote.Symbol, quote.Expiry,
			quote.Strike, quote.OptionType, quote.Bid, quote.Ask, quote.Last, quote.Volume,
			quote.OpenInterest, quote.ImpliedVol, quote.Delayed, quote.Feed, quote.PriceType,
			time.Now().UTC(), batch, quote.TradeTimestamp)
		if err != nil {
			return err
		}
	}
	return tx.Commit()
}

func (c *Client) Collect(ctx context.Context, db *sql.DB, symbols []string, maxContracts int) (CollectionSummary, error) {
	id, err := batchID()
	if err != nil {
		return CollectionSummary{}, err
	}
	result := CollectionSummary{Provider: "ALPACA", StartedAt: time.Now().UTC(), SymbolsRequested: len(symbols),
		BatchID: id, Errors: []CollectionError{}, SymbolStatus: map[string]map[string]string{}}
	for _, original := range symbols {
		symbol := strings.ToUpper(strings.TrimSpace(original))
		result.SymbolStatus[symbol] = map[string]string{"stock": "FAILED", "options": "PENDING"}
		snapshot, sourceError := c.Snapshot(ctx, symbol, maxContracts, time.Now().UTC())
		if snapshot.Stock != nil {
			if err := saveStockSnapshot(ctx, db, *snapshot.Stock, id); err != nil {
				return result, err
			}
			result.StockQuotesSaved++
			result.SymbolStatus[symbol]["stock"] = "SAVED"
		}
		if sourceError == nil && len(snapshot.Options) > 0 {
			if err := saveOptionSnapshots(ctx, db, snapshot.Options, id); err != nil {
				return result, err
			}
			result.OptionQuotesSaved += len(snapshot.Options)
			result.SymbolsSucceeded++
			result.SymbolStatus[symbol]["options"] = "SAVED"
		} else {
			result.SymbolsFailed++
			result.SymbolStatus[symbol]["options"] = "FAILED"
			code := "OPTION_CHAIN_UNAVAILABLE"
			if sourceError != nil {
				code = "OPTION_COLLECTION_UNAVAILABLE"
			}
			result.Errors = append(result.Errors, CollectionError{Symbol: symbol, Code: code, Message: code})
		}
		for _, code := range snapshot.Errors {
			result.Errors = append(result.Errors, CollectionError{Symbol: symbol, Code: code, Message: code})
		}
		if sourceError != nil && (strings.Contains(sourceError.Error(), "rate limit") || strings.Contains(sourceError.Error(), "credentials or market-data")) {
			pause := 300
			result.RetryAfterSeconds = &pause
			break
		}
	}
	result.FinishedAt = time.Now().UTC()
	return result, nil
}
