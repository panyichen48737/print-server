import os
from collections import deque
from datetime import datetime
from loguru import logger
from jinja2 import pass_context
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app.upload_helper import handle_file_upload
from app._paths import app_root, data_root

admin_router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(data_root(), 'app', 'templates'))


# -- Custom url_for for Jinja2 templates (Flask blueprint compatibility) --

@pass_context
def _url_for(ctx, name, **path_params):
    """Jinja2 global: compat url_for that strips 'admin.' prefix for FastAPI."""
    request = ctx.get('request')
    # Flask blueprint compatibility: 'admin.history' -> 'history'
    if name.startswith('admin.'):
        name = name.split('.', 1)[1]
    # Flask uses 'filename' kwarg, Starlette uses 'path' kwarg
    if name == 'static' and 'filename' in path_params:
        path_params['path'] = path_params.pop('filename')
    return str(request.url_for(name, **path_params))


templates.env.globals['url_for'] = _url_for


# -- Template routes --

@admin_router.get('/', name='dashboard')
async def dashboard(request: Request):
    queue_mgr = request.app.state.queue_manager
    stats = queue_mgr.get_stats()
    recent_jobs = queue_mgr.get_jobs(limit=10, offset=0)
    return templates.TemplateResponse(
        'admin/dashboard.html',
        {'request': request, 'stats': stats, 'recent_jobs': recent_jobs}
    )


@admin_router.get('/history', name='history')
async def history(
    request: Request,
    page: int = 1,
    status: str = '',
    search: str = '',
    date_from: str = '',
    date_to: str = '',
):
    queue_mgr = request.app.state.queue_manager
    per_page = 20

    status_param = status if status else None
    search_param = search if search else None

    total = queue_mgr.count_jobs(status=status_param, search=search_param)
    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    jobs = queue_mgr.get_jobs(status=status_param, search=search_param, limit=per_page, offset=offset)

    return templates.TemplateResponse('admin/history.html', {
        'request': request, 'jobs': jobs,
        'total': total, 'page': page, 'total_pages': total_pages,
        'status_filter': status, 'search': search,
        'date_from': date_from, 'date_to': date_to,
    })


@admin_router.get('/logs', name='logs')
async def logs(request: Request):
    return templates.TemplateResponse('admin/logs.html', {'request': request})


@admin_router.get('/api/logs')
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


@admin_router.get('/settings', name='settings')
async def settings_get(request: Request):
    config = request.app.state.app_config
    queue_mgr = request.app.state.queue_manager
    printers = queue_mgr.get_printers()
    return templates.TemplateResponse(
        'admin/settings.html',
        {'request': request, 'config': config, 'printers': printers}
    )


