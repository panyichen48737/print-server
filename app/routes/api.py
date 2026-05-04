import os
import json
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from app.auth import require_auth
from app.upload_helper import handle_file_upload

api_router = APIRouter()


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
    queue_mgr = request.app.state.queue_manager
    content = await file.read()
    result = handle_file_upload(
        file.filename, content, config, queue_mgr, source='ios',
        printer=printer, copies=copies, duplex=duplex,
        color=color, paper_size=paper_size,
    )
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    return {'status': 'queued', 'job_id': result['job_id']}


@api_router.get('/status/{job_id}')
async def get_status(job_id: str, request: Request):
    """查询任务状态"""
    queue_mgr = request.app.state.queue_manager
    job = queue_mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='任务不存在')
    result = {'success': True, 'status': job['status'], 'job_id': job['id']}
    if job['status'] == 'failed' and job.get('error_message'):
        result['error'] = job['error_message']
    return result


@api_router.get('/printers')
async def list_printers(request: Request):
    """获取可用打印机列表"""
    queue_mgr = request.app.state.queue_manager
    return {'printers': queue_mgr.get_printers()}


@api_router.get('/printers/status')
async def printer_status(request: Request):
    """获取全部打印机实时状态"""
    pm = getattr(request.app.state, 'printer_monitor', None)
    if not pm:
        return {'printers': {}}
    return {'printers': pm.get_all_statuses()}


@api_router.post('/cancel/{job_id}')
async def cancel_job_api(
    job_id: str,
    request: Request,
    auth=Depends(require_auth),
):
    """取消任务"""
    queue_mgr = request.app.state.queue_manager
    success, error = queue_mgr.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {'success': True}


@api_router.get('/events')
async def sse_events(request: Request):
    """Server-Sent Events endpoint"""
    broadcaster = request.app.state.sse
    sub_id, q = broadcaster.subscribe()

    def generate():
        try:
            while True:
                event_type, data = q.get()
                yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            broadcaster.unsubscribe(sub_id)

    return StreamingResponse(generate(), media_type='text/event-stream')
