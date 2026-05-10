package main

import (
	"log"

	"golang.org/x/sys/windows/svc"
)

type handler struct{}

func (h *handler) Execute(args []string, requests <-chan svc.ChangeRequest, changes chan<- svc.Status) (bool, uint32) {
	const cmdsAccepted = svc.AcceptStop | svc.AcceptShutdown
	changes <- svc.Status{State: svc.StartPending}

	stopCh := make(chan struct{})
	go servePipe(stopCh)

	changes <- svc.Status{State: svc.Running, Accepts: cmdsAccepted}
	log.Println("Service is running, pipe listener active")

	for {
		select {
		case c := <-requests:
			switch c.Cmd {
			case svc.Interrogate:
				changes <- c.CurrentStatus
			case svc.Stop, svc.Shutdown:
				log.Println("Service stopping...")
				close(stopCh)
				changes <- svc.Status{State: svc.StopPending}
				return false, 0
			}
		}
	}
}
