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
const svcDisplayName = "iOS打印服务器更新服务"

func dataDir() string {
	programData := os.Getenv("ProgramData")
	if programData == "" {
		programData = "C:\\ProgramData"
	}
	return filepath.Join(programData, "iOSPrintServer")
}

func main() {
	exe, _ := os.Executable()
	appDir := filepath.Dir(exe)

	// Write logs and cache to %ProgramData%/iOSPrintServer/
	dd := dataDir()
	logDir := filepath.Join(dd, "logs")
	os.MkdirAll(logDir, 0755)

	logFile, _ := os.OpenFile(
		filepath.Join(logDir, "update_service.log"),
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
			// Clean up service data
			os.RemoveAll(dataDir())
			return
		}
	}

	log.Println("Service starting...")
	if err := svc.Run(svcName, &handler{appDir: appDir}); err != nil {
		log.Fatalf("Service failed: %v", err)
	}
	log.Println("Service stopped.")
}

func installService(exePath string) {
	m, err := mgr.Connect()
	if err != nil {
		fmt.Fprintf(os.Stderr, "连接服务控制管理器失败: %v\n", err)
		os.Exit(1)
	}
	defer m.Disconnect()

	// Remove existing service first (handles re-install/update)
	if old, err := m.OpenService(svcName); err == nil {
		old.Control(svc.Stop)
		old.Delete()
		old.Close()
	}

	s, err := m.CreateService(svcName, exePath, mgr.Config{
		DisplayName:      svcDisplayName,
		Description:      "处理 iOS打印服务器自动更新（下载、原子替换、回滚）",
		StartType:        mgr.StartAutomatic,
		DelayedAutoStart: true,
	})
	if err != nil {
		fmt.Fprintf(os.Stderr, "创建服务失败: %v\n", err)
		os.Exit(1)
	}
	defer s.Close()

	if err := s.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "启动服务失败: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("服务安装并启动成功。")
}

func uninstallService() {
	m, err := mgr.Connect()
	if err != nil {
		fmt.Fprintf(os.Stderr, "连接服务控制管理器失败: %v\n", err)
		os.Exit(1)
	}
	defer m.Disconnect()

	s, err := m.OpenService(svcName)
	if err != nil {
		fmt.Fprintf(os.Stderr, "服务未找到: %v\n", err)
		os.Exit(1)
	}
	defer s.Close()

	s.Control(svc.Stop)

	if err := s.Delete(); err != nil {
		fmt.Fprintf(os.Stderr, "删除服务失败: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("服务卸载成功。")
}
