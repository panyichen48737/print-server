package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const (
	manifestURL    = "https://panyichen48737.github.io/print-server/update.json"
	checkInterval  = 6 * time.Hour
	userAgent      = "iOSPrintServerUpdateService"
)

type manifestData struct {
	LatestVersion string `json:"latest_version"`
	ReleaseURL    string `json:"release_url"`
	ReleaseNotes  string `json:"release_notes"`
	DownloadURL   struct {
		Incremental string `json:"incremental"`
		Full        string `json:"full"`
	} `json:"download_url"`
	SHA256 struct {
		Incremental string `json:"incremental"`
		Full        string `json:"full"`
	} `json:"sha256"`
}

type pendingUpdate struct {
	Version      string `json:"version"`
	ZipPath      string `json:"zip_path"`
	DownloadType string `json:"download_type"` // "incremental" | "full"
}

var (
	mu        sync.Mutex
	pending   *pendingUpdate
	updateDir string
)

func startUpdateChecker(stopCh chan struct{}, appDir string) {
	updateDir = filepath.Join(dataDir(), "update_cache")
	os.MkdirAll(updateDir, 0755)

	// Resume pending update if previously saved
	resumePending()

	go func() {
		ticker := time.NewTicker(checkInterval)
		defer ticker.Stop()

		time.Sleep(10 * time.Second)
		checkAndDownloadWithRetry(appDir)

		for {
			select {
			case <-ticker.C:
				checkAndDownloadWithRetry(appDir)
			case <-stopCh:
				return
			}
		}
	}()
}

func getPendingUpdate() *pendingUpdate {
	mu.Lock()
	defer mu.Unlock()
	return pending
}

func triggerCheck(appDir string) {
	go checkAndDownloadWithRetry(appDir)
}

func writePendingJSON(p *pendingUpdate) {
	path := filepath.Join(updateDir, "pending.json")
	data, err := json.Marshal(p)
	if err != nil {
		log.Printf("Failed to marshal pending.json: %v", err)
		return
	}
	if err := os.WriteFile(path, data, 0644); err != nil {
		log.Printf("Failed to write pending.json: %v", err)
	}
}

func removePendingJSON() {
	os.Remove(filepath.Join(updateDir, "pending.json"))
}

func resumePending() {
	path := filepath.Join(updateDir, "pending.json")
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	var p pendingUpdate
	if err := json.Unmarshal(data, &p); err != nil {
		log.Printf("Failed to parse pending.json: %v", err)
		os.Remove(path)
		return
	}
	// Verify the file still exists on disk
	if _, err := os.Stat(p.ZipPath); os.IsNotExist(err) {
		log.Printf("Pending update file missing: %s", p.ZipPath)
		os.Remove(path)
		return
	}
	mu.Lock()
	pending = &p
	mu.Unlock()
	log.Printf("Resumed pending update: %s (%s)", p.Version, p.DownloadType)
}

func getCurrentVersion(appDir string) string {
	paths := []string{
		filepath.Join(appDir, "_internal", "version_info.json"),
		filepath.Join(appDir, "resources", "version_info.json"),
	}
	for _, p := range paths {
		data, err := os.ReadFile(p)
		if err != nil {
			continue
		}
		var info struct {
			AppVersion string `json:"app_version"`
		}
		if json.Unmarshal(data, &info) == nil && info.AppVersion != "" {
			return strings.TrimPrefix(info.AppVersion, "v")
		}
	}
	return "0.0.0"
}

// checkAndDownloadWithRetry calls checkAndDownload, retrying on failure
// with backoff: 1min -> 5min -> 15min.
func checkAndDownloadWithRetry(appDir string) {
	delays := []time.Duration{1 * time.Minute, 5 * time.Minute, 15 * time.Minute}
	for i := 0; ; i++ {
		if checkAndDownload(appDir) {
			return
		}
		if i >= len(delays) {
			log.Println("All retry attempts exhausted, will retry at next scheduled interval")
			return
		}
		log.Printf("Retrying update check in %v...", delays[i])
		time.Sleep(delays[i])
	}
}

