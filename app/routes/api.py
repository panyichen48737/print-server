import os
import json
from collections import deque
from loguru import logger
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from app.auth import require_auth
from app._paths import app_root
from app.version import __version__
from app.services.upload import handle_file_upload
from app.utils import format_time
from app.schemas import (
    HealthResponse, PrintResponse, StatusResponse, CancelResponse, CancelAllResponse,
    PrinterListResponse, PrinterStatusResponse, RetryResponse, LogsResponse,
    NotificationTestResponse, SetDefaultPrinterRequest,
)

api_router = APIRouter()


async def _handle_upload(request, file, printer, copies, duplex, color, paper_size, source):
    config = request.app.state.app_config
    job_queue = request.app.state.job_queue
    content = await file.read()
    result = handle_file_upload(
        file.filename, content, config, job_queue,
        source=source, printer=printer, copies=copies,
        duplex=duplex, color=color, paper_size=paper_size,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {'success': True, 'job_id': result.job_id}


@api_router.get('/health', response_model=HealthResponse)
async def health(request: Request):
    return {
        'status': 'ok',
        'version': __version__,
        'queue_size': request.app.state.job_queue.queue_size(),
    }


@api_router.get('/logs', response_model=LogsResponse)
async def api_logs(request: Request, lines: int = 50):
    """获取最新日志行"""
    log_file = os.path.join(app_root(), 'logs', 'print_server.log')
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            last_lines = deque(f, maxlen=lines)
        return {'lines': list(last_lines)}
    except FileNotFoundError:
        return {'lines': []}
    except Exception as e:
        return {'lines': [f'[ERROR] 读取日志失败: {e}']}


@api_router.post('/print', response_model=PrintResponse)
async def print_file(
    request: Request,
    file: UploadFile = File(...),
    printer: str = Form(None),
    copies: str = Form(None),
    duplex: str = Form(None),
    color: str = Form(None),
    paper_size: str = Form(None),
    auth=Depends(require_auth),
):
    """提交打印任务（iOS 端使用）"""
    return await _handle_upload(request, file, printer, copies, duplex, color, paper_size, 'ios')


@api_router.get('/status/{job_id}', response_model=StatusResponse)
async def get_status(job_id: str, request: Request):
    """查询任务状态"""
    job = request.app.state.job_repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='任务不存在')
    result = {'success': True, 'status': job['status'], 'job_id': job['id']}
    if job['status'] == 'failed' and job.get('error_message'):
        result['error'] = job['error_message']
    return result


@api_router.get('/printers', response_model=PrinterListResponse)
async def list_printers(request: Request):
    """获取可用打印机列表"""
    monitor = request.app.state.printer_monitor
    return {'printers': list(monitor.get_all_statuses().keys())}


@api_router.get('/printers/status', response_model=PrinterStatusResponse)
async def printer_status(request: Request):
    """获取全部打印机实时状态"""
    monitor = request.app.state.printer_monitor
    return {'printers': monitor.get_all_statuses()}


@api_router.post('/cancel/{job_id}', response_model=CancelResponse)
async def cancel_job_api(
    job_id: str,
    request: Request,
    auth=Depends(require_auth),
):
    """取消任务"""
    job_queue = request.app.state.job_queue
    print_engine = request.app.state.print_engine
    success, error = job_queue.cancel_job(job_id, print_engine=print_engine)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {'success': True}


@api_router.post('/upload', response_model=PrintResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    printer: str = Form(None),
    copies: str = Form(None),
    duplex: str = Form(None),
    color: str = Form(None),
    paper_size: str = Form(None),
    auth=Depends(require_auth),
):
    """Web 上传打印"""
    result = await _handle_upload(request, file, printer, copies, duplex, color, paper_size, 'web')
    logger.info(f'Web 上传成功: job_id={result["job_id"]}')
    return result


@api_router.post('/set_default_printer')
async def set_default_printer(
    request: Request,
    body: SetDefaultPrinterRequest,
    auth=Depends(require_auth),
):
    config = request.app.state.app_config
    config.set('default_printer', body.printer)
    config.save()
    logger.info(f'默认打印机已设置: {body.printer}')
    return {'success': True}


@api_router.post('/retry/{job_id}', response_model=RetryResponse)
async def retry_job(
    job_id: str,
    request: Request,
    auth=Depends(require_auth),
):
    job_queue = request.app.state.job_queue
    new_id, error = job_queue.retry_job(job_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {'success': True, 'new_job_id': new_id}


@api_router.post('/test_notification', response_model=NotificationTestResponse)
async def test_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    auth=Depends(require_auth),
):
    config = request.app.state.app_config
    channel = config.get('notify_channel', 'disabled')
    time_str = format_time()

    def _send():
        dingtalk = getattr(request.app.state, 'dingtalk', None)
        bark = getattr(request.app.state, 'bark', None)
        try:
            if channel == 'dingtalk' and dingtalk:
                dingtalk.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}', level='info')
            elif channel == 'bark' and bark:
                bark.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}')
        except Exception as e:
            logger.warning(f'发送测试通知失败: {e}')

    background_tasks.add_task(_send)
    return {'success': True, 'channel': channel}


@api_router.post('/cancel_all_queued', response_model=CancelAllResponse)
async def cancel_all_queued(
    request: Request,
    auth=Depends(require_auth),
):
    job_queue = request.app.state.job_queue
    count = job_queue.cancel_all_queued()
    return {'success': True, 'cancelled': count}


@api_router.get('/events')
async def sse_events(request: Request):
    """Server-Sent Events endpoint"""
    broadcaster = request.app.state.sse
    sub_id, q = broadcaster.subscribe()

    import queue as _queue
    import time as _time

    start = _time.monotonic()
    MAX_DURATION = 3600

    def generate():
        try:
            while True:
                elapsed = _time.monotonic() - start
                if elapsed > MAX_DURATION:
                    break
                try:
                    event_type, data = q.get(timeout=30)
                    yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                except _queue.Empty:
                    continue
        except GeneratorExit:
            pass
        finally:
            broadcaster.unsubscribe(sub_id)

    return StreamingResponse(generate(), media_type='text/event-stream')
