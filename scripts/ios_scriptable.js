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
const ACTIVE_JOBS_KEY = "PrintServer_ActiveJobs";
const WS_TIMEOUT = 8;  // WebSocket 等待超时（秒），超时后回退到轮询
// ==============================================================

async function main() {
  const files = getFiles();

  if (!files || files.length === 0) {
    // 从通知或手动运行 -> 显示操作菜单
    const activeJobs = getActiveJobs();
    if (activeJobs.length > 0) {
      await showCancelMenu(activeJobs);
    } else {
      const dialog = new Alert();
      dialog.title = "iOS 云打印";
      dialog.message = "请通过分享表单使用此脚本：\n\n1. 在文件 App 或 Safari 中选择一个或多个文件\n2. 点击分享按钮\n3. 选择「共享」→ Scriptable\n4. 选择此脚本";
      dialog.addAction("知道了");
      await dialog.present();
    }
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
    dialog.addAction("OK");
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

  const total = validFiles.length;

  // Confirm before multi-file upload
  if (total > 1) {
    const confirm = new Alert();
    confirm.title = `打印 ${total} 个文件`;
    confirm.message = `文件列表:\n${validFiles.map(f => f.name).join("\n")}`;
    confirm.addAction("开始打印");
    confirm.addCancelAction("取消");
    const btn = await confirm.present();
    if (btn === -1) return;
  }

  // Upload files sequentially, saving after each for cancel-from-icon support
  const uploadedJobs = [];
  for (let i = 0; i < total; i++) {
    console.log(`正在上传 (${i + 1}/${total}): ${validFiles[i].name}`);
    const jobId = await uploadFile(validFiles[i]);
    if (jobId) {
      uploadedJobs.push({ id: jobId, filename: validFiles[i].name });
      saveActiveJobs(uploadedJobs);
      // Send notification for upload progress
      if (total > 1) {
        const n = new Notification();
        n.title = `📤 上传 ${i + 1}/${total}`;
        n.body = `「${validFiles[i].name}」已提交到服务器`;
        n.sound = "default";
        await n.schedule();
      }
    }
  }

  // Wait for completion
  if (total === 1 && uploadedJobs.length === 1) {
    await waitForCompletion(uploadedJobs[0].id);
  } else if (uploadedJobs.length > 0) {
    // Multi-file: confirm before starting to wait
    const confirmWait = new Alert();
    confirmWait.title = `已上传 ${uploadedJobs.length} 个文件`;
    confirmWait.message = "等待打印完成？";
    confirmWait.addAction("等待完成");
    confirmWait.addCancelAction("后台运行");
    const waitBtn = await confirmWait.present();
    if (waitBtn === -1) {
      // User chose to run in background, just notify submission
      const n = new Notification();
      n.title = `📨 ${uploadedJobs.length} 个文件已提交打印`;
      n.body = "文件已上传到服务器，打印完成后会通知";
      n.sound = "default";
      await n.schedule();
      return;
    }

    // Parallel wait via WebSocket (all statuses arrive in real time)
    const results = await Promise.allSettled(
      uploadedJobs.map(j => waitForJob(j.id))
    );
    clearActiveJobs();
    const completed = results.filter(r => r.status === 'fulfilled').length;
    const failed = results.filter(r => r.status === 'rejected').length;
    const n = new Notification();
    if (failed === 0) {
      n.title = `✅ ${completed} 个文件打印完成`;
      n.body = "所有文件已成功发送到打印机";
    } else if (completed > 0) {
      n.title = `⚠ ${completed} 完成, ${failed} 失败`;
      n.body = "部分文件打印失败，请检查服务器日志";
    } else {
      n.title = `❌ ${failed} 个文件打印失败`;
      n.body = "所有文件打印失败，请检查服务器日志";
    }
    n.sound = "default";
    await n.schedule();
  }
}

function getFiles() {
  const files = [];
  const fm = FileManager.local();

  // Files from share sheet (Files app, Safari, etc.)
  if (args.fileURLs && args.fileURLs.length > 0) {
    for (const url of args.fileURLs) {
      const data = fm.read(url);
      const name = decodeURIComponent(url.split("/").pop().split("?")[0]);
      if (data) files.push({ data, name });
    }
  }

  // Images from Photos app share sheet
  if (args.images && args.images.length > 0) {
    for (const image of args.images) {
      const w = image.size.width;
      const h = image.size.height;
      const name = `photo_${Date.now()}_${files.length}_${w}x${h}.jpg`;
      files.push({ image, name });
    }
  }

  return files;
}

function getExtension(filename) {
  const idx = filename.lastIndexOf(".");
  return idx >= 0 ? filename.substring(idx).toLowerCase() : "";
}

// ── 持久化任务 ID（Keychain），支持从主屏幕取消 ──

function getActiveJobs() {
  try {
    const json = Keychain.get(ACTIVE_JOBS_KEY);
    return json ? JSON.parse(json) : [];
  } catch (e) {
    return [];
  }
}

function saveActiveJobs(jobs) {
  Keychain.set(ACTIVE_JOBS_KEY, JSON.stringify(jobs));
}

function clearActiveJobs() {
  Keychain.remove(ACTIVE_JOBS_KEY);
}

async function showCancelMenu(jobs) {
  if (jobs.length === 0) return;

  const dialog = new Alert();
  dialog.title = `⏳ ${jobs.length} 个打印任务进行中`;
  dialog.message = jobs.map((j, i) => `${i + 1}. ${j.filename}`).join("\n");
  dialog.addDestructiveAction("取消全部");

  for (const job of jobs) {
    dialog.addDestructiveAction(`✕ ${job.filename}`);
  }

  dialog.addCancelAction("关闭");
  const btn = await dialog.present();

  if (btn === 0) {
    // Cancel all
    for (const job of jobs) {
      try { await cancelJob(job.id); } catch(e) {}
    }
    clearActiveJobs();
    const n = new Notification();
    n.title = `⏹ 已取消全部 ${jobs.length} 个任务`;
    n.body = "所有打印任务已取消";
    n.sound = "default";
    await n.schedule();
  } else if (btn > 0 && btn <= jobs.length) {
    // Cancel one specific job (btn-1 because btn 0 = "取消全部")
    const job = jobs[btn - 1];
    try {
      await cancelJob(job.id);
      const remaining = jobs.filter(j => j.id !== job.id);
      if (remaining.length > 0) {
        saveActiveJobs(remaining);
        await showCancelMenu(remaining);
      } else {
        clearActiveJobs();
        const n = new Notification();
        n.title = "⏹ 所有任务已取消";
        n.body = "打印任务已全部取消";
        n.sound = "default";
        await n.schedule();
      }
    } catch(e) {
      const errAlert = new Alert();
      errAlert.title = "取消失败";
      errAlert.message = `无法取消「${job.filename}」: ${e}`;
      errAlert.addAction("重试");
      errAlert.addCancelAction("返回");
      const retry = await errAlert.present();
      if (retry === 0) await showCancelMenu(jobs);
    }
  }
}

async function waitForCompletion(jobId) {
  const dialog = new Alert();
  dialog.title = "🖨 正在打印...";
  dialog.message = "等待打印完成，或取消该任务";
  dialog.addDestructiveAction("取消打印");
  dialog.addAction("等待完成");
  dialog.addCancelAction("关闭");

  const btn = await dialog.present();

  if (btn === 0) {
    await cancelJob(jobId);
    clearActiveJobs();
    const n = new Notification();
    n.title = "⏹ 打印已取消";
    n.body = "打印任务已取消";
    n.sound = "default";
    await n.schedule();
    return;
  } else if (btn === -1) {
    return;
  }

  try {
    await waitForJob(jobId);
    clearActiveJobs();
    const n = new Notification();
    n.title = "✅ 打印完成";
    n.body = "文件已成功发送到打印机";
    n.sound = "default";
    await n.schedule();
  } catch (err) {
    clearActiveJobs();
    const n = new Notification();
    if (err.message === '超时') {
      n.title = "⏱ 轮询超时";
      n.body = "请检查服务器状态";
    } else {
      n.title = "❌ 打印失败";
      n.body = err.message;
    }
    n.sound = "default";
    await n.schedule();
  }
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
  const req = new Request(`${SERVER_URL}/api/print`);
  req.method = "POST";
  req.allowInsecureRequest = true;
  req.headers = { "Authorization": `Bearer ${API_KEY}` };

  // Use built-in multipart API (automatic Content-Type, no manual encoding)
  if (file.data) {
    req.addFileDataToMultipart(file.data, "application/octet-stream", "file", file.name);
  } else if (file.image) {
    const imgData = Data.fromJPEG(file.image);
    req.addFileDataToMultipart(imgData, "image/jpeg", "file", file.name);
  } else {
    return null;
  }

  try {
    const response = await req.loadJSON();

    if (response && response.job_id) {
      console.log(`上传成功，任务 ID: ${response.job_id}`);
      return response.job_id;
    } else {
      const dialog = new Alert();
      dialog.title = "上传失败";
      dialog.message = "服务器返回了意外的响应";
      dialog.addAction("OK");
      await dialog.present();
      return null;
    }
  } catch (error) {
    const dialog = new Alert();
    dialog.title = "上传失败";
    dialog.message = `无法连接到服务器: ${error}`;
    dialog.addAction("OK");
    await dialog.present();
    return null;
  }
}

// ── WebSocket + 轮询混合等待 ──

function waitForJob(jobId) {
  return new Promise((resolve, reject) => {
    let resolved = false;
    const wsUrl = SERVER_URL.replace('https://', 'wss://').replace('http://', 'ws://');

    function fallback() {
      if (!resolved) {
        resolved = true;
        pollStatus(jobId).then(resolve).catch(reject);
      }
    }

    const ws = new WebSocket(`${wsUrl}/ws/events`);
    const wsTimeout = setTimeout(() => {
      console.log("WebSocket 连接超时，降级到轮询");
      try { ws.close(); } catch(e) {}
      fallback();
    }, WS_TIMEOUT * 1000);

    ws.onopen = () => { console.log("WebSocket 已连接"); };

    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg);
        if (event.event === 'job_status' && event.data.job_id === jobId) {
          if (event.data.status === 'completed') {
            resolved = true;
            clearTimeout(wsTimeout);
            ws.close();
            resolve();
          } else if (event.data.status === 'failed') {
            resolved = true;
            clearTimeout(wsTimeout);
            ws.close();
            reject(new Error(event.data.error || '打印失败'));
          }
        }
      } catch (e) {
        console.log(`WS 消息解析失败: ${e}`);
      }
    };

    ws.onerror = (err) => {
      console.log(`WebSocket 错误: ${err}`);
      clearTimeout(wsTimeout);
      try { ws.close(); } catch(e) {}
      fallback();
    };

    ws.onclose = () => {
      if (!resolved) {
        clearTimeout(wsTimeout);
        fallback();
      }
    };
  });
}

function pollStatus(jobId) {
  return new Promise((resolve, reject) => {
    let retries = 0;
    const timer = setInterval(async () => {
      retries++;
      const url = `${SERVER_URL}/api/status/${jobId}`;
      const req = new Request(url);
      req.method = "GET";
      req.allowInsecureRequest = true;
      try {
        const response = await req.loadJSON();
        if (!response || !response.status) {
          if (retries >= POLL_MAX_RETRIES) {
            clearInterval(timer);
            reject(new Error('超时'));
          }
          return;
        }
        if (response.status === "completed") {
          clearInterval(timer);
          resolve();
        } else if (response.status === "failed") {
          clearInterval(timer);
          reject(new Error(response.error || '打印失败'));
        }
      } catch (error) {
        console.log(`轮询失败: ${error}`);
      }
    }, POLL_INTERVAL * 1000);
  });
}

// Run
await main();
Script.complete();
