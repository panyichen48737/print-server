package main

import (
	"archive/zip"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func runUpdate(zipPath, exePath, appDir string) {
	// Determine update type from file extension
	isFull := strings.HasSuffix(strings.ToLower(zipPath), ".exe")

	if isFull {
		log.Printf("Starting full installer update: %s", zipPath)
		cmd := exec.Command(zipPath, "/S")
		cmd.Dir = appDir
		if err := cmd.Start(); err != nil {
			log.Printf("Failed to start installer: %v", err)
			logToFile(filepath.Join(appDir, "update.log"),
				fmt.Sprintf("更新失败：无法启动安装器 - %v", err))
			return
		}
		log.Println("Installer launched, exiting update service...")
		time.Sleep(1 * time.Second)
		os.Exit(0)
		return
	}

	internalDir := filepath.Join(appDir, "_internal")
	backupDir := filepath.Join(appDir, "_internal.bak")
	exeBak := exePath + ".bak"
	svcBak := filepath.Join(appDir, "update_service.exe.bak")
	updateLog := filepath.Join(appDir, "update.log")

	log.Printf("Starting update: zip=%s, exe=%s, appDir=%s", zipPath, exePath, appDir)

	// Step 1: Wait for main process to exit
	log.Println("Waiting for main process to exit...")
	if err := waitForProcessExit("iOSPrintServer.exe", 60*time.Second); err != nil {
		log.Printf("Timeout waiting for process exit: %v", err)
		logToFile(updateLog, "更新失败：等待进程退出超时")
		return
	}
	log.Println("Main process exited")

	// Step 2: Backup files that could be overwritten
	log.Println("Backing up current files...")
	backups := backupFile(internalDir, backupDir)
	backups += backupFile(exePath, exeBak)
	backups += backupFile(filepath.Join(appDir, "update_service.exe"), svcBak)
	log.Printf("Backed up %d items", backups)

	// Step 3: Extract zip to appDir (overwrites _internal/, exe, resources, etc.)
	log.Println("Extracting update...")
	if err := extractZip(zipPath, appDir); err != nil {
		log.Printf("Extract failed: %v", err)
		restoreAll(internalDir, backupDir, exePath, exeBak, svcBak, appDir)
		logToFile(updateLog, fmt.Sprintf("更新失败：解压错误 - %v", err))
		return
	}
	log.Println("Extraction complete")

	// Step 4: Start new version
	log.Println("Starting new version...")
	cmd := exec.Command(exePath)
	cmd.Dir = appDir
	if err := cmd.Start(); err != nil {
		log.Printf("Start failed: %v", err)
		restoreAll(internalDir, backupDir, exePath, exeBak, svcBak, appDir)
		logToFile(updateLog, fmt.Sprintf("更新失败：无法启动新版 - %v", err))
		return
	}

	// Step 5: Wait 10s and verify new process is still running
	time.Sleep(10 * time.Second)
	if !isProcessRunning("iOSPrintServer.exe") {
		log.Println("New process crashed, rolling back")
		restoreAll(internalDir, backupDir, exePath, exeBak, svcBak, appDir)
		exec.Command(exePath).Start()
		logToFile(updateLog, "更新失败：新版启动后崩溃，已回滚")
		return
	}

	// Step 6: Cleanup
	os.RemoveAll(backupDir)
	os.Remove(exeBak)
	os.Remove(svcBak)
	os.Remove(zipPath)

	log.Println("Update completed successfully")
	logToFile(updateLog, "✅ 更新成功！")
}

func backupFile(src, dst string) int {
	if _, err := os.Stat(src); os.IsNotExist(err) {
		return 0
	}
	os.RemoveAll(dst)
	if err := os.Rename(src, dst); err != nil {
		log.Printf("Backup of %s failed: %v", src, err)
		return 0
	}
	return 1
}

func restoreAll(internalDir, backupDir, exePath, exeBak, svcBak, appDir string) {
	// Restore _internal/
	os.RemoveAll(internalDir)
	if _, err := os.Stat(backupDir); err == nil {
		if err := os.Rename(backupDir, internalDir); err != nil {
			log.Printf("Rollback _internal/ failed: %v", err)
		}
	}
	// Restore exe
	if _, err := os.Stat(exeBak); err == nil {
		os.Remove(exePath)
		os.Rename(exeBak, exePath)
	}
	// Restore update_service.exe
	svcPath := filepath.Join(appDir, "update_service.exe")
	if _, err := os.Stat(svcBak); err == nil {
		os.Remove(svcPath)
		os.Rename(svcBak, svcPath)
	}
}

func waitForProcessExit(name string, timeout time.Duration) error {
	deadline := time.After(timeout)
	for {
		select {
		case <-deadline:
			return os.ErrDeadlineExceeded
		default:
		}
		if !isProcessRunning(name) {
			return nil
		}
		time.Sleep(500 * time.Millisecond)
	}
}

func isProcessRunning(name string) bool {
	cmd := exec.Command("tasklist", "/FI", "IMAGENAME eq "+name, "/NH")
	output, err := cmd.Output()
	if err != nil {
		return false
	}
	return strings.Contains(string(output), name)
}

func extractZip(src, destDir string) error {
	r, err := zip.OpenReader(src)
	if err != nil {
		return err
	}
	defer r.Close()

	for _, f := range r.File {
		fpath := filepath.Join(destDir, f.Name)
		if !strings.HasPrefix(filepath.Clean(fpath), filepath.Clean(destDir)+string(os.PathSeparator)) {
			continue // zip slip prevention
		}
		if f.FileInfo().IsDir() {
			os.MkdirAll(fpath, 0755)
			continue
		}
		os.MkdirAll(filepath.Dir(fpath), 0755)

		rc, err := f.Open()
		if err != nil {
			return err
		}
		outFile, err := os.OpenFile(fpath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {
			rc.Close()
			return err
		}
		_, err = io.Copy(outFile, rc)
		outFile.Close()
		rc.Close()
		if err != nil {
			return err
		}
	}
	return nil
}

func logToFile(path, msg string) {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	f.WriteString(time.Now().Format("2006-01-02 15:04:05") + " " + msg + "\n")
}
