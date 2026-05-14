package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"

	"golang.org/x/sys/windows"
)

const (
	healthCheckInterval = 10 * time.Second
	gracePeriod         = 15 * time.Second
	stableResetPeriod   = 30 * time.Minute
	maxCrashCount       = 3
)

type Watchdog struct {
	mu           sync.Mutex
	registered   bool
	port         int
	stopCh       chan struct{}
	stopOnce     sync.Once
	restartCmd   *exec.Cmd
	lastRestart  time.Time
	backoffLevel int
	lastStable   time.Time
	logFile      *os.File
}

func NewWatchdog() *Watchdog {
	return &Watchdog{
		stopCh:     make(chan struct{}),
		lastStable: time.Now(),
	}
}

func (w *Watchdog) SetLogFile(path string) {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		log.Printf("Watchdog: failed to open log file %s: %v", path, err)
		return
	}
	w.logFile = f
}

func (w *Watchdog) logf(format string, args ...interface{}) {
	msg := fmt.Sprintf(time.Now().Format("2006-01-02 15:04:05")+" [INFO] [Watchdog] "+format, args...)
	if w.logFile != nil {
		w.logFile.WriteString(msg + "\n")
	}
}

func (w *Watchdog) Start(appDir string) {
	go func() {
		ticker := time.NewTicker(healthCheckInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ticker.C:
				w.check(appDir)
			case <-w.stopCh:
				return
			}
		}
	}()
	w.logf("started (%v interval)", healthCheckInterval)
}

func (w *Watchdog) Stop() {
	w.stopOnce.Do(func() {
		close(w.stopCh)
		if w.logFile != nil {
			w.logFile.Close()
		}
	})
}

func (w *Watchdog) Register(port int) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.registered = true
	w.port = port
	w.logf("registered (port %d)", port)
}

func (w *Watchdog) Unregister() {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.registered = false
	w.logf("unregistered")
}

func (w *Watchdog) BackendHealth() bool {
	w.mu.Lock()
	port := w.port
	w.mu.Unlock()
	return port > 0 && w.backendHealthy(port)
}

func (w *Watchdog) check(appDir string) {
	w.mu.Lock()
	reg := w.registered
	port := w.port
	sinceRestart := time.Since(w.lastRestart)
	sinceStable := time.Since(w.lastStable)
	backoff := w.backoffLevel
	restartCmd := w.restartCmd
	w.mu.Unlock()

	if !reg {
		return
	}

	if sinceRestart < gracePeriod {
		return
	}

	// Reset backoff if app has been stable long enough
	if sinceStable > stableResetPeriod && backoff > 0 {
		w.mu.Lock()
		w.backoffLevel = 0
		w.mu.Unlock()
		w.logf("app stable for 30min, reset backoff")
	}

	// Check process: prefer PID-native check, fallback to tasklist
	alive := false
	if restartCmd != nil && restartCmd.Process != nil {
		alive = processExists(restartCmd.Process.Pid)
	} else {
		alive = isProcessRunning("iOSPrintServer.exe")
	}

	if !alive {
		w.logf("iOSPrintServer.exe crashed, restarting...")
		w.recordCrash()
		w.restartWithBackoff(appDir)
		return
	}

	// Process is alive — verify backend health via HTTP
	if port > 0 && !w.backendHealthy(port) {
		w.logf("backend unhealthy (port %d), killing and restarting...", port)
		exec.Command("taskkill", "/F", "/IM", "iOSPrintServer.exe").Run()
		time.Sleep(2 * time.Second)
		w.recordCrash()
		w.restartWithBackoff(appDir)
		return
	}

	// App is fully healthy
	w.mu.Lock()
	w.lastStable = time.Now()
	w.mu.Unlock()
}

func (w *Watchdog) backendHealthy(port int) bool {
	client := &http.Client{Timeout: 3 * time.Second}
	resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%d/api/health", port))
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

func (w *Watchdog) recordCrash() {
	w.mu.Lock()
	defer w.mu.Unlock()

	w.backoffLevel++
	if w.backoffLevel > 3 {
		w.backoffLevel = 3
	}
	w.logf("crash recorded, backoff level %d", w.backoffLevel)
}

func (w *Watchdog) restartWithBackoff(appDir string) {
	w.mu.Lock()
	level := w.backoffLevel
	w.mu.Unlock()

	if level >= 3 {
		w.logf("max restart attempts reached (level 3), stopping watchdog")
		return
	}

	delays := []time.Duration{0, 30 * time.Second, 2 * time.Minute, 10 * time.Minute}
	if level < len(delays) && delays[level] > 0 {
		w.logf("backoff: waiting %v before restart (level %d)", delays[level], level)
		time.Sleep(delays[level])
	}

	w.restartApp(appDir)
}

func (w *Watchdog) restartApp(appDir string) {
	exePath := filepath.Join(appDir, "iOSPrintServer.exe")
	cmd := exec.Command(exePath, "--tray")
	cmd.Dir = appDir
	if err := cmd.Start(); err != nil {
		w.logf("restart failed: %v", err)
	} else {
		w.mu.Lock()
		w.restartCmd = cmd
		w.lastRestart = time.Now()
		w.mu.Unlock()
		w.logf("restart initiated (pid %d)", cmd.Process.Pid)
	}
}

// processExists checks if a process with the given PID is still running
// using Windows native API (no tasklist needed).
func processExists(pid int) bool {
	handle, err := windows.OpenProcess(windows.PROCESS_QUERY_INFORMATION, false, uint32(pid))
	if err != nil {
		return false
	}
	defer windows.CloseHandle(handle)
	var exitCode uint32
	if err := windows.GetExitCodeProcess(handle, &exitCode); err != nil {
		return false
	}
	return exitCode == 259 // STILL_ACTIVE
}
