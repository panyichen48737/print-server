import os
from loguru import logger
from jinja2 import pass_context
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import require_auth
from app._paths import data_root
from app.utils import safe_int as _safe_int, format_time
from app.schemas import AdminActionResponse, SettingsResponse

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
    repo = request.app.state.job_repo
    stats = repo.get_stats()
    recent_jobs = repo.get_jobs(limit=10, offset=0)
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
    repo = request.app.state.job_repo
    per_page = 20

    status_param = status or None
    search_param = search or None

    total = repo.count_jobs(status=status_param, search=search_param)
    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    jobs = repo.get_jobs(status=status_param, search=search_param, limit=per_page, offset=offset)

    return templates.TemplateResponse('admin/history.html', {
        'request': request, 'jobs': jobs,
        'total': total, 'page': page, 'total_pages': total_pages,
        'status_filter': status, 'search': search,
        'date_from': date_from, 'date_to': date_to,
    })


@admin_router.get('/logs', name='logs')
async def logs(request: Request):
    return templates.TemplateResponse('admin/logs.html', {'request': request})


@admin_router.get('/settings', name='settings')
async def settings_get(request: Request):
    config = request.app.state.app_config
    monitor = request.app.state.printer_monitor
    printers = list(monitor.get_all_statuses().keys())
    return templates.TemplateResponse(
        'admin/settings.html',
        {'request': request, 'config': config, 'printers': printers}
    )


@admin_router.post('/settings', response_model=SettingsResponse)
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
        updates = {
            'api_key': api_key,
            'default_printer': default_printer,
            'default_copies': _safe_int(default_copies, 1),
            'default_duplex': default_duplex == '1',
            'default_color': default_color == '1',
            'excel_print_all_sheets': excel_print_all_sheets == '1',
            'ppt_output_type': ppt_output_type,
            'paper_size': paper_size,
            'notify_channel': notify_channel,
            'dingtalk_level': dingtalk_level,
            'bark_server': bark_server,
            'auto_retry_count': _safe_int(auto_retry_count, 0),
            'port': max(1024, min(65535, _safe_int(port, 5000))),
            'log_level': log_level,
        }

        for secret_field, val in [
            ('quark_api_key_id', quark_api_key_id),
            ('quark_api_key', quark_api_key),
            ('dingtalk_webhook', dingtalk_webhook),
            ('bark_key', bark_key),
        ]:
            updates[secret_field] = val

        config.set_many(updates)
        config.save()
        logger.info('配置已保存')
        return {'success': True}
    except Exception as e:
        logger.error(f'保存配置失败: {e}')
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.get('/printers', name='printers')
async def printers(request: Request):
    config = request.app.state.app_config
    monitor = request.app.state.printer_monitor
    printer_list = list(monitor.get_all_statuses().keys())
    return templates.TemplateResponse(
        'admin/printers.html',
        {'request': request, 'config': config, 'printers': printer_list}
    )


@admin_router.get('/upload', name='upload_page')
async def upload_page(request: Request):
    config = request.app.state.app_config
    monitor = request.app.state.printer_monitor
    printer_list = list(monitor.get_all_statuses().keys())
    return templates.TemplateResponse('admin/upload.html', {
        'request': request,
        'config': config,
        'printers': printer_list,
        'allowed_extensions': config.get('allowed_extensions', []),
    })


@admin_router.get('/api/stats')
async def api_stats(request: Request):
    """HTMX: 返回统计面板 HTML 片段"""
    stats = request.app.state.job_repo.get_stats()
    return templates.TemplateResponse('admin/_stats.html', {
        'request': request, 'stats': stats,
    })


@admin_router.post('/api/test_notification')
async def admin_test_notification(request: Request, background_tasks: BackgroundTasks):
    """HTMX: 发送测试通知，返回 HTML 片段"""
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
    return HTMLResponse(f'<span style="color: var(--text-success);">✓ 测试通知已加入发送队列 ({channel})</span>')


@admin_router.post('/api/restart', response_model=AdminActionResponse)
async def api_restart(request: Request, auth=Depends(require_auth)):
    """重启后台服务——通过 uvicorn.Server.should_exit 触发 lifespan 优雅关闭"""
    server = getattr(request.app.state, '_server', None)
    if server:
        server.should_exit = True
    return {'success': True}
