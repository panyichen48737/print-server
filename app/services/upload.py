"""文件上传辅助模块：统一处理文件接收、校验、保存和入队"""

import os
import uuid
from dataclasses import dataclass
from loguru import logger
from app._paths import app_root, ensure_dir


@dataclass
class UploadResult:
    """文件上传结果"""
    success: bool
    job_id: str = ''
    error: str = ''


def handle_file_upload(
    filename: str,
    file_bytes: bytes,
    config,
    queue_mgr,
    *,
    source: str = 'api',
    printer: str | None = None,
    copies: str | None = None,
    duplex: str | None = None,
    color: str | None = None,
    paper_size: str | None = None,
) -> UploadResult:
    """处理文件上传的统一逻辑（不依赖 Flask request 对象）

    参数:
        filename: 原始文件名
        file_bytes: 文件二进制内容
        config: Config 实例
        queue_mgr: JobQueue 实例
        source: 来源标识，'api' 或 'web'
        printer/copies/duplex/color/paper_size: 打印参数

    返回:
        {'success': True, 'job_id': '...'} 或 {'success': False, 'error': '...'}
    """
    if not filename:
        return UploadResult(success=False, error='文件名为空')

    ext = os.path.splitext(filename)[1].lower()

    if ext not in config.get('allowed_extensions', ['.pdf']):
        return UploadResult(success=False, error=f'不支持的文件类型: {ext}')

    max_size = config.get('max_file_size_mb', 50) * 1024 * 1024
    if len(file_bytes) > max_size:
        return UploadResult(success=False, error=f'文件过大，最大 {config.get("max_file_size_mb", 50)}MB')

    safe_name = filename
    job_id = str(uuid.uuid4())
    jobs_dir = ensure_dir(app_root(), 'jobs')
    save_path = os.path.join(jobs_dir, f'{job_id}_{safe_name}')

    with open(save_path, 'wb') as f:
        f.write(file_bytes)

    actual_job_id = queue_mgr.add_job(
        filename, save_path, len(file_bytes), ext,
        duplex=int(duplex) if duplex in ('0', '1') else None,
        color=int(color) if color in ('0', '1') else None,
        copies=int(copies) if copies and copies.isdigit() else None,
        paper_size=paper_size or None,
        printer_name=printer or None,
        source=source,
    )

    logger.info(f'Upload success: {filename} -> job_id={actual_job_id}')
    return UploadResult(success=True, job_id=actual_job_id)
