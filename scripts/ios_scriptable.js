// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: blue; icon-glyph: print;
// iOS Cloud Print Server - Scriptable Script

// ===== 配置（在 iPhone 上通过「分享表单」→ Scriptable 使用） =====
// 首次使用前，请将下方 SERVER_URL 改为你的服务器地址
const SERVER_URL = "https://192.168.1.100:5000";      // ← 改成你的服务器地址（支持 https:// 或 http://）
const API_KEY = "print-server-key-2026";              // ← 改成你的 API Key（与 config.json 一致）
const POLL_INTERVAL = 3;                               // 轮询间隔（秒）
const POLL_MAX_RETRIES = 60;                           // 最大轮询次数（约3分钟）
const ALLOWED_EXTENSIONS = [".doc", ".docx", ".pdf", ".xls", ".xlsx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif", ".heic", ".heif"];
// ==============================================================

async function main() {
  const files = getFiles();
  if (!files || files.length === 0) {
    // 手动运行时显示使用说明
    const dialog = new Alert();
    dialog.title = "iOS 云打印";
    dialog.message = "请通过分享表单使用此脚本：\n\n1. 在文件 App 或 Safari 中选择一个或多个文件\n2. 点击分享按钮\n3. 选择「共享」→ Scriptable\n4. 选择此脚本";
    dialog.addOKButton("知道了");
    await dialog.present();
    return;
  }

  // Filter supported files
  const validFiles = [];
  const errors = [];
  for (const file of files) {
    const ext = getExtension(file.name);
    if (ALLOWED_EXTENSIONS.includes(ext)) {
      validFiles.push(file);
    } else {
      errors.push(`"${file.name}" (${ext}) 不支持`);
    }
  }

  if (validFiles.length === 0) {
    const dialog = new Alert();
    dialog.title = "没有可打印的文件";
    dialog.message = `所选文件类型均不在允许列表中。\n\n允许的类型: ${ALLOWED_EXTENSIONS.join(", ")}`;
    if (errors.length > 0) dialog.message += `\n\n${errors.join("\n")}`;
    dialog.addOKButton();
    await dialog.present();
    return;
  }

  if (errors.length > 0) {
    const dialog = new Alert();
    dialog.title = `${errors.length} 个文件被跳过`;
    dialog.message = errors.join("\n") + "\n\n继续打印其余文件？";
    dialog.addAction("继续");
    dialog.addCancelAction("取消");
    const btn = await dialog.present();
    if (btn === -1) return;
  }

  // Show progress
  const total = validFiles.length;
  const dialog = new Alert();
  dialog.title = total > 1 ? `打印 ${total} 个文件` : "正在打印...";
  dialog.message = `正在上传 (0/${total})...`;
  dialog.addCancelAction("取消全部");

  const btnPromise = dialog.present();

  // Upload files sequentially
  const jobIds = [];
  for (let i = 0; i < total; i++) {
    // Check cancel
    const race = await Promise.race([
      btnPromise.then(b => ({ type: 'cancel', btn: b })),
      Promise.resolve({ type: 'continue' })
    ]);
    if (race.type === 'cancel' && race.btn === -1) {
      dialog.dismiss();
      // Cancel already submitted jobs
      for (const jid of jobIds) {
        try { await cancelJob(jid); } catch(e) {}
      }
      const n = new Notification();
      n.title = "⏹ 打印已取消";
      n.body = `已取消 ${total} 个打印任务`;
      n.sound = "default";
      await n.schedule();
      return;
    }

    dialog.message = `正在上传 (${i + 1}/${total}): ${validFiles[i].name}`;

    // Upload single file
    const jobId = await uploadFile(validFiles[i]);
    if (jobId) {
      jobIds.push(jobId);
    }
  }

  // Dismiss the dialog — files are submitted
  dialog.dismiss();

  // Wait for completion
  if (total === 1 && jobIds.length === 1) {
    await waitForCompletion(jobIds[0]);
  } else if (jobIds.length > 0) {
    // Multi-file: wait via polling in background, notify summary
    let completed = 0;
    let failed = 0;
    for (const jid of jobIds) {
      try {
        await waitForCompletionWS(jid);
        completed++;
      } catch (e) {
        if (e.message === 'cancelled') return;
        failed++;
      }
    }
    const n = new Notification();
    if (failed === 0) {
      n.title = `✅ ${completed} 个文件打印完成`;
      n.body = "所有文件已成功发送到打印机";
    } else {
      n.title = `⚠ ${completed} 完成, ${failed} 失败`;
      n.body = "部分文件打印失败，请检查服务器日志";
    }
    n.sound = "default";
    await n.schedule();
  }
}

