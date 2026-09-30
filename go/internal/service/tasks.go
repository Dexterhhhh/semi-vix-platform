package service

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/alpaca"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/market"
)

func (s *Service) Collect(ctx context.Context, now time.Time) (map[string]any, error) {
	status, err := market.Current(now)
	if err != nil {
		return nil, err
	}
	if !status.IsCollectionWindow || status.SessionDate == nil {
		return map[string]any{"status": "SKIPPED", "reason": "market_closed", "market": status}, nil
	}
	conn, locked, err := s.lock(ctx, "svix_market_collection")
	if err != nil {
		return nil, err
	}
	if !locked {
		return map[string]any{"status": "SKIPPED", "reason": "collection_running"}, nil
	}
	defer unlock(conn, "svix_market_collection")
	interval := 60
	if err = s.setting(ctx, "intraday_refresh_seconds", &interval); err != nil {
		return nil, err
	}
	interval = max(60, min(3600, interval))
	var latestID int
	var started time.Time
	var finished sql.NullTime
	var latestStatus string
	var retry sql.NullInt64
	err = s.DB.QueryRowContext(ctx, "SELECT id,started_at,finished_at,status,retry_after_seconds FROM market_collection_runs WHERE session_date=$1 ORDER BY started_at DESC,id DESC LIMIT 1", *status.SessionDate).Scan(&latestID, &started, &finished, &latestStatus, &retry)
	if err != nil && err != sql.ErrNoRows {
		return nil, err
	}
	if err == nil {
		if latestStatus == "RUNNING" {
			if started.After(now.Add(-time.Duration(max(1800, interval*2)) * time.Second)) {
				return map[string]any{"status": "SKIPPED", "reason": "collection_running"}, nil
			}
			if _, err = s.DB.ExecContext(ctx, "UPDATE market_collection_runs SET status='FAILED',finished_at=$1,error_message='stale collection run' WHERE id=$2", now, latestID); err != nil {
				return nil, err
			}
		}
		delay := interval
		if latestStatus == "FAILED" || latestStatus == "NO_VALID_DATA" {
			rows, e := s.DB.QueryContext(ctx, "SELECT status FROM market_collection_runs WHERE session_date=$1 ORDER BY started_at DESC,id DESC LIMIT 4", *status.SessionDate)
			if e != nil {
				return nil, e
			}
			failures := 0
			for rows.Next() {
				var state string
				if e = rows.Scan(&state); e != nil {
					rows.Close()
					return nil, e
				}
				if state != "FAILED" && state != "NO_VALID_DATA" {
					break
				}
				failures++
			}
			e = rows.Err()
			rows.Close()
			if e != nil {
				return nil, e
			}
			delay = max(interval, min(300, 60*(1<<max(0, failures-1))))
		}
		next := started.Add(time.Duration(delay) * time.Second)
		if finished.Valid && retry.Valid {
			retryAt := finished.Time.Add(time.Duration(retry.Int64) * time.Second)
			if retryAt.After(next) {
				next = retryAt
			}
		}
		if next.After(now) {
			return map[string]any{"status": "SKIPPED", "reason": "interval_not_due", "next_due": next, "market": status}, nil
		}
	}
	var id int
	err = s.DB.QueryRowContext(ctx, `INSERT INTO market_collection_runs(session_date,status,interval_minutes,interval_seconds,stock_quotes_saved,option_quotes_saved,symbols_succeeded,symbols_failed,started_at) VALUES($1,'RUNNING',$2,$3,0,0,0,0,$4) RETURNING id`, *status.SessionDate, (interval+59)/60, interval, now).Scan(&id)
	if err != nil {
		return nil, err
	}
	summary, err := s.collectQuotes(ctx)
	if err != nil {
		_, _ = s.DB.ExecContext(context.Background(), "UPDATE market_collection_runs SET status='FAILED',finished_at=now(),error_message='Market collection failed' WHERE id=$1", id)
		return nil, err
	}
	runStatus := "COMPLETED"
	if summary.OptionQuotesSaved == 0 {
		runStatus = "NO_VALID_DATA"
	} else if summary.SymbolsFailed > 0 || len(summary.Errors) > 0 {
		runStatus = "PARTIAL"
	}
	calculation := "PENDING"
	if summary.OptionQuotesSaved == 0 {
		calculation = "NO_VALID_DATA"
	}
	encodedStatus, _ := json.Marshal(summary.SymbolStatus)
	encodedErrors, _ := json.Marshal(summary.Errors)
	_, err = s.DB.ExecContext(ctx, `UPDATE market_collection_runs SET status=$1,finished_at=$2,stock_quotes_saved=$3,option_quotes_saved=$4,symbols_succeeded=$5,symbols_failed=$6,batch_id=$7,symbol_status=$8,collection_errors=$9,retry_after_seconds=$10,calculation_status=$11 WHERE id=$12`, runStatus, summary.FinishedAt, summary.StockQuotesSaved, summary.OptionQuotesSaved, summary.SymbolsSucceeded, summary.SymbolsFailed, summary.BatchID, string(encodedStatus), string(encodedErrors), summary.RetryAfterSeconds, calculation, id)
	if err != nil {
		return nil, err
	}
	if summary.OptionQuotesSaved > 0 {
		_, err = s.Observation(ctx, summary.BatchID)
		if err != nil {
			_, _ = s.DB.ExecContext(context.Background(), "UPDATE market_collection_runs SET calculation_status='FAILED',error_message='Observation calculation failed' WHERE id=$1", id)
		}
		// Custom series share the same persisted input. Their failure does not discard the observation.
		day, _ := time.Parse("2006-01-02", *status.SessionDate)
		_, historyErr := s.History(ctx, day, day, "daily", false)
		if historyErr != nil && err == nil {
			err = historyErr
		}
	}
	result := map[string]any{"status": runStatus, "market": status, "interval_seconds": interval, "batch_id": summary.BatchID, "option_quotes_saved": summary.OptionQuotesSaved, "stock_quotes_saved": summary.StockQuotesSaved}
	return result, err
}
func (s *Service) collectQuotes(ctx context.Context) (alpaca.CollectionSummary, error) {
	credential, err := s.Providers.Credential("")
	if err != nil {
		return alpaca.CollectionSummary{}, err
	}
	provider, err := s.Provider(ctx)
	if err != nil {
		return alpaca.CollectionSummary{}, err
	}
	names, err := s.Symbols(ctx, true)
	if err != nil {
		return alpaca.CollectionSummary{}, err
	}
	if provider == "ALPACA" {
		credentials, err := s.Providers.Alpaca(credential)
		if err != nil {
			return alpaca.CollectionSummary{}, err
		}
		client, err := alpaca.NewClient(credentials)
		if err != nil {
			return alpaca.CollectionSummary{}, err
		}
		return client.Collect(ctx, s.DB, names, 120)
	}
	payload, err := json.Marshal(map[string]any{"symbols": names})
	if err != nil {
		return alpaca.CollectionSummary{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, "http://127.0.0.1:8000/internal/providers/collect", bytes.NewReader(payload))
	if err != nil {
		return alpaca.CollectionSummary{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	response, err := http.DefaultClient.Do(req)
	if err != nil {
		return alpaca.CollectionSummary{}, errors.New("vendor SDK bridge unavailable")
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return alpaca.CollectionSummary{}, errors.New("vendor SDK collection failed")
	}
	var result alpaca.CollectionSummary
	err = json.NewDecoder(response.Body).Decode(&result)
	return result, err
}
func jobError(err error) string {
	message := err.Error()
	switch {
	case strings.Contains(message, "credentials or market-data"):
		return "Alpaca 凭据无效，或账户无权访问所请求的历史数据"
	case strings.Contains(message, "Alpaca"):
		return "Alpaca 历史数据服务暂时不可用"
	default:
		return "历史计算失败，请检查数据源后重试"
	}
}
func (s *Service) PendingJob(ctx context.Context) (map[string]any, error) {
	conn, locked, err := s.lock(ctx, "svix_historical_job")
	if err != nil {
		return nil, err
	}
	if !locked {
		return map[string]any{"status": "IDLE"}, nil
	}
	defer unlock(conn, "svix_historical_job")
	// Owning the session lock proves no Go worker is still executing an abandoned job.
	if _, err = s.DB.ExecContext(ctx, "UPDATE calculation_jobs SET status='PENDING',progress=0,started_at=NULL,error_message=NULL WHERE status='RUNNING'"); err != nil {
		return nil, err
	}
	// A durable atomic claim prevents API retries and multiple workers taking the same job.
	var id int
	var start, end time.Time
	var frequency string
	err = s.DB.QueryRowContext(ctx, `UPDATE calculation_jobs SET status='RUNNING',progress=10,started_at=now(),error_message=NULL WHERE id=(SELECT id FROM calculation_jobs WHERE status='PENDING' ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id,start_date,end_date,frequency`).Scan(&id, &start, &end, &frequency)
	if err == sql.ErrNoRows {
		return map[string]any{"status": "IDLE"}, nil
	}
	if err != nil {
		return nil, err
	}
	result, err := s.runJob(ctx, id, start, end, frequency)
	if err != nil {
		failCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_, _ = s.DB.ExecContext(failCtx, "UPDATE calculation_jobs SET status='FAILED',progress=100,finished_at=now(),error_message=$1 WHERE id=$2", jobError(err), id)
	}
	return result, err
}
func (s *Service) runJob(ctx context.Context, id int, start, end time.Time, frequency string) (map[string]any, error) {
	credential, err := s.Providers.Credential("")
	if err != nil {
		return nil, err
	}
	backfill := alpaca.BackfillSummary{}
	if credential != nil && credential.Provider == "ALPACA" {
		credentials, err := s.Providers.Alpaca(credential)
		if err != nil {
			return nil, err
		}
		client, err := alpaca.NewClient(credentials)
		if err != nil {
			return nil, err
		}
		names, err := s.Symbols(ctx, true)
		if err != nil {
			return nil, err
		}
		if _, err = s.DB.ExecContext(ctx, "UPDATE calculation_jobs SET progress=15,result_summary=$1 WHERE id=$2", `{"stage":"正在下载历史行情"}`, id); err != nil {
			return nil, err
		}
		backfill, err = client.Backfill(ctx, s.DB, start, end, names, "")
		if err != nil {
			return nil, err
		}
		if _, err = s.DB.ExecContext(ctx, "UPDATE calculation_jobs SET progress=85,result_summary=$1 WHERE id=$2", `{"stage":"正在计算 SVIX"}`, id); err != nil {
			return nil, err
		}
	}
	summary, err := s.History(ctx, start, end, frequency, false)
	if err != nil {
		return nil, err
	}
	finalStatus := "COMPLETED"
	if summary.Records == 0 {
		finalStatus = "NO_VALID_DATA"
	} else if summary.Skipped > 0 {
		finalStatus = "PARTIAL"
	}
	encoded, _ := json.Marshal(map[string]any{"stock_rows": backfill.StockRows, "option_rows": backfill.OptionRows, "records_calculated": summary.Records, "estimated_records": summary.Estimated, "skipped_records": summary.Skipped, "stage": "已完成"})
	_, err = s.DB.ExecContext(ctx, "UPDATE calculation_jobs SET status=$1,progress=100,finished_at=now(),result_summary=$2 WHERE id=$3", finalStatus, string(encoded), id)
	return map[string]any{"job_id": id, "status": finalStatus, "records_calculated": summary.Records}, err
}
