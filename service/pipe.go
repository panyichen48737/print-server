package main

import (
	"encoding/json"
	"io"
	"log"
	"net"
	"os"
	"path/filepath"
)

const listenAddr = "127.0.0.1:48273"

type request struct {
	Cmd     string `json:"cmd"`
	ZipPath string `json:"zip_path,omitempty"`
	ExePath string `json:"exe_path,omitempty"`
	AppDir  string `json:"app_dir,omitempty"`
}

type response struct {
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

func servePipe(stopCh chan struct{}) {
	listener, err := net.Listen("tcp", listenAddr)
	if err != nil {
		log.Printf("Failed to listen on %s: %v", listenAddr, err)
		return
	}
	log.Printf("Listening on %s", listenAddr)

	go func() {
		<-stopCh
		listener.Close()
	}()

	for {
		conn, err := listener.Accept()
		if err != nil {
			select {
			case <-stopCh:
				return
			default:
				log.Printf("Accept error: %v", err)
				continue
			}
		}
		go handleConn(conn)
	}
}

func handleConn(conn net.Conn) {
	defer conn.Close()

	data, err := io.ReadAll(conn)
	if err != nil {
		log.Printf("Read error: %v", err)
		return
	}

	var req request
	if err := json.Unmarshal(data, &req); err != nil {
		writeJSON(conn, response{Status: "error", Message: "invalid JSON"})
		return
	}

	switch req.Cmd {
	case "STATUS":
		writeJSON(conn, response{Status: "ok", Message: "running"})
	case "APPLY":
		handleApply(conn, &req)
	default:
		writeJSON(conn, response{Status: "error", Message: "unknown cmd: " + req.Cmd})
	}
}

func handleApply(conn net.Conn, req *request) {
	appDir := req.AppDir
	if appDir == "" {
		appDir = "C:\\Program Files\\iOSPrintServer"
	}
	exePath := req.ExePath
	if exePath == "" {
		exePath = filepath.Join(appDir, "iOSPrintServer.exe")
	}

	if _, err := os.Stat(req.ZipPath); os.IsNotExist(err) {
		writeJSON(conn, response{Status: "error", Message: "zip not found: " + req.ZipPath})
		return
	}

	writeJSON(conn, response{Status: "ok", Message: "update accepted"})

	go runUpdate(req.ZipPath, exePath, appDir)
}

func writeJSON(conn net.Conn, resp response) {
	data, _ := json.Marshal(resp)
	conn.Write(data)
}
