package main

import (
	"archive/zip"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

func runUpdate(zipPath, exePath, appDir string) {
	internalDir := filepath.Join(appDir, "_internal")
	backupDir := filepath.Join(appDir, "_internal.bak")
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

	// Step 2: Backup current _internal/
	log.Println("Backing up _internal/...")
	if _, err := os.Stat(internalDir); err == nil {
		os.RemoveAll(backupDir)
		if err := os.Rename(internalDir, backupDir); err != nil {
			log.Printf("Backup failed: %v", err)
			logToFile(updateLog, "更新失败：备份 _internal/ 失败")
			return
		}
	}

	// Step 3: Extract new _internal/ from zip
	log.Println("Extracting update...")
	if err := extractZip(zipPath, appDir); err != nil {
		log.Printf("Extract failed: %v", err)
		rollback(internalDir, backupDir, updateLog)
		return
	}
	log.Println("Extraction complete")

	// Step 4: Start new version
	log.Println("Starting new version...")
	cmd := exec.Command(exePath)
	cmd.Dir = appDir
	if err := cmd.Start(); err != nil {
		log.Printf("Start failed: %v", err)
		rollback(internalDir, backupDir, updateLog)
		return
	}

	// Step 5: Wait 10s and verify new process is still running
	time.Sleep(10 * time.Second)
	if !isProcessRunning("iOSPrintServer.exe") {
		log.Println("New process crashed, rolling back")
		rollback(internalDir, backupDir, updateLog)
		exec.Command(exePath).Start()
		logToFile(updateLog, "更新失败：新版启动后崩溃，已回滚")
		return
	}

	// Step 6: Cleanup
	os.RemoveAll(backupDir)
	os.Remove(zipPath)

	log.Println("Update completed successfully")
	logToFile(updateLog, "✅ 更新成功！")
}

func rollback(internalDir, backupDir, updateLog string) {
	os.RemoveAll(internalDir)
	if _, err := os.Stat(backupDir); err == nil {
		if err := os.Rename(backupDir, internalDir); err != nil {
			log.Printf("Rollback rename failed: %v", err)
		}
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
