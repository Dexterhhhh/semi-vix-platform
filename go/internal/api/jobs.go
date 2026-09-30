package api

import (
	"database/sql"
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
)

type Job struct {
	ID            int        `json:"id"`
	Type          string     `json:"type"`
	StartDate     string     `json:"start_date"`
	EndDate       string     `json:"end_date"`
	Frequency     string     `json:"frequency"`
	Status        string     `json:"status"`
	Progress      int        `json:"progress"`
	ResultSummary any        `json:"result_summary"`
	CreatedAt     time.Time  `json:"created_at"`
	StartedAt     *time.Time `json:"started_at"`
	FinishedAt    *time.Time `json:"finished_at"`
	ErrorMessage  *string    `json:"error_message"`
}

type rowScanner interface{ Scan(...any) error }

func scanJob(row rowScanner) (Job, error) {
	var job Job
	var start, end time.Time
	var summary, message sql.NullString
	var started, finished sql.NullTime
	err := row.Scan(&job.ID, &job.Type, &start, &end, &job.Frequency, &job.Status,
		&job.Progress, &summary, &job.CreatedAt, &started, &finished, &message)
	if err != nil {
		return job, err
	}
	job.StartDate, job.EndDate = start.Format("2006-01-02"), end.Format("2006-01-02")
	if summary.Valid {
		_ = json.Unmarshal([]byte(summary.String), &job.ResultSummary)
	}
	if started.Valid {
		value := started.Time.UTC()
		job.StartedAt = &value
	}
	if finished.Valid {
		value := finished.Time.UTC()
		job.FinishedAt = &value
	}
	if message.Valid {
		job.ErrorMessage = &message.String
	}
	return job, nil
}

const jobColumns = `id,type,start_date,end_date,frequency,status,progress,result_summary,created_at,started_at,finished_at,error_message`

type JobsHandler struct{ auth *auth.Handler }

func NewJobsHandler(authHandler *auth.Handler) *JobsHandler { return &JobsHandler{auth: authHandler} }

func (h *JobsHandler) get(id int) (Job, error) {
	return scanJob(h.auth.Database().QueryRow("SELECT "+jobColumns+" FROM calculation_jobs WHERE id=$1", id))
}