// checkAndDownload returns true on success, false on failure.
func checkAndDownload(appDir string) bool {
	log.Println("Checking for updates from manifest...")

	current := getCurrentVersion(appDir)

	manifest, err := fetchManifest()
	if err != nil {
		log.Printf("Update check failed: %v", err)
		return false
	}

	ver := strings.TrimPrefix(manifest.LatestVersion, "v")
	if !versionGreater(ver, current) {
		log.Printf("Already up to date: %s", current)
		return true
	}

	// Pick incremental first, fall back to full installer
	var downloadURL, downloadType string
	if manifest.DownloadURL.Incremental != "" {
		downloadURL = manifest.DownloadURL.Incremental
		downloadType = "incremental"
	} else if manifest.DownloadURL.Full != "" {
		downloadURL = manifest.DownloadURL.Full
		downloadType = "full"
	} else {
		log.Println("No download URL found in manifest")
		return false
	}

	ext := ".zip"
	if downloadType == "full" {
		ext = ".exe"
	}
	dest := filepath.Join(updateDir, fmt.Sprintf("update-%s%s", ver, ext))

	// Check if already downloaded
	mu.Lock()
	if pending != nil && pending.ZipPath == dest && pending.DownloadType == downloadType {
		mu.Unlock()
		log.Printf("Update %s already downloaded", ver)
		return true
	}
	mu.Unlock()

	log.Printf("Downloading update %s (%s)...", ver, downloadType)
	if err := downloadFile(downloadURL, dest); err != nil {
		log.Printf("Download failed: %v", err)
		return false
	}

	// SHA256 verification
	expectedSHA, hasSHA := manifest.SHA256.Incremental, false
	if downloadType == "incremental" && manifest.SHA256.Incremental != "" {
		hasSHA = true
	} else if downloadType == "full" && manifest.SHA256.Full != "" {
		expectedSHA = manifest.SHA256.Full
		hasSHA = true
	}
	if hasSHA {
		if err := verifySHA256(dest, expectedSHA); err != nil {
			log.Printf("SHA256 verification failed: %v, removing corrupt file", err)
			os.Remove(dest)
			return false
		}
		log.Println("SHA256 verification passed")
	} else {
		log.Println("No SHA256 in manifest, skipping verification")
	}

	mu.Lock()
	// Cleanup old pending file (different version)
	oldPending := pending
	if oldPending != nil && oldPending.ZipPath != dest {
		os.Remove(oldPending.ZipPath)
	}
	p := &pendingUpdate{Version: ver, ZipPath: dest, DownloadType: downloadType}
	pending = p
	writePendingJSON(p)
	mu.Unlock()

	log.Printf("Update %s ready (%s)", ver, downloadType)
	return true
}

func fetchManifest() (*manifestData, error) {
	req, err := http.NewRequest("GET", manifestURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", userAgent)

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("manifest returned HTTP %d", resp.StatusCode)
	}

	var m manifestData
	if err := json.NewDecoder(resp.Body).Decode(&m); err != nil {
		return nil, err
	}
	if m.LatestVersion == "" {
		return nil, fmt.Errorf("empty latest_version in manifest")
	}
	return &m, nil
}

func downloadFile(url, dest string) error {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("User-Agent", userAgent)

	client := &http.Client{Timeout: 300 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	tmp := dest + ".tmp"
	f, err := os.Create(tmp)
	if err != nil {
		return err
	}
	defer f.Close()

	if _, err := io.Copy(f, resp.Body); err != nil {
		f.Close()
		os.Remove(tmp)
		return err
	}
	f.Close()
	return os.Rename(tmp, dest)
}

func verifySHA256(path, expectedHex string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return err
	}
	got := fmt.Sprintf("%x", h.Sum(nil))
	if !strings.EqualFold(got, expectedHex) {
		return fmt.Errorf("SHA256 mismatch: got %s, expected %s", got, expectedHex)
	}
	return nil
}

func versionGreater(a, b string) bool {
	pa := parseInts(strings.Split(a, "."))
	pb := parseInts(strings.Split(b, "."))
	for i := range max(len(pa), len(pb)) {
		va := 0
		vb := 0
		if i < len(pa) {
			va = pa[i]
		}
		if i < len(pb) {
			vb = pb[i]
		}
		if va != vb {
			return va > vb
		}
	}
	return false
}

func parseInts(parts []string) []int {
	r := make([]int, 0, len(parts))
	for _, s := range parts {
		var n int
		fmt.Sscanf(s, "%d", &n)
		r = append(r, n)
	}
	return r
}
