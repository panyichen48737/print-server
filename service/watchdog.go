package main

import (
	"fmt"
	"log"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

type Watchdog struct {
	mu          sync.Mutex
	registered  bool
	port        int
	stopCh      chan struct{}
	stopOnce    sync.Once
	lastRestart time.Time
	logFile     *os.File
}

func NewWatchdog() *Watchdog {
	return &Watchdog{
		stopCh:      make(chan struct{}),
		lastRestart: time.Now().Add(-30 * time.Second), // allow immediate first check
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
		ticker := time.NewTicker(5 * time.Second)
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
	w.logf("started (5s interval)")
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
	return port > 0 && w.backendListening(port)
}

func (w *Watchdog) check(appDir string) {
	w.mu.Lock()
	reg := w.registered
	port := w.port
	sinceRestart := time.Since(w.lastRestart)
	w.mu.Unlock()
	if !reg {
		return
	}

	// Grace period after restart: backend needs time to start
	if sinceRestart < 15*time.Second {
		return
	}

	if !isProcessRunning("iOSPrintServer.exe") {
		w.logf("iOSPrintServer.exe crashed, restarting...")
		w.restartApp(appDir)
		return
	}

	// Process is alive but backend port is down — kill & restart
	if port > 0 && !w.backendListening(port) {
		w.logf("backend unreachable, killing and restarting...")
		exec.Command("taskkill", "/F", "/IM", "iOSPrintServer.exe").Run()
		time.Sleep(2 * time.Second)
		w.restartApp(appDir)
	}
}

func (w *Watchdog) backendListening(port int) bool {
	conn, err := net.DialTimeout("tcp", "127.0.0.1:"+itoa(port), 2*time.Second)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

func (w *Watchdog) restartApp(appDir string) {
	exePath := filepath.Join(appDir, "iOSPrintServer.exe")
	cmd := exec.Command(exePath, "--tray")
	cmd.Dir = appDir
	if err := cmd.Start(); err != nil {
		w.logf("restart failed: %v", err)
	} else {
		w.mu.Lock()
		w.lastRestart = time.Now()
		w.mu.Unlock()
		w.logf("restart initiated")
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var buf [12]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	return string(buf[i:])
}