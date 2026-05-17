"""打印任务 API 路由 — 上传、取消、状态查询、打印机管理"""

import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from loguru import logger

from app.core import _paths as app_core_paths
from app.core.auth import require_auth
from app.core.exceptions import FileTypeError, PrintServerError
from app.core.schemas import (
    BatchImagesResponse,
    ErrorDetail,
    PrintConfigResponse,
    PrintResponse,
    QueuePositionResponse,
)
from app.core.utils import format_time, safe_remove
from app.services.upload import handle_file_upload

api_router = APIRouter()


async def _handle_upload(
    request, file, printer, copies, duplex, color, paper_size, source, page_range=None, nup=None
):
    config = request.app.state.app_config
    job_queue = request.app.state.job_queue
    content = await file.read()
    try:
        result = handle_file_upload(
            file.filename,
            content,
            config,
            job_queue,
            source=source,
            printer=printer,
            copies=copies,
            duplex=duplex,
            color=color,
            paper_size=paper_size,
            page_range=page_range,
            nup=nup,
        )
    except FileTypeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except PrintServerError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {'success': True, 'job_id': result.job_id}


@api_router.post('/print', response_model=PrintResponse, responses={400: {'model': ErrorDetail}})
async def print_file(
    request: Request,
    file: UploadFile = File(...),
    printer: str = Form(None),
    copies: str = Form(None),
    duplex: str = Form(None),
    color: str = Form(None),
    paper_size: str = Form(None),
    page_range: str = Form(None),
    nup: str = Form(None),
    _auth=Depends(require_auth),
):
    """提交打印任务（iOS 端使用）

    - file: 要打印的文件（PDF/Office/图片）
    - printer: 打印机名称（可选，默认使用服务器默认打印机）
    - copies: 份数（可选，默认 1）
    - duplex: 双面打印（可选，"0"或"1"）
    - color: 彩色打印（可选，"0"或"1"）
    - paper_size: 纸张大小（可选，"A4"/"Letter"/"A3"）
    - page_range: 页码范围（可选，如 "1-3,5,7-9"）
    - nup: 多页合一（可选，"2"/"4"/"6"/"8"/"16"）
    """
    nup_val = int(nup) if nup and nup.isdigit() else None
    return await _handle_upload(
        request,
        file,
        printer,
        copies,
        duplex,
        color,
        paper_size,
        'ios',
        page_range=page_range,
        nup=nup_val,
    )


@api_router.post(
    '/print/images',
    response_model=BatchImagesResponse,
    responses={400: {'model': ErrorDetail}},
)
async def print_images_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    printer: str = Form(None),
    copies: str = Form(None),
    duplex: str = Form(None),
    color: str = Form(None),
    paper_size: str = Form(None),
    _auth=Depends(require_auth),
):
    """多图片合并为一个打印任务

    - files: 多个图片文件，按提交顺序打印
    - 所有图片合并为一个多页 PDF 后作为一个任务提交
    """
    if not files:
        raise HTTPException(status_code=400, detail='至少需要一个图片文件')

    from app.printing.image_merger import merge_images_to_pdf

    config = request.app.state.app_config
    job_queue = request.app.state.job_queue
    upload_dir = app_core_paths.persistent_dir() / 'jobs'
    upload_dir.mkdir(parents=True, exist_ok=True)

    image_exts = {
        '.jpg',
        '.jpeg',
        '.png',
        '.bmp',
        '.gif',
        '.webp',
        '.tiff',
        '.tif',
        '.heic',
        '.heif',
    }
    saved_paths: list[str] = []
    file_size = 0
    first_name = ''
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in image_exts:
            continue
        content = await f.read()
        job_id = str(uuid.uuid4())
        save_path = upload_dir / f'{job_id}{ext}'
        save_path.write_bytes(content)
        saved_paths.append(str(save_path))
        file_size += len(content)
        if not first_name:
            first_name = Path(f.filename).stem

    if not saved_paths:
        raise HTTPException(status_code=400, detail='没有有效的图片文件')

    try:
        pdf_path = merge_images_to_pdf(
            saved_paths,
            paper_size=paper_size or config.get('paper_size', 'A4'),
            color=bool(color) if color in ('0', '1') else config.get('default_color', True),
            dpi=config.get('print_dpi', 300),
        )
    except Exception as e:
        for p in saved_paths:
            Path(p).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f'图片合并失败: {e}') from e

    for p in saved_paths:
        Path(p).unlink(missing_ok=True)

    try:
        actual_job_id = job_queue.add_job(
            f'{first_name} 等 {len(saved_paths)} 张图片',
            pdf_path,
            file_size,
            '.pdf',
            duplex=int(duplex) if duplex in ('0', '1') else None,
            color=int(color) if color in ('0', '1') else None,
            copies=int(copies) if copies and copies.isdigit() else None,
            paper_size=paper_size or None,
            printer_name=printer or None,
            source='api',
        )
    except Exception as e:
        safe_remove(pdf_path, '临时 PDF')
        raise HTTPException(status_code=500, detail=str(e)) from e

    logger.info(f'Batch images merged: {len(saved_paths)} pages -> job_id={actual_job_id}')
    return BatchImagesResponse(success=True, job_id=actual_job_id, pages=len(saved_paths))


