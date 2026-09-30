package market

import (
	"embed"
	"encoding/csv"
	"errors"
	"fmt"
	"sort"
	"sync"
	"time"
)

//go:embed nyse_sessions.csv
var calendarFS embed.FS

type Session struct {
	Date  string
	Open  time.Time
	Close time.Time
}

type Status struct {
	State              string     `json:"state"`
	IsCollectionWindow bool       `json:"is_collection_window"`
	SessionDate        *string    `json:"session_date"`
	MarketOpen         *time.Time `json:"market_open"`
	MarketClose        *time.Time `json:"market_close"`
	CollectionEnd      *time.Time `json:"collection_end"`
	NextOpen           *time.Time `json:"next_open"`
}

var once sync.Once
var sessions []Session
var byDate map[string]Session
var loadError error

func load() error {
	once.Do(func() {
		file, err := calendarFS.Open("nyse_sessions.csv")
		if err != nil {
			loadError = err
			return
		}
		defer file.Close()
		rows, err := csv.NewReader(file).ReadAll()
		if err != nil || len(rows) < 2 {
			loadError = errors.New("NYSE session calendar unavailable")
			return
		}
		byDate = make(map[string]Session, len(rows)-1)
		for _, row := range rows[1:] {
			if len(row) != 3 {
				loadError = errors.New("invalid NYSE calendar row")
				return
			}
			opened, openErr := time.Parse(time.RFC3339, row[1])
			closed, closeErr := time.Parse(time.RFC3339, row[2])
			if openErr != nil || closeErr != nil || !closed.After(opened) {
				loadError = fmt.Errorf("invalid NYSE session %s", row[0])
				return
			}
			session := Session{Date: row[0], Open: opened, Close: closed}
			sessions = append(sessions, session)
			byDate[row[0]] = session
		}
	})
	return loadError
}

func Bounds(date string) (time.Time, time.Time, bool) {
	if load() != nil {
		return time.Time{}, time.Time{}, false
	}
	session, ok := byDate[date]
	if !ok {
		return time.Time{}, time.Time{}, false
	}
	return session.Open, session.Close.Add(30 * time.Minute), true
}

func Current(now time.Time) (Status, error) {
	if err := load(); err != nil {
		return Status{}, err
	}
	ny, err := time.LoadLocation("America/New_York")
	if err != nil {
		return Status{}, err
	}
	now = now.UTC()
	localDate := now.In(ny).Format("2006-01-02")
	if localDate < "2020-01-01" || localDate > "2040-12-31" {
		return Status{}, errors.New("NYSE calendar date is outside the supported range")
	}
	index := sort.Search(len(sessions), func(i int) bool { return sessions[i].Date >= localDate })
	var display *Session
	if index < len(sessions) && sessions[index].Date == localDate {
		display = &sessions[index]
	} else if index > 0 {
		display = &sessions[index-1]
	}
	status := Status{State: "CLOSED"}
	if display != nil {
		date, opened, closed := display.Date, display.Open, display.Close
		end := closed.Add(30 * time.Minute)
		status.SessionDate, status.MarketOpen, status.MarketClose, status.CollectionEnd = &date, &opened, &closed, &end
	}
	for i := index; i < len(sessions); i++ {
		if sessions[i].Open.After(now) {
			opened := sessions[i].Open
			status.NextOpen = &opened
			break
		}
	}
	if index >= len(sessions) || sessions[index].Date != localDate {
		return status, nil
	}
	session := sessions[index]
	switch {
	case now.Before(session.Open):
		status.State = "PRE_MARKET"
	case !now.After(session.Close):
		status.State, status.IsCollectionWindow = "OPEN", true
	case !now.After(session.Close.Add(30 * time.Minute)):
		status.State, status.IsCollectionWindow = "POST_CLOSE_DELAY", true
	}
	return status, nil
}

func Previous(date string) (string, bool) {
	if load() != nil {
		return "", false
	}
	i := sort.Search(len(sessions), func(i int) bool { return sessions[i].Date >= date })
	if i == 0 {
		return "", false
	}
	return sessions[i-1].Date, true
}
func SessionsAgo(date, older string) int {
	if load() != nil || older > date {
		return 0
	}
	first := sort.Search(len(sessions), func(i int) bool { return sessions[i].Date >= older })
	last := sort.Search(len(sessions), func(i int) bool { return sessions[i].Date > date })
	n := last - first - 1
	if n < 0 {
		return 0
	}
	return n
}
