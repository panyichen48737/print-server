"""文件上传辅助模块：统一处理文件接收、校验、保存和入队"""

import os
import uuid
import logging
from typing import Optional
from flask import jsonify, Response
from werkzeug.utils import secure_filename
from app._paths import app_root, ensure_dir

logger = logging.getLogger('print_server')


def handle_file_upload(request, config, queue_mgr, *, source: str = 'api') -> tuple[Optional[str], Optional[tuple[Response, int]]]:
    """
    处理文件上传的统一逻辑

    参数:
        request: Flask request 对象
        config: Config 实例
        queue_mgr: QueueManager 实例
        source: 来源标识，'api' 或 'web'

    返回:
        (job_id, error_response) 元组
        成功时 error_response 为 None
        失败时返回 (None, (json_response, status_code))
    """
    if 'file' not in request.files:
        return None, (jsonify({'success': False, 'error': 'No file provided'}), 400)

    file = request.files['file']
    if not file.filename:
        return None, (jsonify({'success': False, 'error': 'Empty filename'}), 400)

    config_obj = config
    original_name = file.filename
    ext = os.path.splitext(original_name)[1].lower()

    # 校验扩展名
    if ext not in config_obj.allowed_extensions:
        return None, (jsonify({'success': False, 'error': f'File type {ext} not allowed'}), 400)

    # 先检查 Content-Length 避免大文件写入
    max_size = config_obj.max_file_size_mb * 1024 * 1024
    content_length = request.headers.get('Content-Length')
    if content_length and int(content_length) > max_size:
        return None, (jsonify({'success': False, 'error': f'File too large, max {config_obj.max_file_size_mb}MB'}), 400)

    # 安全化文件名 + UUID 前缀保唯一
    safe_name = secure_filename(original_name) or f"file{ext}"
    job_id = str(uuid.uuid4())
    jobs_dir = ensure_dir(app_root(), 'jobs')
    save_path = os.path.join(jobs_dir, f'{job_id}_{safe_name}')
    file.save(save_path)
    file_size = os.path.getsize(save_path)

    # 校验文件大小
    if file_size > max_size:
        os.remove(save_path)
        return None, (jsonify({'success': False, 'error': f'File too large, max {config_obj.max_file_size_mb}MB'}), 400)

    # 获取打印参数（可选，来自表单）
    printer = request.form.get('printer') or None
    copies_s = request.form.get('copies')
    copies = int(copies_s) if copies_s and copies_s.isdigit() else None
    duplex_s = request.form.get('duplex')
    duplex = int(duplex_s) if duplex_s in ('0', '1') else None
    color_s = request.form.get('color')
    color = int(color_s) if color_s in ('0', '1') else None
    paper_size = request.form.get('paper_size') or None

    if copies is not None and (copies < 1 or copies > 99):
        os.remove(save_path)
        return None, (jsonify({'success': False, 'error': 'Copies must be between 1 and 99'}), 400)

    # 入队
    actual_job_id = queue_mgr.add_job(
        original_name, save_path, file_size, ext,
        duplex=duplex, color=color, copies=copies,
        paper_size=paper_size, printer_name=printer,
        source=source
    )

    logger.info(f'Upload success: {original_name} -> job_id={actual_job_id}')
    return actual_job_id, None