function getFiles() {
  if (args.fileURLs && args.fileURLs.length > 0) {
    const fm = FileManager.local();
    const files = [];
    for (const url of args.fileURLs) {
      const data = fm.read(url);
      const name = decodeURIComponent(url.split("/").pop().split("?")[0]);
      files.push({ data, name });
    }
    return files;
  }
  return [];
}

function getExtension(filename) {
  const idx = filename.lastIndexOf(".");
  return idx >= 0 ? filename.substring(idx).toLowerCase() : "";
}

async function waitForCompletion(jobId) {
  const dialog = new Alert();
  dialog.title = "🖨 正在打印...";
  dialog.message = "任务已提交，等待打印机响应";
  dialog.addAction("等待完成");
  dialog.addCancelAction("取消打印");

  const btn = await Promise.race([
    dialog.present(),
    new Promise(r => setTimeout(() => r(0), 3000))
  ]);

  if (btn === -1) {
    await cancelJob(jobId);
    const n = new Notification();
    n.title = "⏹ 打印已取消";
    n.body = "打印任务已取消";
    n.sound = "default";
    await n.schedule();
    return;
  }

  try {
    await waitForCompletionWS(jobId);
    const n = new Notification();
    n.title = "✅ 打印完成";
    n.body = "文件已成功发送到打印机";
    n.sound = "default";
    await n.schedule();
  } catch (err) {
    if (err.message === 'cancelled') return;
    await pollStatus(jobId);
  }
}

function waitForCompletionWS(jobId) {
  return new Promise((resolve, reject) => {
    // WebSocket URL: 自动适配 http→ws / https→wss
    const protocol = SERVER_URL.startsWith('https') ? 'wss' : 'ws';
    const baseUrl = SERVER_URL.replace(/^https?:\/\//, '');
    const wsUrl = `${protocol}://${baseUrl}/socket.io/?transport=websocket&EIO=4`;
    const ws = new WebSocket(wsUrl);
    const timeout = setTimeout(() => { ws.close(); reject(new Error('超时')); }, 180000);

    ws.onopen = () => ws.send('40');
    ws.onmessage = (evt) => {
      const msg = evt.data;
      if (msg === '40' || msg === '40/') return;
      if (typeof msg === 'string' && msg.startsWith('42')) {
        try {
          const [eventType, data] = JSON.parse(msg.slice(2));
          if (eventType === 'job_status' && data && data.job_id === jobId) {
            if (data.status === 'completed') {
              clearTimeout(timeout); ws.close(); resolve('completed');
            } else if (data.status === 'failed') {
              clearTimeout(timeout); ws.close();
              reject(new Error(data.error || '打印失败'));
            }
          }
        } catch(e) {}
      }
    };
    ws.onerror = () => { clearTimeout(timeout); reject(new Error('WS连接失败')); };
  });
}

async function cancelJob(jobId) {
  const url = `${SERVER_URL}/api/cancel/${jobId}`;
  const req = new Request(url);
  req.method = "POST";
  req.allowInsecureRequest = true;
  req.headers = { "Authorization": `Bearer ${API_KEY}` };
  await req.loadJSON();
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
      const dialog = new Alert();
      dialog.title = "上传失败";
      dialog.message = "服务器返回了意外的响应";
      dialog.addOKButton();
      await dialog.present();
      return null;
    }
  } catch (error) {
    const dialog = new Alert();
    dialog.title = "上传失败";
    dialog.message = `无法连接到服务器: ${error}`;
    dialog.addOKButton();
    await dialog.present();
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
