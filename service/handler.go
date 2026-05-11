package main

import (
	"log"
	"os"
	"path/filepath"

	"golang.org/x/sys/windows/svc"
)

type handler struct{}

func (h *handler) Execute(args []string, requests <-chan svc.ChangeRequest, changes chan<- svc.Status) (bool, uint32) {
	const cmdsAccepted = svc.AcceptStop | svc.AcceptShutdown
	changes <- svc.Status{State: svc.StartPending}

	// Determine app directory from own exe path
	exe, _ := os.Executable()
	appDir := filepath.Dir(exe)

	stopCh := make(chan struct{})
	go servePipe(stopCh)
	startUpdateChecker(stopCh, appDir)

	// Start watchdog
	wd := NewWatchdog()
	setWatchdog(wd)
	wd.Start(appDir)

	changes <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}
	log.Println("Service is running, pipe listener, update checker and watchdog active")

	for {
		select {
		case c := <-requests:
			switch c.Cmd {
			case svc.Interrogate:
				changes <- c.CurrentStatus
			case svc.Stop, svc.Shutdown:
				log.Println("Service stopping...")
				wd.Stop()
				close(stopCh)
				changes <- svc.Status{State: svc.StopPending}
				return false, uint32(0)
			}
		}
	}
}