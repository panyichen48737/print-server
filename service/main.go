package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"

	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

const svcName = "iOSPrintServerUpdateSvc"
const svcDisplayName = "iOS 云打印服务器更新服务"

func main() {
	exe, _ := os.Executable()
	logFile, _ := os.OpenFile(
		filepath.Join(filepath.Dir(exe), "update_service.log"),
		os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644,
	)
	if logFile != nil {
		log.SetOutput(logFile)
		defer logFile.Close()
	}

	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "--install":
			installService(exe)
			return
		case "--uninstall":
			uninstallService()
			return
		}
	}

	log.Println("Service starting...")
	if err := svc.Run(svcName, &handler{}); err != nil {
		log.Fatalf("Service failed: %v", err)
	}
	log.Println("Service stopped.")
}

func installService(exePath string) {
	m, err := mgr.Connect()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to connect to SCM: %v\n", err)
		os.Exit(1)
	}
	defer m.Disconnect()

	s, err := m.CreateService(svcName, exePath, mgr.Config{
		DisplayName:      svcDisplayName,
		Description:      "处理 iOSPrintServer 自动更新（下载、原子替换、回滚）",
		StartType:        mgr.StartAutomatic,
		DelayedAutoStart: true,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create service: %v\n", err)
		os.Exit(1)
	}
	defer s.Close()

	if err := s.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to start service: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Service installed and started successfully.")
}

func uninstallService() {
	m, err := mgr.Connect()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to connect to SCM: %v\n", err)
		os.Exit(1)
	}
	defer m.Disconnect()

	s, err := m.OpenService(svcName)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Service not found: %v\n", err)
		os.Exit(1)
	}
	defer s.Close()

	s.Control(svc.Stop)

	if err := s.Delete(); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to delete service: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Service uninstalled successfully.")
}
