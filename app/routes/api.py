"""打印任务 API 路由 — 上传、取消、状态查询、打印机管理"""

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

from app.core.auth import require_auth
from app.core.exceptions import FileTypeError, PrintServerError
from app.core.utils import format_time
from app.services.upload import handle_file_upload

api_router = APIRouter()


async def _handle_upload(request, file, printer, copies, duplex, color, paper_size, source):
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
        )
    except FileTypeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except PrintServerError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {'success': True, 'job_id': result.job_id}


@api_router.post('/print')
async def print_file(
    request: Request,
    file: UploadFile = File(...),
    printer: str = Form(None),
    copies: str = Form(None),
    duplex: str = Form(None),
    color: str = Form(None),
    paper_size: str = Form(None),
    _auth=Depends(require_auth),
):
    """提交打印任务（iOS 端使用）"""
    return await _handle_upload(request, file, printer, copies, duplex, color, paper_size, 'ios')


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


@api_router.post('/upload')
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    printer: str = Form(None),
    copies: str = Form(None),
    duplex: str = Form(None),
    color: str = Form(None),
    paper_size: str = Form(None),
    _auth=Depends(require_auth),
):
    """Web 上传打印"""
    result = await _handle_upload(request, file, printer, copies, duplex, color, paper_size, 'web')
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
