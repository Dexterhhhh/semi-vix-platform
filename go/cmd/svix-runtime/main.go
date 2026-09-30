// svix-runtime is the container's Go process manager and schema initializer.
package main

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/Dexterhhhh/semi-vix-platform/go/internal/auth"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/database"
	"github.com/Dexterhhhh/semi-vix-platform/go/internal/providers"
	"github.com/lib/pq"
)

type process struct {
	name string
	cmd  *exec.Cmd
	done chan struct{}
}
type exitEvent struct {
	name string
	err  error
}

func healthy(address string) bool {
	client := http.Client{Timeout: 3 * time.Second}
	response, err := client.Get(address)
	if err != nil {
		return false
	}
	defer response.Body.Close()
	return response.StatusCode == 200
}

func initialize(ctx context.Context) error {
	u := &url.URL{Scheme: "postgres", Host: "127.0.0.1:5432", User: url.UserPassword(os.Getenv("POSTGRES_USER"), os.Getenv("POSTGRES_PASSWORD")), Path: "/postgres"}
	q := url.Values{"sslmode": {"disable"}}
	u.RawQuery = q.Encode()
	db, err := sql.Open("postgres", u.String())
	if err != nil {
		return err
	}
	defer db.Close()
	for {
		if db.PingContext(ctx) == nil {
			break
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Second):
		}
	}
	name := os.Getenv("POSTGRES_DB")
	var exists bool
	if err = db.QueryRowContext(ctx, "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)", name).Scan(&exists); err != nil {
		return err
	}
	if !exists {
		if _, err = db.ExecContext(ctx, "CREATE DATABASE "+pq.QuoteIdentifier(name)+" OWNER "+pq.QuoteIdentifier(os.Getenv("POSTGRES_USER"))); err != nil {
			return err
		}
	}
	u.Path = "/" + name
	dsn := u.String()
	// Only the optional SDK bridge uses SQLAlchemy's driver-qualified scheme.
	os.Setenv("DATABASE_URL", strings.Replace(dsn, "postgres://", "postgresql+psycopg://", 1))
	appDB, err := sql.Open("postgres", dsn)
	if err != nil {
		return err
	}
	defer appDB.Close()
	if err = database.Migrate(ctx, appDB); err != nil {
		return err
	}
	a, err := auth.New(dsn)
	if err != nil {
		return err
	}
	defer a.Database().Close()
	if err = a.Bootstrap(ctx); err != nil {
		return err
	}
	return os.WriteFile("/run/svix/migrations-complete", []byte("ready\n"), 0644)
}

func run() error {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	exits := make(chan exitEvent, 8)
	children := []process{}
	var ready atomic.Bool
	start := func(name, user string, args ...string) error {
		command := exec.Command("gosu", append([]string{user}, args...)...)
		command.Stdout = os.Stdout
		command.Stderr = os.Stderr
		command.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
		if err := command.Start(); err != nil {
			return err
		}
		done := make(chan struct{})
		children = append(children, process{name, command, done})
		go func() { err := command.Wait(); close(done); exits <- exitEvent{name, err} }()
		log.Printf("%s started", name)
		return nil
	}
	defer func() {
		ready.Store(false)
		// Stop dependants before PostgreSQL so their final transactions can finish.
		for i := len(children) - 1; i >= 0; i-- {
			child := children[i]
			signal := syscall.SIGTERM
			if child.name == "postgres" {
				signal = syscall.SIGINT
			}
			if child.name == "nginx" {
				signal = syscall.SIGQUIT
			}
			_ = syscall.Kill(-child.cmd.Process.Pid, signal)
			select {
			case <-child.done:
			case <-time.After(10 * time.Second):
				_ = syscall.Kill(-child.cmd.Process.Pid, syscall.SIGKILL)
			}
		}
	}()
	if err := start("postgres", "postgres", "/usr/lib/postgresql/16/bin/postgres", "-D", os.Getenv("PGDATA"), "-c", "listen_addresses=127.0.0.1", "-c", "unix_socket_directories=/var/run/postgresql"); err != nil {
		return err
	}
	initCtx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()
	if err := initialize(initCtx); err != nil {
		return fmt.Errorf("database initialization: %w", err)
	}
	if err := start("go-engine", "svix", "/usr/local/bin/svix-engine"); err != nil {
		return err
	}
	if providers.BuildEdition == "full" {
		if err := start("sdk-bridge", "svix", "/usr/local/bin/uvicorn", "app.bridge:app", "--app-dir", "/opt/svix/backend", "--host", "127.0.0.1", "--port", "8000"); err != nil {
			return err
		}
	}
	if err := start("scheduler", "svix", "/usr/local/bin/svix-scheduler"); err != nil {
		return err
	}
	if err := start("nginx", "root", "/usr/sbin/nginx", "-g", "daemon off;"); err != nil {
		return err
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		if !ready.Load() || !healthy("http://127.0.0.1:8090/ready") || providers.BuildEdition == "full" && !healthy("http://127.0.0.1:8000/health") {
			http.Error(w, "not ready", 503)
			return
		}
		fmt.Fprintln(w, "ok")
	})
	server := &http.Server{Addr: "127.0.0.1:8091", Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	defer server.Close()
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			exits <- exitEvent{"runtime-health", err}
		}
	}()
	ready.Store(true)
	log.Printf("Semi-VIX %s runtime initialized", providers.BuildEdition)
	select {
	case <-ctx.Done():
		return nil
	case event := <-exits:
		return fmt.Errorf("%s exited: %v", event.name, event.err)
	}
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--healthcheck" {
		if !healthy("http://127.0.0.1:8091/health") {
			os.Exit(1)
		}
		return
	}
	if err := run(); err != nil {
		log.Printf("runtime stopped: %v", err)
		os.Exit(1)
	}
}
