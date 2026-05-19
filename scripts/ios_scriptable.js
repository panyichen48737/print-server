// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: blue; icon-glyph: print;
// iOS Cloud Print Server - Scriptable Script

// ===== 配置 =====
const SERVER_URL = "https://10.1.0.62:5000";
const API_KEY = "print-server-key-2026";
const ALLOWED_EXTENSIONS = [".doc", ".docx", ".pdf", ".xls", ".xlsx", ".ppt", ".pptx", ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif", ".heic", ".heif"];
const CONFIG_KEY = "PrintServer_Config";
const HISTORY_KEY = "PrintServer_History";
const MAX_CONCURRENT = 3;
const IMAGE_SIZE_LIMIT = 4000;
const FILE_SIZE_LIMIT_KB = 10240; // 10MB
const SMALL_FILE_LIMIT_KB = 5120;  // 5MB for BMP/TIFF
// ==========================

// ── Porcelain 主题 CSS ──
const PORCELAIN_CSS = `
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#FAFAF8;--card:#FFF;--primary:#8B7355;--primary-hover:#7A6248;--text:#1C1917;--text-sec:#8A8178;--border:#E5DDD5;--ok:#6B8F6B;--err:#C53A3A;--r12:12px;--r6:6px;--ft:Newsreader,Georgia,serif;--fb:-apple-system,sans-serif}
@media(prefers-color-scheme:dark){:root{--bg:#1C1C1A;--card:#262522;--primary:#B8956A;--primary-hover:#C9A67E;--text:#E8E5E0;--text-sec:#9A928A;--border:#353330;--ok:#7DBD7D;--err:#E86060}}
body{font-family:var(--fb);background:var(--bg);color:var(--text);padding:16px;min-height:100vh;display:flex;flex-direction:column}
h1{font-family:var(--ft);font-size:22px;font-weight:600;margin-bottom:16px}
.card{background:var(--card);border-radius:var(--r12);padding:16px;margin-bottom:12px;border:1px solid var(--border)}
.row{display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--border)}
.row:last-child{border-bottom:none}
.row-icon{width:22px;height:22px;margin-right:10px;flex-shrink:0}
.row-name{flex:1;font-size:15px}
.row-status{font-size:13px;color:var(--text-sec)}
.btn{display:inline-flex;align-items:center;justify-content:center;padding:10px 20px;border-radius:var(--r6);border:none;font-size:15px;font-weight:500;-webkit-tap-highlight-color:transparent}
.btn-pri{background:var(--primary);color:#fff}
.btn-pri:active{background:var(--primary-hover)}
.btn-sec{background:var(--card);color:var(--text);border:1px solid var(--border)}
.btn-sec:active{background:var(--border)}
.btn-err{background:var(--err);color:#fff}
.gap{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}
.flex{flex:1}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{width:18px;height:18px;border:2px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin .8s linear infinite;margin-right:10px;flex-shrink:0}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.pulse{animation:pulse 1.5s ease-in-out infinite}
.cfg{font-size:13px;color:var(--text-sec)}
.cfg b{color:var(--text)}
.cfg-row{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px}
`;

// ── 状态管理 ──

function getSavedConfig() {
  try { return JSON.parse(Keychain.get(CONFIG_KEY)); } catch { return null; }
}
function saveConfig(c) { Keychain.set(CONFIG_KEY, JSON.stringify(c)); }

// ── API ──

async function apiGet(path) {
  const r = new Request(SERVER_URL + path);
  r.method = "GET"; r.allowInsecureRequest = true;
  r.headers = { Authorization: "Bearer " + API_KEY };
  return await r.loadJSON();
}

async function apiPost(path, body) {
  const r = new Request(SERVER_URL + path);
  r.method = "POST"; r.allowInsecureRequest = true;
  r.headers = { Authorization: "Bearer " + API_KEY, "Content-Type": "application/json" };
  r.body = Data.fromString(JSON.stringify(body));
  return await r.loadJSON();
}

async function fetchServerConfig() {
  const r = new Request(SERVER_URL + "/api/print/config");
  r.method = "GET"; r.allowInsecureRequest = true;
  return await r.loadJSON();
}

async function cancelJob(id) { return apiPost("/api/cancel/" + id); }
async function retryJob(id) { return apiPost("/api/retry/" + id); }

// ── 图片压缩 ──

function resizeImage(img, max) {
  const w = img.size.width, h = img.size.height;
  if (w <= max && h <= max) return img;
  const s = Math.min(max / w, max / h);
  const ctx = new DrawContext();
  ctx.size = new Size(Math.round(w * s), Math.round(h * s));
  ctx.drawImageInRect(img, new Rect(0, 0, ctx.size.width, ctx.size.height));
  return ctx.getImage();
}

function fileSizeKB(data) {
  const b = data.getBytes();
  return b ? b.length / 1024 : 0;
}

// ── HTML 页面生成 ──

function htmlWrap(title, bodyHTML, configTag, extraJS) {
  const cfg = configTag ? `
<div class="card cfg">
  <div style="font-weight:600;margin-bottom:4px;color:var(--text);font-size:14px">打印配置</div>
  <div>&#x1F5A8; ${configTag.printer || '默认打印机'}</div>
  <div class="cfg-row"><span>份数:${configTag.copies||1}</span><span>${configTag.duplex?'双面':'单面'}</span><span>${configTag.color?'彩色':'黑白'}</span><span>${configTag.paperSize||'A4'}</span></div>
</div>` : '';
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><style>${PORCELAIN_CSS}</style></head><body><h1>${title}</h1>${bodyHTML}${cfg}${extraJS ? '<script>'+extraJS+'</script>' : ''}</body></html>`;
}

function uploadPageHTML(files, cfg) {
  const rows = files.map((_, i) =>
    `<div class="row" id=r${i}><div class="spin" id=s${i}></div><span class="row-name" id=n${i}>${_.name}</span><span class="row-status" id=st${i}>等待上传</span></div>`
  ).join('');
  return htmlWrap('上传进度',
    `<div class="card"><div style="text-align:center;margin-bottom:12px;font-size:14px;color:var(--text-sec)" id=prog>0 / ${files.length}</div>${rows}</div><div class="gap"><button class="btn btn-err" id=cancelBtn onclick="c()">取消上传</button></div>`,
    cfg,
    `var c_=false;function c(){c_=true;document.getElementById('cancelBtn').disabled=true;document.getElementById('cancelBtn').textContent='正在取消...';window.location='cb://cancel'}
function u(i,t){var e=document.getElementById('st'+i);if(e)e.textContent=t}
function d(i){var e=document.getElementById('s'+i);if(e)e.style.display='none';e=document.getElementById('cancelBtn');if(e)e.style.display='none'}
function p(dn,t){document.getElementById('prog').textContent=dn+' / '+t}
function xfer(){var h='<div class="card" style="text-align:center;padding:24px"><div style="font-size:40px">&#x2705;</div><div style="font-size:16px;font-weight:600;margin:8px 0">全部上传完成</div><div style="font-size:14px;color:var(--text-sec);margin-bottom:16px" id=xmsg></div><button class="btn btn-pri" onclick="window.location=\'cb://wait\'">查看进度</button></div>';document.body.innerHTML=h}
function xmsg(m){var e=document.getElementById('xmsg');if(e)e.textContent=m}`
  );
}

function waitPageHTML(jobs, cfg) {
  const rows = jobs.map((j, i) =>
    `<div class="row" id=j${i}><div class="spin" id=js${i}></div><span class="row-name">${j.filename}</span><span class="row-status" id=js${i}>排队中</span><button class="btn btn-sec" id=jb${i} onclick="w('${j.id}',${i})" style="margin-left:8px;padding:4px 10px;font-size:13px">取消</button></div>`
  ).join('');
  return htmlWrap('打印进度',
    `<div class="card"><div style="text-align:center;margin-bottom:12px;font-size:14px;color:var(--text-sec)" id=qpos></div>${rows}</div><div class="gap"><button class="btn btn-sec" onclick="window.location='cb://close'">后台运行</button></div>`,
    cfg,
    `function u(i,s,e){var el=document.getElementById('js'+i);if(!el)return
if(s==='completed'){el.textContent='✅ 完成';var sp=document.getElementById('jsp'+i);if(sp)sp.remove()
var b=document.getElementById('jb'+i);if(b)b.remove()}
else if(s==='failed'){el.textContent='❌ '+(e||'失败');var sp=document.getElementById('jsp'+i);if(sp)sp.remove()
var b=document.getElementById('jb'+i);if(b)b.remove()}
else if(s==='printing')el.textContent='🖨 打印中'
else el.textContent='⏳ 排队中'}
function w(id,i){window.location='cb://cancel?id='+id+'&i='+i}
function q(p,s){var e=document.getElementById('qpos');if(e&&p>0)e.textContent='队列位置: '+p+' / '+s;else if(e)e.textContent=''}
function allDone(){document.querySelector('.gap').innerHTML='<button class="btn btn-pri" onclick="window.location=\'cb://done\'">查看结果</button>'}`
  );
}

function settingsHTML(cfg, printers) {
  const popts = printers.map(p => `<option value="${p}"${p===cfg.printer?' selected':''}>${p}</option>`).join('');
  return htmlWrap('打印设置',
    `<div class="card">
  <div style="margin-bottom:12px"><label style="display:block;font-size:14px;font-weight:500;margin-bottom:4px">打印机</label><select id=p style="width:100%;padding:8px;border-radius:6px;border:1px solid var(--border);background:var(--card);color:var(--text);font-size:15px">${popts}</select></div>
  <div style="margin-bottom:12px"><label style="display:block;font-size:14px;font-weight:500;margin-bottom:4px">份数</label><input type=number id=c value="${cfg.copies||1}" min=1 max=99 style="width:80px;padding:8px;border-radius:6px;border:1px solid var(--border);background:var(--card);color:var(--text);font-size:15px"></div>
  <div style="margin-bottom:12px;display:flex;align-items:center;justify-content:space-between"><span style="font-size:14px;font-weight:500">双面打印</span><input type=checkbox id=d ${cfg.duplex?'checked':''} style="width:20px;height:20px"></div>
  <div style="margin-bottom:12px;display:flex;align-items:center;justify-content:space-between"><span style="font-size:14px;font-weight:500">彩色打印</span><input type=checkbox id=cl ${cfg.color?'checked':''} style="width:20px;height:20px"></div>
  <div style="margin-bottom:4px"><label style="display:block;font-size:14px;font-weight:500;margin-bottom:4px">纸张大小</label><select id=ps style="width:100%;padding:8px;border-radius:6px;border:1px solid var(--border);background:var(--card);color:var(--text);font-size:15px"><option value=A4${cfg.paperSize==='A4'?' selected':''}>A4</option><option value=Letter${cfg.paperSize==='Letter'?' selected':''}>Letter</option><option value=A3${cfg.paperSize==='A3'?' selected':''}>A3</option></select></div>
</div><div class="gap"><button class="btn btn-pri" onclick="save()">保存</button><button class="btn btn-sec" onclick="window.location='cb://reset'">重置为默认值</button></div>`,
    null,
    `function save(){var d={printer:document.getElementById('p').value,copies:parseInt(document.getElementById('c').value)||1,duplex:document.getElementById('d').checked,color:document.getElementById('cl').checked,paperSize:document.getElementById('ps').value};window.location='cb://save?'+encodeURIComponent(JSON.stringify(d))}`
  );
}

// ── 分享表单流程 ──

async function shareSheetFlow(files) {
  let cfg = getSavedConfig();
  if (!cfg) {
    try {
      const sc = await fetchServerConfig();
      cfg = { printer: sc.default_printer, copies: sc.default_copies, duplex: sc.default_duplex, color: sc.default_color, paperSize: sc.paper_size };
      saveConfig(cfg);
    } catch {
      cfg = { printer: '', copies: 1, duplex: true, color: true, paperSize: 'A4' };
    }
  }

  // 多张图片自动合并为一个打印任务
  const IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.heif'];
  const isMultiImage = files.length > 1 && files.every(f => IMAGE_EXTS.includes(getExtension(f.name)));
  if (isMultiImage) {
    await batchImageUpload(files, cfg);
    return;
  }

  // QuickLook 预览确认 — Data 类型不能直接传递，需先转为 Image
  for (const f of files) {
    const preview = f.image || (f.data ? Image.fromData(f.data) : null);
    if (preview) await QuickLook.present(preview);
  }

  const wv = new WebView();
  let wvClosed = false;
  const closePromise = wv.present(true).then(() => { wvClosed = true; });

  // === 上传阶段 ===
  await wv.loadHTML(uploadPageHTML(files, cfg));

  const jobs = [];
  let cancelled = false;
  const queue = [...files];

  async function uploadOne(file) {
    const i = files.indexOf(file);
    if (!wvClosed) await wv.evaluateJavaScript('u(' + i + ",'上传中...')");

    const r = new Request(SERVER_URL + "/api/print");
    r.method = "POST"; r.allowInsecureRequest = true;
    r.headers = { Authorization: "Bearer " + API_KEY };

    if (file.data) {
      let d = file.data;
      const ext = getExtension(file.name);
      const skb = fileSizeKB(d);
      if ((ext === '.bmp' || ext === '.tiff' || ext === '.tif' || ext === '.png') && skb > FILE_SIZE_LIMIT_KB) {
        try {
          const img = Image.fromData(d);
          d = Data.fromJPEG(resizeImage(img, IMAGE_SIZE_LIMIT));
        } catch {}
      }
      r.addFileDataToMultipart(d, "application/octet-stream", "file", file.name);
    } else if (file.image) {
      let img = file.image;
      const skb = fileSizeKB(Data.fromJPEG(img));
      if (skb > FILE_SIZE_LIMIT_KB || img.size.width > IMAGE_SIZE_LIMIT || img.size.height > IMAGE_SIZE_LIMIT) {
        img = resizeImage(img, IMAGE_SIZE_LIMIT);
      }
      r.addFileDataToMultipart(Data.fromJPEG(img), "image/jpeg", "file", file.name);
    } else return null;

    if (cfg.printer) r.addParameterToMultipart("printer", cfg.printer);
    r.addParameterToMultipart("copies", String(cfg.copies || 1));
    r.addParameterToMultipart("duplex", cfg.duplex ? "1" : "0");
    r.addParameterToMultipart("color", cfg.color ? "1" : "0");
    if (cfg.paperSize) r.addParameterToMultipart("paper_size", cfg.paperSize);

    try {
      const res = await r.loadJSON();
      if (res && res.job_id) {
        jobs.push({ id: res.job_id, filename: file.name });
        if (!wvClosed) {
          await wv.evaluateJavaScript('u(' + i + ",'✅ 已上传')");
          await wv.evaluateJavaScript('d(' + i + ')');
          await wv.evaluateJavaScript('p(' + jobs.length + ',' + files.length + ')');
        }
        return res.job_id;
      }
    } catch {}
    if (!wvClosed) {
      await wv.evaluateJavaScript('u(' + i + ",'❌ 上传失败')");
    }
    return null;
  }

  // 3 并发上传
  const workers = [];
  for (let i = 0; i < Math.min(MAX_CONCURRENT, queue.length); i++) {
    workers.push((async () => {
      while (queue.length > 0 && !cancelled) {
        if (wvClosed) return;
        const file = queue.shift();
        await uploadOne(file);
        // 检查用户是否取消
        if (!wvClosed) {
          try { cancelled = await wv.evaluateJavaScript('c_'); } catch {}
        }
      }
    })());
  }
  await Promise.all(workers);

  if (wvClosed) {
    // 用户关闭了页面，发通知
    if (jobs.length > 0) {
      const n = new Notification();
      n.title = "✅ " + jobs.length + " 个文件已上传";
      n.body = "文件已提交到服务器";
      n.sound = "default";
      n.userInfo = { type: 'uploaded', jobs: jobs, timestamp: Date.now() };
      await n.schedule();
    }
    return;
  }

  // 上传完成 → 过渡到等待页
  await wv.evaluateJavaScript('xfer()');
  if (jobs.length === 0) {
    await wv.evaluateJavaScript('xmsg("全部上传失败")');
    await new Promise(r => setTimeout(r, 2000));
    return;
  }
  await wv.evaluateJavaScript('xmsg("' + jobs.length + ' 个文件已提交")');

  // 等用户点"查看进度"
  try {
    const cb = await Promise.race([
      wv.waitForLoad().catch(() => null),
      closePromise
    ]);
    if (!cb || wvClosed) return;
  } catch { return; }

  // === 等待阶段 ===
  await wv.loadHTML(waitPageHTML(jobs, cfg));

  // WebSocket 监听
  const wsUrl = SERVER_URL.replace('https://', 'wss://').replace('http://', 'ws://');
  let ws = null;
  const statuses = {};
  jobs.forEach(j => { statuses[j.id] = 'queued'; });

  try {
    ws = new WebSocket(wsUrl + "/ws/events");
    ws.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg);
        if (ev.event === 'job_status') {
          const d = ev.data;
          statuses[d.job_id] = d.status;
          const idx = jobs.findIndex(j => j.id === d.job_id);
          if (idx >= 0 && !wvClosed) {
            wv.evaluateJavaScript("u(" + idx + ",'" + (d.status||'').replace(/'/g,"\\'") + "','" + (d.error||'').replace(/'/g,"\\'") + "')");
          }
          // 检查是否全部完成
          if (jobs.every(j => { const s=statuses[j.id]; return s==='completed'||s==='failed'; })) {
            if (!wvClosed) wv.evaluateJavaScript('allDone()');
          }
        }
      } catch {}
    };
    ws.onerror = () => { ws = null; };
  } catch { ws = null; }

  // 等待用户操作
  while (!wvClosed) {
    try {
      const callback = await wv.waitForLoad();
      const url = callback.url || '';
      if (url.includes('close')) break;
      if (url.includes('cancel')) {
        const m = url.match(/id=([^&]+)/);
        if (m) cancelJob(m[1]).catch(() => {});
      }
      if (url.includes('done')) { await sendResultNotif(jobs, statuses); break; }
    } catch { break; }
  }

  if (ws) ws.close();

  // 用户关闭了等待页，发通知
  const allTerminal = jobs.every(j => { const s=statuses[j.id]; return s==='completed'||s==='failed'; });
  if (!allTerminal) {
    const n = new Notification();
    n.title = "📨 " + jobs.length + " 个文件正在打印";
    n.body = "打印完成后会通知您";
    n.sound = "default";
    n.userInfo = { type: 'waiting', jobs: jobs, timestamp: Date.now() };
    await n.schedule();
  } else {
    await sendResultNotif(jobs, statuses);
  }
}

async function sendResultNotif(jobs, statuses) {
  const ok = jobs.filter(j => statuses[j.id] === 'completed').length;
  const fail = jobs.filter(j => statuses[j.id] === 'failed');
  const n = new Notification();
  if (fail.length === 0) {
    n.title = "✅ 打印完成";
    n.body = ok + " 个文件已发送到打印机";
    n.userInfo = { type: 'completed', jobs: jobs, timestamp: Date.now() };
  } else if (ok > 0) {
    n.title = "⚠️ 打印完成";
    n.body = ok + " 个成功，" + fail.length + " 个失败";
    n.userInfo = { type: 'partial', jobs: jobs, failedJobs: fail, timestamp: Date.now() };
  } else {
    n.title = "❌ 打印失败";
    n.body = "请检查打印机和服务器状态";
    n.userInfo = { type: 'failed', jobs: jobs, errors: fail, timestamp: Date.now() };
  }
  n.sound = "default";
  await n.schedule();
}

// ── 多图片合并上传 ──

async function batchImageUpload(files, cfg) {
  const wv = new WebView();
  let wvClosed = false;
  wv.present(true).then(() => { wvClosed = true; });
  await wv.loadHTML(uploadPageHTML(files, cfg));

  const r = new Request(SERVER_URL + "/api/print/images");
  r.method = "POST"; r.allowInsecureRequest = true;
  r.headers = { Authorization: "Bearer " + API_KEY };

  for (const [i, f] of files.entries()) {
    if (!wvClosed) await wv.evaluateJavaScript('u(' + i + ",'添加中...')");
    if (f.data) {
      r.addFileDataToMultipart(f.data, "application/octet-stream", "files", f.name);
    } else if (f.image) {
      let img = f.image;
      r.addFileDataToMultipart(Data.fromJPEG(img), "image/jpeg", "files", f.name);
    }
  }

  if (cfg.printer) r.addParameterToMultipart("printer", cfg.printer);
  r.addParameterToMultipart("copies", String(cfg.copies || 1));
  r.addParameterToMultipart("duplex", cfg.duplex ? "1" : "0");
  r.addParameterToMultipart("color", cfg.color ? "1" : "0");
  if (cfg.paperSize) r.addParameterToMultipart("paper_size", cfg.paperSize);

  let jobId = null;
  let failed = false;
  try {
    const res = await r.loadJSON();
    if (res && res.job_id) {
      jobId = res.job_id;
      if (!wvClosed) await wv.evaluateJavaScript('xfer()');
    } else {
      failed = true;
    }
  } catch {
    failed = true;
  }

  if (failed || !jobId) {
    if (!wvClosed) {
      await wv.evaluateJavaScript('document.body.innerHTML=\'<div class="card" style="text-align:center;padding:24px"><div style="font-size:40px">\\u274C</div><div style="font-size:16px;font-weight:600;margin:8px 0">\\u4E0A\\u4F20\\u5931\\u8D25</div><button class="btn btn-pri" onclick="window.location=\'cb://close\'">\\u8FD4\\u56DE</button></div>\'');
    }
    return;
  }

  await wv.evaluateJavaScript('xmsg("已提交 ' + files.length + ' 张图片")');
  const n = new Notification();
  n.title = "✅ 打印任务已提交";
  n.body = files.length + " 张图片已合并为一个打印任务";
  n.sound = "default";
  n.userInfo = { type: 'uploaded', jobs: [{ id: jobId, filename: files[0].name + ' 等' }], timestamp: Date.now() };
  await n.schedule();
}

// ── 直接运行流程 ──

async function directRunFlow() {
  const table = new UITable();
  table.showSeparators = true;
  const items = [
    ["printer", "打印设置", "配置默认打印机、份数、纸张等"],
    ["list.bullet", "任务列表", "查看和管理打印任务"],
    ["clock.arrow.circlepath", "打印历史", "最近完成的任务，可重新提交"],
    ["server.rack", "服务器状态", "连接状态、队列长度、打印机列表"],
  ];
  let selected = -1;
  for (let i = 0; i < items.length; i++) {
    const [icon, title, sub] = items[i];
    const row = new UITableRow();
    row.dismissOnSelect = true;
    row.cellSpacing = 10;
    row.onSelect = () => { selected = i; };
    const sym = SFSymbol.named(icon);
    if (sym) {
      const c = row.addImage(sym.image);
      c.widthWeight = 40;
    }
    const tc = row.addText(title, sub);
    tc.titleFont = Font.boldSystemFont(16);
    tc.subtitleFont = Font.systemFont(13);
    tc.subtitleColor = Color.gray();
    tc.widthWeight = 100;
    table.addRow(row);
  }
  await table.present();
  if (selected === 0) await showSettings();
  else if (selected === 1) await showTaskList();
  else if (selected === 2) await showHistory();
  else if (selected === 3) await showServerStatus();
}

async function showSettings() {
  let cfg = getSavedConfig();
  let printers = [];
  try {
    const sc = await fetchServerConfig();
    printers = sc.printers || [];
    if (!cfg) cfg = { printer: sc.default_printer, copies: sc.default_copies, duplex: sc.default_duplex, color: sc.default_color, paperSize: sc.paper_size };
  } catch {
    if (!cfg) cfg = { printer: '', copies: 1, duplex: true, color: true, paperSize: 'A4' };
  }
  const wv = new WebView();
  await wv.loadHTML(settingsHTML(cfg, printers));
  wv.present(true);
  while (true) {
    try {
      const cb = await wv.waitForLoad();
      const url = cb.url || '';
      if (url.includes('save')) {
        saveConfig(JSON.parse(decodeURIComponent(url.split('?')[1])));
        await wv.evaluateJavaScript('document.body.innerHTML=\'<div class="card" style="text-align:center;padding:24px"><div style="font-size:40px">\\u2705</div><div style="font-size:16px;font-weight:600;margin:8px 0">\\u8BBE\\u7F6E\\u5DF2\\u4FDD\\u5B58</div><button class="btn btn-pri" onclick="window.location=\'cb://close\'" style="margin-top:16px">\\u5173\\u95ED</button></div>\'');
      } else if (url.includes('reset')) {
        try {
          const sc = await fetchServerConfig();
          const def = { printer: sc.default_printer, copies: sc.default_copies, duplex: sc.default_duplex, color: sc.default_color, paperSize: sc.paper_size };
          saveConfig(def);
          await wv.loadHTML(settingsHTML(def, printers));
        } catch {
          await wv.evaluateJavaScript('alert("无法获取服务器默认配置")');
        }
      } else break;
    } catch { break; }
  }
}

async function showTaskList() {
  try {
    const data = await apiGet("/api/jobs?limit=50");
    const jobs = data.jobs || [];
    if (jobs.length === 0) {
      const a = new Alert(); a.title = "任务列表"; a.message = "当前没有活跃任务"; a.addAction("返回"); await a.present(); return;
    }
    const table = new UITable(); table.showSeparators = true;
    const failed = jobs.filter(j => j.status === 'failed');
    if (failed.length > 1) {
      const hr = new UITableRow();
      hr.addText("批量重试 (" + failed.length + " 个失败任务)");
      hr.dismissOnSelect = true;
      hr.onSelect = async () => {
        for (const f of failed) { try { await retryJob(f.id); } catch {} }
        const a = new Alert(); a.title = "批量重试"; a.message = "已全部重新提交"; a.addAction("返回"); await a.present();
        await showTaskList();
      };
      table.addRow(hr);
    }
    for (const j of jobs) {
      const row = new UITableRow(); row.cellSpacing = 8;
      const icon = j.status === 'completed' ? '✅' : j.status === 'failed' ? '❌' : j.status === 'printing' ? '🖨' : '⏳';
      const tc = row.addText(icon + ' ' + j.filename, j.status + (j.error_message ? ' - ' + j.error_message : ''));
      tc.titleFont = Font.mediumFont(15); tc.subtitleFont = Font.systemFont(12); tc.subtitleColor = Color.gray(); tc.widthWeight = 100;
      if (j.status === 'queued' || j.status === 'printing') {
        const btn = row.addButton("取消"); btn.widthWeight = 50;
        btn.onTap = async () => { try { await cancelJob(j.id); await showTaskList(); } catch {} };
      } else if (j.status === 'failed') {
        const btn = row.addButton("重试"); btn.widthWeight = 50;
        btn.onTap = async () => { try { await retryJob(j.id); await showTaskList(); } catch {} };
      }
      table.addRow(row);
    }
    await table.present();
  } catch (e) {
    const a = new Alert(); a.title = "获取失败"; a.message = "" + e; a.addAction("返回"); await a.present();
  }
}

async function showHistory() {
  try {
    const data = await apiGet("/api/jobs?limit=20&status=completed,failed");
    const jobs = data.jobs || [];
    if (jobs.length === 0) {
      const a = new Alert(); a.title = "打印历史"; a.message = "暂无打印记录"; a.addAction("返回"); await a.present(); return;
    }
    const table = new UITable(); table.showSeparators = true;
    for (const j of jobs) {
      const row = new UITableRow(); row.dismissOnSelect = true;
      const icon = j.status === 'completed' ? '✅' : '❌';
      const ts = j.completed_at ? new Date(j.completed_at).toLocaleString() : '';
      row.addText(icon + ' ' + j.filename, ts + (j.error_message ? ' - ' + j.error_message : ''));
      row.onSelect = async () => {
        try {
          const res = await retryJob(j.id);
          if (res && res.new_job_id) {
            const a = new Alert(); a.title = "已重新提交"; a.message = "「" + j.filename + "」已重新加入打印队列"; a.addAction("返回"); await a.present();
          }
        } catch (e) {
          const a = new Alert(); a.title = "重提交失败"; a.message = "" + e; a.addAction("返回"); await a.present();
        }
      };
      table.addRow(row);
    }
    await table.present();
  } catch (e) {
    const a = new Alert(); a.title = "获取失败"; a.message = "" + e; a.addAction("返回"); await a.present();
  }
}

async function showServerStatus() {
  try {
    const health = await apiGet("/api/health");
    const printers = await apiGet("/api/printers/status");
    const table = new UITable(); table.showSeparators = true;
    const hr = new UITableRow(); hr.addText("服务器状态", "版本: " + (health.version||'未知') + " | 端口: " + (health.port||5000)); hr.isHeader = true; table.addRow(hr);
    const sr = new UITableRow(); sr.addText(health.status === 'ok' ? '✅ 运行中' : '❌ 异常', "队列长度: " + (health.queue_size||0)); table.addRow(sr);
    const pd = printers.printers || {};
    const pn = Object.keys(pd);
    if (pn.length > 0) {
      const ph = new UITableRow(); ph.addText("打印机 (" + pn.length + ")"); ph.isHeader = true; table.addRow(ph);
      for (const name of pn) {
        const pr = pd[name];
        const prRow = new UITableRow();
        const icon = pr.overall === 'ready' ? '✅' : pr.overall === 'error' ? '❌' : pr.overall === 'warning' ? '⚠️' : '🔄';
        prRow.addText(icon + ' ' + name, pr.overall || '未知');
        table.addRow(prRow);
      }
    }
    await table.present();
  } catch (e) {
    const a = new Alert(); a.title = "连接失败"; a.message = "无法连接到服务器: " + e + "\n\n请检查服务器地址和网络连接"; a.addAction("返回"); await a.present();
  }
}

// ── 通知点击回溯 ──

async function handleNotification(n) {
  const ctx = n.userInfo;
  if (!ctx || !ctx.type) return;
  switch (ctx.type) {
    case 'completed': {
      const a = new Alert(); a.title = "✅ 打印完成"; a.message = (ctx.jobs||[]).length + " 个文件已发送到打印机"; a.addAction("关闭"); await a.present(); break;
    }
    case 'partial': {
      const fj = ctx.failedJobs || [];
      const table = new UITable(); table.showSeparators = true;
      for (const f of fj) {
        const row = new UITableRow();
        const btn = row.addButton("重试"); btn.widthWeight = 50;
        btn.onTap = async () => { try { await retryJob(f.id); } catch {} };
        row.addText("❌ " + f.filename);
        table.addRow(row);
      }
      if (fj.length > 1) {
        const rr = new UITableRow(); rr.dismissOnSelect = true;
        rr.addText("全部重试 (" + fj.length + ")");
        rr.onSelect = async () => { for (const f of fj) { try { await retryJob(f.id); } catch {} } const a = new Alert(); a.title = "已全部重试"; a.message = fj.length + " 个任务已重新提交"; a.addAction("返回"); await a.present(); };
        table.addRow(rr);
      }
      await table.present(); break;
    }
    case 'failed': {
      const errs = ctx.errors || ctx.jobs || [];
      const a = new Alert(); a.title = "❌ 打印失败";
      a.message = errs.map(j => "「" + (j.filename||j.id) + "」" + (j.error||'')).join('\n') || "请检查打印机和服务器状态";
      a.addAction("全部重试"); a.addCancelAction("关闭");
      if (await a.present() === 0) {
        for (const j of errs) { try { await retryJob(j.id); } catch {} }
        const n = new Notification(); n.title = "已全部重试"; n.body = errs.length + " 个任务已重新提交"; n.sound = "default"; await n.schedule();
      }
      break;
    }
    case 'cancelled': {
      const a = new Alert(); a.title = "⏹ 已取消"; a.message = "已取消 " + (ctx.count||0) + " 个打印任务"; a.addAction("关闭"); await a.present(); break;
    }
    case 'waiting':
    case 'uploaded': {
      await showTaskList(); break;
    }
  }
}

// ── 工具函数 ──

function getExtension(n) {
  const i = n.lastIndexOf(".");
  return i >= 0 ? n.substring(i).toLowerCase() : "";
}

// ── 入口 ──

async function main() {
  if (args.notification) { await handleNotification(args.notification); return; }

  const files = [];
  const fm = FileManager.local();
  if (args.fileURLs) {
    for (const url of args.fileURLs) {
      const d = fm.read(url);
      const n = decodeURIComponent(url.split("/").pop().split("?")[0]);
      if (d) files.push({ data: d, name: n });
    }
  }
  if (args.images) {
    for (const img of args.images) {
      files.push({ image: img, name: "photo_" + Date.now() + "_" + files.length + ".jpg" });
    }
  }

  if (files.length === 0) { await directRunFlow(); return; }

  // 过滤支持的文件
  const valid = [], errors = [];
  for (const f of files) {
    const ext = getExtension(f.name);
    if (ALLOWED_EXTENSIONS.includes(ext)) valid.push(f);
    else errors.push("「" + f.name + "」 (" + ext + ") 不支持");
  }
  if (valid.length === 0) {
    const a = new Alert(); a.title = "没有可打印的文件";
    a.message = "所选文件类型均不在允许列表中。\n\n允许的类型: " + ALLOWED_EXTENSIONS.join(", ");
    if (errors.length) a.message += "\n\n" + errors.join("\n");
    a.addAction("OK"); await a.present(); return;
  }
  if (errors.length > 0) {
    const a = new Alert(); a.title = errors.length + " 个文件被跳过";
    a.message = errors.join("\n") + "\n\n继续打印剩余文件？";
    a.addAction("继续"); a.addCancelAction("取消");
    if (await a.present() === -1) return;
  }

  await shareSheetFlow(valid);
}

await main();
Script.complete();