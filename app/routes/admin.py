import os
import logging
from collections import deque
from flask import Blueprint, render_template, request, jsonify, current_app
from datetime import datetime

from app.auth import require_auth, check_auth
from app._paths import app_root

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger('print_server')


def get_job_service():
    return current_app.config['job_service']


def get_config():
    return current_app.config['app_config']


@admin_bp.route('/')
def dashboard():
    job_service = get_job_service()
    stats = job_service.get_stats()
    recent_jobs = job_service.list_jobs(limit=10, offset=0)
    return render_template('admin/dashboard.html', stats=stats, recent_jobs=recent_jobs)


@admin_bp.route('/history')
def history():
    job_service = get_job_service()
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    per_page = 20

    status_param = status if status else None
    search_param = search if search else None

    total = job_service.count_jobs(status=status_param, search=search_param)
    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    jobs = job_service.list_jobs(status=status_param, search=search_param, limit=per_page, offset=offset)

    return render_template('admin/history.html',
                           jobs=jobs,
                           total=total,
                           page=page,
                           total_pages=total_pages,
                           status_filter=status,
                           search=search)


@admin_bp.route('/logs')
def logs():
    return render_template('admin/logs.html')


@admin_bp.route('/api/logs')
def api_logs():
    """获取最新日志行"""
    lines = request.args.get('lines', 50, type=int)
    log_file = os.path.join(app_root(), 'logs', 'print_server.log')
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            last_lines = deque(f, maxlen=lines)
        return jsonify({'lines': list(last_lines)})
    except FileNotFoundError:
        return jsonify({'lines': []})
    except Exception as e:
        return jsonify({'lines': [f'[ERROR] 读取日志失败: {e}']})


@admin_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    config = get_config()

    if request.method == 'POST':
        if not check_auth():
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        try:
            def safe_int(val, default):
                try:
                    return int(val)
                except (ValueError, TypeError):
                    return default

            config.set('api_key', request.form.get('api_key', config.get('api_key', '')))
            config.set('default_printer', request.form.get('default_printer', ''))
            config.set('default_copies', safe_int(request.form.get('default_copies'), 1))
            config.set('default_duplex', request.form.get('default_duplex') == '1')
            config.set('default_color', request.form.get('default_color') == '1')
            config.set('excel_print_all_sheets', request.form.get('excel_print_all_sheets') == '1')
            config.set('ppt_output_type', request.form.get('ppt_output_type', 'slides'))
            config.set('paper_size', request.form.get('paper_size', 'A4'))

            for secret_field in ('quark_api_key_id', 'quark_api_key', 'dingtalk_webhook', 'bark_key'):
                val = request.form.get(secret_field, '')
                if val:
                    config.set(secret_field, val)

            config.set('notify_channel', request.form.get('notify_channel', 'disabled'))
            config.set('dingtalk_level', request.form.get('dingtalk_level', 'error'))
            config.set('bark_server', request.form.get('bark_server', 'https://api.day.app'))
            config.set('auto_retry_count', safe_int(request.form.get('auto_retry_count'), 0))
            config.set('port', safe_int(request.form.get('port'), 5000))
            config.set('log_level', request.form.get('log_level', 'INFO'))
            config.save()
            logger.info('配置已保存')
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f'保存配置失败: {e}')
            return jsonify({'success': False, 'error': str(e)}), 500

    job_service = get_job_service()
    printers = job_service.list_printers()
    return render_template('admin/settings.html', config=config, printers=printers)


@admin_bp.route('/printers')
def printers():
    config = get_config()
    job_service = get_job_service()
    printer_list = job_service.list_printers()
    return render_template('admin/printers.html', config=config, printers=printer_list)


@admin_bp.route('/upload')
def upload_page():
    config = get_config()
    job_service = get_job_service()
    printers = job_service.list_printers()
    return render_template('admin/upload.html',
        config=config,
        printers=printers,
        allowed_extensions=config.allowed_extensions
    )


@admin_bp.route('/api/upload', methods=['POST'])
@require_auth
def upload_file():
    """Web 上传打印"""
    job_service = get_job_service()
    result = job_service.submit(request, source='web')
    if not result['success']:
        return jsonify({'success': False, 'error': result['error']}), 400
    logger.info(f'Web 上传成功: job_id={result["job_id"]}')
    return jsonify({'success': True, 'job_id': result['job_id']})


@admin_bp.route('/api/set_default_printer', methods=['POST'])
@require_auth
def set_default_printer():
    config = get_config()
    data = request.get_json()
    printer = data.get('printer', '')
    config.set('default_printer', printer)
    config.save()
    logger.info(f'默认打印机已设置: {printer}')
    return jsonify({'success': True})


@admin_bp.route('/api/retry/<job_id>', methods=['POST'])
@require_auth
def retry_job(job_id):
    job_service = get_job_service()
    new_id, error = job_service.retry(job_id)
    if error:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'new_job_id': new_id})


@admin_bp.route('/api/cancel/<job_id>', methods=['POST'])
@require_auth
def cancel_job(job_id):
    job_service = get_job_service()
    success, error = job_service.cancel(job_id)
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True})


@admin_bp.route('/api/test_notification', methods=['POST'])
@require_auth
def test_notification():
    config = current_app.config['app_config']
    channel = config.get('notify_channel', 'disabled')
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        if channel == 'dingtalk':
            dt = current_app.config['dingtalk']
            if dt:
                dt.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}', level='info')
        elif channel == 'bark':
            bk = current_app.config['bark']
            if bk:
                bk.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}')
    except Exception as e:
        logger.warning(f'发送测试通知失败: {e}')
        return jsonify({'success': False, 'error': f'发送失败: {e}'}), 500
    return jsonify({'success': True, 'channel': channel})


@admin_bp.route('/api/cancel_all_queued', methods=['POST'])
@require_auth
def cancel_all_queued():
    job_service = get_job_service()
    count = job_service.cancel_all_queued()
    return jsonify({'success': True, 'cancelled': count})
