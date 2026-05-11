package main

import (
	"log"
	"net"
	"os/exec"
	"path/filepath"
	"sync"
	"time"
)

type Watchdog struct {
	mu         sync.Mutex
	registered bool
	port       int
	stopCh     chan struct{}
}

func NewWatchdog() *Watchdog {
	return &Watchdog{stopCh: make(chan struct{})}
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
	log.Println("Watchdog started (5s interval)")
}

func (w *Watchdog) Stop() {
	close(w.stopCh)
}

func (w *Watchdog) Register(port int) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.registered = true
	w.port = port
	log.Printf("Watchdog: registered (port %d)", port)
}

func (w *Watchdog) Unregister() {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.registered = false
	log.Println("Watchdog: unregistered")
}

func (w *Watchdog) BackendHealth() bool {
	w.mu.Lock()
	port := w.port
	w.mu.Unlock()
	if port == 0 {
		return false
	}
	conn, err := net.DialTimeout("tcp", "127.0.0.1:"+itoa(port), 2*time.Second)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

func (w *Watchdog) check(appDir string) {
	w.mu.Lock()
	reg := w.registered
	w.mu.Unlock()
	if !reg {
		return
	}

	if !isProcessRunning("iOSPrintServer.exe") {
		log.Println("Watchdog: iOSPrintServer.exe crashed, restarting...")
		exePath := filepath.Join(appDir, "iOSPrintServer.exe")
		cmd := exec.Command(exePath, "--tray")
		cmd.Dir = appDir
		if err := cmd.Start(); err != nil {
			log.Printf("Watchdog: restart failed: %v", err)
		} else {
			log.Println("Watchdog: restart initiated")
		}
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