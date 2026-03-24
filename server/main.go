package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"time"

	"github.com/gin-gonic/gin"
	_ "github.com/mattn/go-sqlite3"
	"github.com/robfig/cron/v3"
)

var (
	db     *sql.DB
	dbPath string
)

type Briefing struct {
	Date        string `json:"date"`
	Hook        string `json:"hook"`
	Situation   string `json:"situation"`
	Actions     string `json:"actions"`
	Financial   string `json:"financial"`
	Close       string `json:"close"`
	SignalCount int    `json:"signal_count"`
	DateSaved   string `json:"date_saved"`
}

type Signal struct {
	Source     string  `json:"source"`
	Content    string  `json:"content"`
	Urgency    float64 `json:"urgency"`
	URRScore   float64 `json:"urr_score"`
	ReceivedAt string  `json:"received_at"`
}

type PipelineStatus struct {
	Status  string `json:"status"`
	Time    string `json:"time"`
	Message string `json:"message,omitempty"`
}

func initDB(path string) error {
	var err error
	db, err = sql.Open("sqlite3", path)
	if err != nil {
		return fmt.Errorf("failed to open db: %w", err)
	}
	return db.Ping()
}

func getLatestBriefing() (*Briefing, error) {
	row := db.QueryRow(
		`SELECT date, narrative, signals_used FROM briefings ORDER BY date DESC LIMIT 1`,
	)
	var dateSaved, narrativeJSON, signalsJSON string
	if err := row.Scan(&dateSaved, &narrativeJSON, &signalsJSON); err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, err
	}

	var b Briefing
	if err := json.Unmarshal([]byte(narrativeJSON), &b); err != nil {
		return nil, err
	}
	b.DateSaved = dateSaved
	return &b, nil
}

func getTodaySignals() ([]Signal, error) {
	today := time.Now().UTC().Format("2006-01-02")
	rows, err := db.Query(
		`SELECT source, content, urgency, urr_score, received_at
		 FROM signals WHERE received_at LIKE ? ORDER BY urr_score DESC`,
		today+"%",
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var signals []Signal
	for rows.Next() {
		var s Signal
		if err := rows.Scan(&s.Source, &s.Content, &s.Urgency, &s.URRScore, &s.ReceivedAt); err != nil {
			continue
		}
		signals = append(signals, s)
	}
	return signals, nil
}

func getBriefingHistory() ([]map[string]interface{}, error) {
	rows, err := db.Query(
		`SELECT date, signals_used FROM briefings ORDER BY date DESC LIMIT 7`,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var history []map[string]interface{}
	for rows.Next() {
		var date, signalsJSON string
		if err := rows.Scan(&date, &signalsJSON); err != nil {
			continue
		}
		var signals []string
		json.Unmarshal([]byte(signalsJSON), &signals)
		history = append(history, map[string]interface{}{
			"date":    date,
			"signals": signals,
		})
	}
	return history, nil
}

func runPython() error {
	rootDir := filepath.Dir(filepath.Dir(os.Args[0]))

	var pythonBin string
	if runtime.GOOS == "windows" {
		pythonBin = "python"
	} else {
		pythonBin = "python3"
	}

	cmd := exec.Command(pythonBin, "run_briefing.py")
	cmd.Dir = rootDir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func triggerPipeline() {
	log.Println("► Pipeline triggered")
	if err := runPython(); err != nil {
		log.Printf("✗ Pipeline error: %v", err)
	} else {
		log.Println("✓ Pipeline complete")
	}
}

func setupRoutes(r *gin.Engine) {
	r.GET("/", func(c *gin.Context) {
		briefing, err := getLatestBriefing()
		if err != nil {
			c.String(http.StatusInternalServerError, "DB error: %v", err)
			return
		}
		c.Header("Content-Type", "text/html")
		c.String(http.StatusOK, renderDashboard(briefing))
	})

	api := r.Group("/api")
	{
		api.GET("/briefing/latest", func(c *gin.Context) {
			briefing, err := getLatestBriefing()
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			if briefing == nil {
				c.JSON(http.StatusNotFound, gin.H{"error": "no briefing found"})
				return
			}
			c.JSON(http.StatusOK, briefing)
		})

		api.GET("/briefing/history", func(c *gin.Context) {
			history, err := getBriefingHistory()
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			c.JSON(http.StatusOK, history)
		})

		api.POST("/briefing/run", func(c *gin.Context) {
			go triggerPipeline()
			c.JSON(http.StatusOK, PipelineStatus{
				Status:  "started",
				Time:    time.Now().UTC().Format(time.RFC3339),
				Message: "pipeline running in background",
			})
		})

		api.GET("/signals/today", func(c *gin.Context) {
			signals, err := getTodaySignals()
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				return
			}
			c.JSON(http.StatusOK, signals)
		})

		api.GET("/health", func(c *gin.Context) {
			c.JSON(http.StatusOK, gin.H{
				"status": "ok",
				"time":   time.Now().UTC().Format(time.RFC3339),
			})
		})
	}
}

func main() {
	rootDir := filepath.Join(filepath.Dir(os.Args[0]), "..")
	dbPath = filepath.Join(rootDir, "data", "sage.db")

	if path := os.Getenv("SAGE_DB_PATH"); path != "" {
		dbPath = path
	}

	if err := initDB(dbPath); err != nil {
		log.Fatalf("✗ DB init failed: %v", err)
	}
	defer db.Close()
	log.Printf(" Connected to %s", dbPath)

	c := cron.New()
	c.AddFunc("0 6 * * *", func() {
		log.Println(" 6am — running morning briefing")
		go triggerPipeline()
	})
	c.Start()
	defer c.Stop()
	log.Println(" Scheduler started — briefing runs at 06:00 daily")

	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()
	setupRoutes(r)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8000"
	}
	
	log.Printf(" SAGE server running → http://localhost:%s", port)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}
