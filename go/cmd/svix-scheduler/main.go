package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

type schedule struct {
	name     string
	interval time.Duration
	timeout  time.Duration
}

func run(ctx context.Context, task schedule) {
	commandCtx, cancel := context.WithTimeout(ctx, task.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(commandCtx, http.MethodPost, "http://127.0.0.1:8000/internal/scheduler/"+task.name, nil)
	if err != nil {
		log.Printf("task %s request failed: %v", task.name, err)
		return
	}
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		if commandCtx.Err() == nil {
			log.Printf("task %s failed: %v", task.name, err)
		}
		return
	}
	defer response.Body.Close()
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		log.Printf("task %s failed: HTTP %d", task.name, response.StatusCode)
	}
}

func loop(ctx context.Context, task schedule) {
	run(ctx, task)
	ticker := time.NewTicker(task.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			run(ctx, task)
		}
	}
}

func waitForMigrations(ctx context.Context) bool {
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		if _, err := os.Stat("/run/svix/migrations-complete"); err == nil {
			return true
		}
		select {
		case <-ctx.Done():
			return false
		case <-ticker.C:
		}
	}
}

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	log.Printf("svix Go scheduler waiting for database migrations")
	if !waitForMigrations(ctx) {
		return
	}
	tasks := []schedule{
		{name: "market", interval: 10 * time.Second, timeout: 45 * time.Minute},
		{name: "jobs", interval: 5 * time.Second, timeout: 6 * time.Hour},
		{name: "maintenance", interval: 15 * time.Second, timeout: 2 * time.Hour},
	}
	for _, task := range tasks {
		go loop(ctx, task)
	}
	log.Printf("svix Go scheduler started")
	<-ctx.Done()
	log.Printf("svix Go scheduler stopped")
}
