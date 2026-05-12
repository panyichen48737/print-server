package main

import (
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
	githubAPI     = "https://api.github.com/repos/panyichen48737/print-server/releases/latest"
	checkInterval = 6 * time.Hour
	userAgent     = "iOSPrintServerUpdateService"
)

type githubRelease struct {
	TagName string `json:"tag_name"`
	Assets  []struct {
		Name               string `json:"name"`
		BrowserDownloadURL string `json:"browser_download_url"`
	} `json:"assets"`
}

type pendingUpdate struct {
	Version string `json:"version"`
	ZipPath string `json:"zip_path"`
}

var (
	mu        sync.Mutex
	pending   *pendingUpdate
	updateDir string
)

func startUpdateChecker(stopCh chan struct{}, appDir string) {
	updateDir = filepath.Join(dataDir(), "update_cache")
	os.MkdirAll(updateDir, 0755)

	// Resume pending update if previously downloaded
	resumePending(appDir)

	go func() {
		ticker := time.NewTicker(checkInterval)
		defer ticker.Stop()

		time.Sleep(10 * time.Second)
		checkAndDownload(appDir)

		for {
			select {
			case <-ticker.C:
				checkAndDownload(appDir)
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
	go checkAndDownload(appDir)
}

func resumePending(appDir string) {
	cacheDir := filepath.Join(dataDir(), "update_cache")
	entries, err := os.ReadDir(cacheDir)
	if err != nil {
		return
	}
	for _, e := range entries {
		if !e.IsDir() && strings.HasPrefix(e.Name(), "update-") && strings.HasSuffix(e.Name(), ".zip") {
			ver := strings.TrimPrefix(strings.TrimSuffix(e.Name(), ".zip"), "update-")
			mu.Lock()
			pending = &pendingUpdate{Version: ver, ZipPath: filepath.Join(cacheDir, e.Name())}
			mu.Unlock()
			log.Printf("Resumed pending update: %s", ver)
			return
		}
	}
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

func checkAndDownload(appDir string) {
	log.Println("Checking for updates from GitHub...")

	current := getCurrentVersion(appDir)

	release, err := fetchLatestRelease()
	if err != nil {
		log.Printf("Update check failed: %v", err)
		return
	}

	ver := strings.TrimPrefix(release.TagName, "v")
	if !versionGreater(ver, current) {
		log.Printf("Already up to date: %s", current)
		return
	}

	var downloadURL string
	for _, a := range release.Assets {
		if strings.HasPrefix(a.Name, "update-") && strings.HasSuffix(a.Name, ".zip") {
			downloadURL = a.BrowserDownloadURL
			break
		}
	}
	if downloadURL == "" {
		log.Println("No update zip found in release")
		return
	}

	dest := filepath.Join(updateDir, fmt.Sprintf("update-%s.zip", ver))

	mu.Lock()
	if pending != nil && pending.ZipPath == dest {
		mu.Unlock()
		log.Printf("Update %s already downloaded", ver)
		return
	}
	mu.Unlock()

	log.Printf("Downloading update %s...", ver)
	if err := downloadFile(downloadURL, dest); err != nil {
		log.Printf("Download failed: %v", err)
		return
	}

	mu.Lock()
	// Cleanup old pending zips (except the new one)
	oldPending := pending
	if oldPending != nil && oldPending.ZipPath != dest {
		os.Remove(oldPending.ZipPath)
	}
	pending = &pendingUpdate{Version: ver, ZipPath: dest}
	mu.Unlock()

	log.Printf("Update %s ready at %s", ver, dest)
}

func fetchLatestRelease() (*githubRelease, error) {
	req, err := http.NewRequest("GET", githubAPI, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github.v3+json")
	req.Header.Set("User-Agent", userAgent)

	client := &http.Client{Timeout: 15 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var release githubRelease
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return nil, err
	}
	if release.TagName == "" {
		return nil, fmt.Errorf("empty tag_name")
	}
	return &release, nil
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
