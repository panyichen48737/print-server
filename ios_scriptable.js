// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: blue; icon-glyph: print;
// iOS Cloud Print Server - Scriptable Script

// ===== 配置（按需修改） =====
const SERVER_URL = "https://192.168.1.100:5000";
const API_KEY = "print-server-key-2026";
const POLL_INTERVAL = 3; // 轮询间隔（秒）
const POLL_MAX_RETRIES = 60; // 最大轮询次数（约3分钟）
const ALLOWED_EXTENSIONS = [".doc", ".docx", ".pdf", ".xls", ".xlsx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif", ".heic", ".heif"];
// ===========================

// Get file from share sheet
const args = Arguments;

async function main() {
  const file = getFile();
  if (!file) return;

  // Check file type
  const ext = getExtension(file.name);
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    const alert = new Alert();
    alert.title = "不支持的文件类型";
    alert.message = `文件 "${file.name}" 的类型 (${ext}) 不在允许列表中。\n\n允许的类型: ${ALLOWED_EXTENSIONS.join(", ")}`;
    alert.addOKButton();
    await alert.present();
    return;
  }

  // Upload file
  const jobId = await uploadFile(file);
  if (!jobId) return;

  // Poll status
  await pollStatus(jobId);
}

function getFile() {
  if (args.fileURLs && args.fileURLs.length > 0) {
    const url = args.fileURLs[0];
    const fm = FileManager.local();
    const data = fm.read(url);
    const name = decodeURIComponent(url.split("/").pop().split("?")[0]);
    return { data, name };
  }
  return null;
}

function getExtension(filename) {
  const idx = filename.lastIndexOf(".");
  return idx >= 0 ? filename.substring(idx).toLowerCase() : "";
}

async function uploadFile(file) {
  const url = `${SERVER_URL}/api/print`;

  // Create form data
  const req = new Request(url);
  req.method = "POST";
  req.allowInsecureRequest = true; // 自签名 HTTPS 证书
  req.headers = {
    "Authorization": `Bearer ${API_KEY}`,
    "Content-Type": "multipart/form-data; boundary=----FormBoundary123"
  };

  // Build multipart body
  const boundary = "----FormBoundary123";
  let body = "";
  body += `--${boundary}\r\n`;
  body += `Content-Disposition: form-data; name="file"; filename="${file.name}"\r\n`;
  body += `Content-Type: application/octet-stream\r\n\r\n`;

  const bodyStart = body;
  const bodyEnd = `\r\n--${boundary}--\r\n`;

  // Create combined data
  const fm = FileManager.local();
  const tempPath = fm.joinPath(fm.temporaryDirectory(), `upload_${Date.now()}.dat`);
  const encoder = new TextEncoder();

  // Write boundary + headers
  fm.write(tempPath, encoder.encode(bodyStart));

  // Append file data
  fm.write(tempPath, file.data, true);

  // Append closing boundary
  fm.write(tempPath, encoder.encode(bodyEnd), true);

  // Read complete data
  const requestData = fm.read(tempPath);
  fm.delete(tempPath);

  req.body = requestData;

  // Show progress
  let progress = Progress.create();
  progress.totalUnitCount = 1;
  progress.completedUnitCount = 0;
  progress.localizedDescription = "正在上传文件...";

  try {
    const response = await req.loadJSON();
    progress.completedUnitCount = 1;

    if (response && response.job_id) {
      console.log(`上传成功，任务 ID: ${response.job_id}`);
      return response.job_id;
    } else {
      const alert = new Alert();
      alert.title = "上传失败";
      alert.message = "服务器返回了意外的响应";
      alert.addOKButton();
      await alert.present();
      return null;
    }
  } catch (error) {
    const alert = new Alert();
    alert.title = "上传失败";
    alert.message = `无法连接到服务器: ${error}`;
    alert.addOKButton();
    await alert.present();
    return null;
  }
}

async function pollStatus(jobId) {
  let running = true;
  let retries = 0;

  while (running) {
    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL * 1000));
    retries++;

    const url = `${SERVER_URL}/api/status/${jobId}`;
    const req = new Request(url);
    req.method = "GET";
    req.allowInsecureRequest = true;

    try {
      const response = await req.loadJSON();

      if (!response || !response.status) {
        if (retries >= POLL_MAX_RETRIES) {
          const notification = new Notification();
          notification.title = "⏱ 轮询超时";
          notification.body = "打印任务状态查询超时，请检查服务器";
          notification.sound = "default";
          await notification.schedule();
          running = false;
        }
        continue;
      }

      console.log(`任务状态: ${response.status}`);

      if (response.status === "completed") {
        const notification = new Notification();
        notification.title = "🖨 打印任务已完成！";
        notification.body = "文件已成功发送到打印机";
        notification.sound = "default";
        await notification.schedule();
        running = false;
      } else if (response.status === "failed") {
        const notification = new Notification();
        notification.title = "❌ 打印失败";
        notification.body = response.error || "未知错误";
        notification.sound = "default";
        await notification.schedule();
        running = false;
      }
    } catch (error) {
      console.log(`轮询失败: ${error}`);
    }
  }
}

// Run
await main();
Script.complete();
