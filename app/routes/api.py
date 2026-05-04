import os
import json
from collections import deque
from loguru import logger
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from app.auth import require_auth
from app._paths import app_root
from app.upload_helper import handle_file_upload

api_router = APIRouter()


@api_router.get('/health')
async def health(request: Request):
    return {
        'status': 'ok',
        'version': '1.0.0',
        'queue_size': request.app.state.job_queue.queue_size(),
    }


@api_router.get('/logs')
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


@api_router.post('/print')
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
    config = request.app.state.app_config
    job_queue = request.app.state.job_queue
    content = await file.read()
    result = handle_file_upload(
        file.filename, content, config, job_queue,
        source='ios', printer=printer, copies=copies,
        duplex=duplex, color=color, paper_size=paper_size,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {'status': 'queued', 'job_id': result.job_id}


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
    pd = request.app.state.printer_discovery
    return {'printers': pd.list_printers()}


@api_router.get('/printers/status')
async def printer_status(request: Request):
    """获取全部打印机实时状态"""
    pd = getattr(request.app.state, 'printer_discovery', None)
    if not pd:
        return {'printers': {}}
    return {'printers': pd.get_all_statuses()}


@api_router.post('/cancel/{job_id}')
async def cancel_job_api(
    job_id: str,
    request: Request,
    auth=Depends(require_auth),
):
    """取消任务"""
    job_queue = request.app.state.job_queue
    success, error = job_queue.cancel_job(job_id)
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
    auth=Depends(require_auth),
):
    """Web 上传打印"""
    ps = request.app.state.print_service
    content = await file.read()
    result = ps.submit_print(
        file.filename, content, source='web',
        printer=printer, copies=copies, duplex=duplex,
        color=color, paper_size=paper_size,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    logger.info(f'Web 上传成功: job_id={result.job_id}')
    return {'success': True, 'job_id': result.job_id}


@api_router.post('/set_default_printer')
async def set_default_printer(
    request: Request,
    body: dict,
    auth=Depends(require_auth),
):
    ps = request.app.state.print_service
    printer = body.get('printer', '')
    ps.set_default_printer(printer)
    logger.info(f'默认打印机已设置: {printer}')
    return {'success': True}


@api_router.post('/retry/{job_id}')
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


@api_router.post('/test_notification')
async def test_notification(
    request: Request,
    auth=Depends(require_auth),
):
    ps = request.app.state.print_service
    config = request.app.state.app_config
    channel = config.get('notify_channel', 'disabled')
    dingtalk = getattr(request.app.state, 'dingtalk', None)
    bark = getattr(request.app.state, 'bark', None)
    try:
        ps.test_notification(channel, dingtalk, bark)
    except Exception as e:
        logger.warning(f'发送测试通知失败: {e}')
        raise HTTPException(status_code=500, detail=f'发送失败: {e}')
    return {'success': True, 'channel': channel}


@api_router.post('/cancel_all_queued')
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

    def generate():
        try:
            while True:
                try:
                    event_type, data = q.get(timeout=1)
                    yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                except _queue.Empty:
                    continue
        except GeneratorExit:
            broadcaster.unsubscribe(sub_id)

    return StreamingResponse(generate(), media_type='text/event-stream')