@admin_router.post('/settings')
async def settings_post(
    request: Request,
    api_key: str = Form(''),
    default_printer: str = Form(''),
    default_copies: str = Form('1'),
    default_duplex: str = Form('0'),
    default_color: str = Form('0'),
    excel_print_all_sheets: str = Form('1'),
    ppt_output_type: str = Form('slides'),
    paper_size: str = Form('A4'),
    quark_api_key_id: str = Form(''),
    quark_api_key: str = Form(''),
    dingtalk_webhook: str = Form(''),
    bark_key: str = Form(''),
    notify_channel: str = Form('disabled'),
    dingtalk_level: str = Form('error'),
    bark_server: str = Form('https://api.day.app'),
    auto_retry_count: str = Form('0'),
    port: str = Form('5000'),
    log_level: str = Form('INFO'),
    auth=Depends(require_auth),
):
    config = request.app.state.app_config
    try:
        def safe_int(val, default):
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        config.set('api_key', api_key)
        config.set('default_printer', default_printer)
        config.set('default_copies', safe_int(default_copies, 1))
        config.set('default_duplex', default_duplex == '1')
        config.set('default_color', default_color == '1')
        config.set('excel_print_all_sheets', excel_print_all_sheets == '1')
        config.set('ppt_output_type', ppt_output_type)
        config.set('paper_size', paper_size)

        for secret_field, val in [
            ('quark_api_key_id', quark_api_key_id),
            ('quark_api_key', quark_api_key),
            ('dingtalk_webhook', dingtalk_webhook),
            ('bark_key', bark_key),
        ]:
            if val:
                config.set(secret_field, val)

        config.set('notify_channel', notify_channel)
        config.set('dingtalk_level', dingtalk_level)
        config.set('bark_server', bark_server)
        config.set('auto_retry_count', safe_int(auto_retry_count, 0))
        config.set('port', safe_int(port, 5000))
        config.set('log_level', log_level)
        config.save()
        logger.info('配置已保存')
        return {'success': True}
    except Exception as e:
        logger.error(f'保存配置失败: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get('/printers', name='printers')
async def printers(request: Request):
    config = request.app.state.app_config
    queue_mgr = request.app.state.queue_manager
    printer_list = queue_mgr.get_printers()
    return templates.TemplateResponse(
        'admin/printers.html',
        {'request': request, 'config': config, 'printers': printer_list}
    )


@admin_router.get('/upload', name='upload_page')
async def upload_page(request: Request):
    config = request.app.state.app_config
    queue_mgr = request.app.state.queue_manager
    printer_list = queue_mgr.get_printers()
    return templates.TemplateResponse('admin/upload.html', {
        'request': request,
        'config': config,
        'printers': printer_list,
        'allowed_extensions': config.allowed_extensions,
    })


@admin_router.post('/api/upload')
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
    config = request.app.state.app_config
    queue_mgr = request.app.state.queue_manager
    content = await file.read()
    result = handle_file_upload(
        file.filename, content, config, queue_mgr, source='web',
        printer=printer, copies=copies, duplex=duplex,
        color=color, paper_size=paper_size,
    )
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    logger.info(f'Web 上传成功: job_id={result["job_id"]}')
    return {'success': True, 'job_id': result['job_id']}


@admin_router.post('/api/set_default_printer')
async def set_default_printer(
    request: Request,
    body: dict,
    auth=Depends(require_auth),
):
    config = request.app.state.app_config
    printer = body.get('printer', '')
    config.set('default_printer', printer)
    config.save()
    logger.info(f'默认打印机已设置: {printer}')
    return {'success': True}


@admin_router.post('/api/retry/{job_id}')
async def retry_job(
    job_id: str,
    request: Request,
    auth=Depends(require_auth),
):
    queue_mgr = request.app.state.queue_manager
    new_id, error = queue_mgr.retry_job(job_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {'success': True, 'new_job_id': new_id}


@admin_router.post('/api/cancel/{job_id}')
async def cancel_job(
    job_id: str,
    request: Request,
    auth=Depends(require_auth),
):
    queue_mgr = request.app.state.queue_manager
    success, error = queue_mgr.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {'success': True}


@admin_router.post('/api/test_notification')
async def test_notification(
    request: Request,
    auth=Depends(require_auth),
):
    config = request.app.state.app_config
    channel = config.get('notify_channel', 'disabled')
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        if channel == 'dingtalk':
            dt = getattr(request.app.state, 'dingtalk', None)
            if dt:
                dt.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}', level='info')
        elif channel == 'bark':
            bk = getattr(request.app.state, 'bark', None)
            if bk:
                bk.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}')
    except Exception as e:
        logger.warning(f'发送测试通知失败: {e}')
        raise HTTPException(status_code=500, detail=f'发送失败: {e}')
    return {'success': True, 'channel': channel}


@admin_router.post('/api/cancel_all_queued')
async def cancel_all_queued(
    request: Request,
    auth=Depends(require_auth),
):
    queue_mgr = request.app.state.queue_manager
    count = queue_mgr.cancel_all_queued()
    return {'success': True, 'cancelled': count}