func (h *JobsHandler) create(w http.ResponseWriter, r *http.Request) {
	var body struct {
		StartDate string `json:"start_date"`
		EndDate   string `json:"end_date"`
		Frequency string `json:"frequency"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&body) != nil {
		invalid(w, 422, "Invalid calculation request")
		return
	}
	start, err := time.Parse("2006-01-02", body.StartDate)
	if err != nil {
		invalid(w, 422, "Invalid start date")
		return
	}
	end, err := time.Parse("2006-01-02", body.EndDate)
	if err != nil || end.Before(start) {
		invalid(w, 422, "end_date must not be before start_date")
		return
	}
	if body.Frequency == "" {
		body.Frequency = "daily"
	}
	if body.Frequency != "daily" && body.Frequency != "weekly" {
		invalid(w, 422, "Invalid frequency")
		return
	}
	db := h.auth.Database()
	var alpaca bool
	if err := db.QueryRow("SELECT EXISTS(SELECT 1 FROM provider_credentials WHERE provider='ALPACA' AND enabled=true)").Scan(&alpaca); err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	if alpaca && start.Before(time.Date(2024, 2, 1, 0, 0, 0, 0, time.UTC)) {
		invalid(w, 422, "Alpaca 期权历史数据仅支持 2024-02-01 之后的日期")
		return
	}
	tx, err := db.BeginTx(r.Context(), nil)
	if err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	defer tx.Rollback()
	if _, err = tx.ExecContext(r.Context(), "SELECT pg_advisory_xact_lock(hashtext('svix_job_configuration'))"); err != nil {
		invalid(w, 503, "Database unavailable")
		return
	}
	var duplicate int
	err = tx.QueryRowContext(r.Context(), `SELECT id FROM calculation_jobs WHERE type='HISTORICAL_SVIX' AND start_date=$1
        AND end_date=$2 AND frequency=$3 AND status IN ('PENDING','RUNNING') LIMIT 1`, start, end, body.Frequency).Scan(&duplicate)
	if err == nil {
		invalid(w, 409, "相同范围的历史计算任务 #"+strconv.Itoa(duplicate)+" 已在运行")
		return
	}
	if err != sql.ErrNoRows {
		invalid(w, 503, "Database unavailable")
		return
	}
	var id int
	err = tx.QueryRowContext(r.Context(), `INSERT INTO calculation_jobs
        (type,start_date,end_date,frequency,status,progress,created_at)
        VALUES ('HISTORICAL_SVIX',$1,$2,$3,'PENDING',0,now()) RETURNING id`, start, end, body.Frequency).Scan(&id)
	if err != nil {
		invalid(w, 503, "Calculation job could not be queued")
		return
	}
	if err = tx.Commit(); err != nil {
		invalid(w, 503, "Calculation job could not be queued")
		return
	}
	job, err := h.get(id)
	if err != nil {
		invalid(w, 503, "Calculation job unavailable")
		return
	}
	respond(w, 202, job)
}

func (h *JobsHandler) list(w http.ResponseWriter, r *http.Request) {
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 || parsed > 100 {
			invalid(w, 422, "Invalid limit")
			return
		}
		limit = parsed
	}
	rows, err := h.auth.Database().Query("SELECT "+jobColumns+" FROM calculation_jobs ORDER BY created_at DESC LIMIT $1", limit)
	if err != nil {
		invalid(w, 503, "Calculation jobs unavailable")
		return
	}
	defer rows.Close()
	jobs := []Job{}
	for rows.Next() {
		job, err := scanJob(rows)
		if err != nil {
			invalid(w, 503, "Calculation jobs unavailable")
			return
		}
		jobs = append(jobs, job)
	}
	if err = rows.Err(); err != nil {
		invalid(w, 503, "Calculation jobs unavailable")
		return
	}
	respond(w, 200, jobs)
}

func (h *JobsHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !h.auth.Authorize(w, r) {
		return
	}
	path := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/api/jobs"), "/")
	if path == "" && r.Method == http.MethodGet {
		h.list(w, r)
		return
	}
	if path == "/create" && r.Method == http.MethodPost {
		h.create(w, r)
		return
	}
	parts := strings.Split(strings.TrimPrefix(path, "/"), "/")
	id, err := strconv.Atoi(parts[0])
	if err != nil || id < 1 {
		invalid(w, 404, "Calculation job not found")
		return
	}
	if len(parts) == 2 && parts[1] == "retry" && r.Method == http.MethodPost {
		job, err := h.get(id)
		if err == sql.ErrNoRows {
			invalid(w, 404, "Calculation job not found")
			return
		}
		if err != nil {
			invalid(w, 503, "Calculation job unavailable")
			return
		}
		if job.Status != "DISPATCH_FAILED" && job.Status != "FAILED" && job.Status != "NO_VALID_DATA" {
			invalid(w, 409, "只有分发失败、执行失败或无有效数据的任务可以重试")
			return
		}
		result, err := h.auth.Database().Exec(`UPDATE calculation_jobs SET status='PENDING',progress=0,
            started_at=NULL,finished_at=NULL,error_message=NULL WHERE id=$1 AND status IN ('DISPATCH_FAILED','FAILED','NO_VALID_DATA')`, id)
		if err != nil {
			invalid(w, 503, "Calculation job unavailable")
			return
		}
		if n, _ := result.RowsAffected(); n == 0 {
			invalid(w, 409, "任务状态已改变，请刷新后重试")
			return
		}
		updated, err := h.get(id)
		if err != nil {
			invalid(w, 503, "Calculation job unavailable")
			return
		}
		respond(w, 202, updated)
		return
	}
	if len(parts) == 1 && r.Method == http.MethodGet {
		job, err := h.get(id)
		if err == sql.ErrNoRows {
			invalid(w, 404, "Calculation job not found")
			return
		}
		if err != nil {
			invalid(w, 503, "Calculation job unavailable")
			return
		}
		respond(w, 200, job)
		return
	}
	invalid(w, http.StatusMethodNotAllowed, "Method not allowed")
}
