"""文件上传辅助模块：统一处理文件接收、校验、保存和入队"""

import uuid
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.core._paths import ensure_dir, persistent_dir

# 文件头魔数 → 扩展名映射（仅校验常见格式）
MAGIC_NUMBERS: dict[bytes, tuple[str, ...]] = {
    b'%PDF': ('.pdf',),
    b'\xff\xd8\xff': ('.jpg', '.jpeg'),
    b'\x89PNG\r\n\x1a\n': ('.png',),
    b'GIF87a': ('.gif',),
    b'GIF89a': ('.gif',),
    b'BM': ('.bmp',),
    b'II*\x00': ('.tiff', '.tif'),
    b'MM\x00*': ('.tiff', '.tif'),
    b'RIFF': ('.webp',),  # WEBP 以 RIFF 开头
    b'\x00\x00\x01\x00': ('.ico',),
    b'\x00\x00\x02\x00': ('.ico',),
    b'ftyp': ('.heic', '.heif'),  # HEIC/HEIF 包含 ftyp box
    b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': ('.doc', '.xls', '.ppt'),  # CFB
    b'PK\x03\x04': ('.docx', '.xlsx', '.pptx'),  # Office Open XML
}


@dataclass
class UploadResult:
    """文件上传结果"""

    success: bool
    job_id: str = ''
    error: str = ''


def _check_magic_number(file_bytes: bytes, ext: str) -> bool:
    """检查文件头魔数是否与扩展名匹配"""
    for magic, exts in MAGIC_NUMBERS.items():
        if ext in exts and file_bytes[: len(magic)] == magic:
            return True
    # HEIC/HEIF 的 ftyp 在偏移 4 处
    if ext in ('.heic', '.heif') and len(file_bytes) > 8 and file_bytes[4:8] == b'ftyp':
        return True
    # 未注册的扩展名跳过魔数检查
    return True


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
    page_range: str | None = None,
    nup: int | None = None,
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

    ext = Path(filename).suffix.lower()

    if ext not in config.get('allowed_extensions', ['.pdf']):
        return UploadResult(success=False, error=f'不支持的文件类型: {ext}')

    max_size = config.get('max_file_size_mb', 50) * 1024 * 1024
    if len(file_bytes) > max_size:
        return UploadResult(
            success=False, error=f'文件过大，最大 {config.get("max_file_size_mb", 50)}MB'
        )

    # 文件头魔数校验
    if not _check_magic_number(file_bytes, ext):
        return UploadResult(success=False, error=f'文件内容与扩展名不匹配: {ext}')

    safe_name = Path(filename).name
    ext = Path(safe_name).suffix or '.bin'
    job_id = str(uuid.uuid4())
    jobs_dir = ensure_dir(persistent_dir(), 'jobs')
    save_path = Path(jobs_dir) / f'{job_id}{ext}'

    with open(save_path, 'wb') as f:
        f.write(file_bytes)

    # 写入后回读校验大小
    try:
        written_size = save_path.stat().st_size
        if written_size != len(file_bytes):
            save_path.unlink(missing_ok=True)
            return UploadResult(
                success=False,
                error=f'文件写入不完整: 期望 {len(file_bytes)} 字节，实际 {written_size} 字节',
            )
    except OSError as e:
        save_path.unlink(missing_ok=True)
        return UploadResult(success=False, error=f'文件写入校验失败: {e}')

    actual_job_id = queue_mgr.add_job(
        filename,
        str(save_path),
        len(file_bytes),
        ext,
        duplex=int(duplex) if duplex in ('0', '1') else None,
        color=int(color) if color in ('0', '1') else None,
        copies=int(copies) if copies and copies.isdigit() else None,
        paper_size=paper_size or None,
        printer_name=printer or None,
        source=source,
        page_range=page_range or None,
        nup=nup or None,
    )

    logger.info(f'Upload success: {filename} -> job_id={actual_job_id}')
    return UploadResult(success=True, job_id=actual_job_id)