@api_router.get('/status/{job_id}')
async def get_status(job_id: str, request: Request):
    """查询任务状态"""
    job = request.app.state.job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='任务不存在')
    result = {'success': True, 'status': job['status'], 'job_id': job['id']}
    if job['status'] == 'failed' and job.get('error_message'):
        result['error'] = job['error_message']
    return result


@api_router.get('/printers')
async def list_printers(request: Request):
    """获取可用打印机列表"""
    monitor = request.app.state.printer_monitor
    return {'printers': list(monitor.get_all_statuses().keys())}


@api_router.get('/printers/status')
async def printer_status(request: Request):
    """获取全部打印机实时状态"""
    monitor = request.app.state.printer_monitor
    return {'printers': monitor.get_all_statuses()}


@api_router.post('/cancel/{job_id}')
async def cancel_job_api(
    job_id: str,
    request: Request,
    _auth=Depends(require_auth),
):
    """取消任务"""
    job_queue = request.app.state.job_queue
    print_engine = request.app.state.print_engine
    try:
        success, error = job_queue.cancel_job(job_id, print_engine=print_engine)
    except PrintServerError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {'success': True}


@api_router.post('/upload', response_model=PrintResponse, responses={400: {'model': ErrorDetail}})
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    printer: str = Form(None),
    copies: str = Form(None),
    duplex: str = Form(None),
    color: str = Form(None),
    paper_size: str = Form(None),
    page_range: str = Form(None),
    nup: str = Form(None),
    _auth=Depends(require_auth),
):
    """Web 上传打印"""
    nup_val = int(nup) if nup and nup.isdigit() else None
    result = await _handle_upload(
        request,
        file,
        printer,
        copies,
        duplex,
        color,
        paper_size,
        'web',
        page_range=page_range,
        nup=nup_val,
    )
    logger.info(f'Web 上传成功: job_id={result["job_id"]}')
    return result


@api_router.post('/set_default_printer')
async def set_default_printer(
    request: Request,
    body: dict,
    _auth=Depends(require_auth),
):
    from app.core.schemas import SetDefaultPrinterRequest

    validated = SetDefaultPrinterRequest(**body)
    config = request.app.state.app_config
    config.set('default_printer', validated.printer)
    config.save()
    logger.info(f'默认打印机已设置: {validated.printer}')
    return {'success': True}


@api_router.post('/retry/{job_id}')
async def retry_job(
    job_id: str,
    request: Request,
    _auth=Depends(require_auth),
):
    job_queue = request.app.state.job_queue
    new_id, error = job_queue.retry_job(job_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {'success': True, 'new_job_id': new_id}


@api_router.post('/test_notification')
async def test_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    _auth=Depends(require_auth),
):
    config = request.app.state.app_config
    channel = config.get('notify_channel', 'disabled')
    time_str = format_time()

    def _send():
        dingtalk = getattr(request.app.state, 'dingtalk', None)
        bark = getattr(request.app.state, 'bark', None)
        try:
            if channel == 'dingtalk' and dingtalk:
                dingtalk.send_notification(
                    '测试通知', f'这是一条测试消息\n时间: {time_str}', level='info'
                )
            elif channel == 'bark' and bark:
                bark.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}')
        except Exception as e:
            logger.warning(f'发送测试通知失败: {e}')

    background_tasks.add_task(_send)
    return {'success': True, 'channel': channel}


@api_router.post('/cancel_all_queued')
async def cancel_all_queued(
    request: Request,
    _auth=Depends(require_auth),
):
    job_queue = request.app.state.job_queue
    count = job_queue.cancel_all_queued()
    return {'success': True, 'cancelled': count}


@api_router.get('/jobs')
async def api_jobs(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    search: str | None = None,
):
    """获取任务列表（JSON 格式）"""
    repo = request.app.state.job_repo
    jobs = repo.get_jobs(
        status=status or None,
        search=search or None,
        limit=limit,
        offset=offset,
    )
    total = repo.count_jobs(status=status or None, search=search or None)
    return {'jobs': jobs, 'total': total}


@api_router.get('/print/config', response_model=PrintConfigResponse)
async def get_print_config(request: Request):
    """获取服务器默认打印配置（无需认证，供 Scriptable 客户端预填表单）"""
    config = request.app.state.app_config
    monitor = request.app.state.printer_monitor
    printers = list(monitor.get_all_statuses().keys())
    if not printers:
        printers = [config.get('default_printer', '')] if config.get('default_printer') else []
    return {
        'default_printer': config.get('default_printer', ''),
        'printers': printers,
        'default_copies': config.get('default_copies', 1),
        'default_duplex': config.get('default_duplex', True),
        'default_color': config.get('default_color', True),
        'paper_size': config.get('paper_size', 'A4'),
    }


@api_router.get('/queue/position/{job_id}', response_model=QueuePositionResponse)
async def get_queue_position(job_id: str, request: Request):
    """查询任务在队列中的位置"""
    job = request.app.state.job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='任务不存在')

    job_queue = request.app.state.job_queue
    queue_size = job_queue.queue_size()
    position = 0

    if job['status'] == 'queued':
        # 获取所有排队任务，计算位置
        queued_jobs = request.app.state.job_repo.get_jobs_by_status('queued')
        for i, qj in enumerate(queued_jobs):
            if qj['id'] == job_id:
                position = i + 1
                break

    return {
        'job_id': job_id,
        'position': position,
        'queue_size': queue_size,
    }
