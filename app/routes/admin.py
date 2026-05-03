import os
import logging
from flask import Blueprint, render_template, request, jsonify, current_app
from werkzeug.utils import secure_filename

admin_bp = Blueprint('admin', __name__)
logger = logging.getLogger('print_server')


def get_queue_manager():
    return current_app.config['queue_manager']


def get_config():
    return current_app.config['app_config']


@admin_bp.route('/')
def dashboard():
    queue_mgr = get_queue_manager()
    stats = queue_mgr.get_stats()
    recent_jobs = queue_mgr.get_jobs(limit=10, offset=0)
    return render_template('admin/dashboard.html', stats=stats, recent_jobs=recent_jobs)


@admin_bp.route('/history')
def history():
    queue_mgr = get_queue_manager()
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    per_page = 20

    status_param = status if status else None
    search_param = search if search else None

    total = queue_mgr.count_jobs(status=status_param, search=search_param)
    total_pages = max(1, (total + per_page - 1) // per_page)
    offset = (page - 1) * per_page

    jobs = queue_mgr.get_jobs(status=status_param, search=search_param, limit=per_page, offset=offset)

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
    from app._paths import app_root
    log_file = os.path.join(app_root(), 'logs', 'print_server.log')
    try:
        from collections import deque
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
        try:
            config.set('api_key', request.form.get('api_key', config.get('api_key', '')))
            config.set('default_printer', request.form.get('default_printer', ''))
            config.set('default_copies', int(request.form.get('default_copies', 1)))
            config.set('default_duplex', request.form.get('default_duplex') == '1')
            config.set('default_color', request.form.get('default_color') == '1')
            config.set('excel_print_all_sheets', request.form.get('excel_print_all_sheets') == '1')
            config.set('ppt_output_type', request.form.get('ppt_output_type', 'slides'))
            config.set('paper_size', request.form.get('paper_size', 'A4'))
            config.set('quark_api_key_id', request.form.get('quark_api_key_id', ''))
            config.set('quark_api_key', request.form.get('quark_api_key', ''))
            config.set('dingtalk_enabled', request.form.get('dingtalk_enabled') == '1')
            config.set('dingtalk_webhook', request.form.get('dingtalk_webhook', ''))
            config.set('dingtalk_level', request.form.get('dingtalk_level', 'error'))
            config.set('port', int(request.form.get('port', 5000)))
            config.set('log_level', request.form.get('log_level', 'INFO'))
            config.save()
            logger.info('配置已保存')
            return jsonify({'success': True})
        except Exception as e:
            logger.error(f'保存配置失败: {e}')
            return jsonify({'success': False, 'error': str(e)}), 500

    queue_mgr = get_queue_manager()
    printers = queue_mgr.get_printers()
    return render_template('admin/settings.html', config=config, printers=printers)


@admin_bp.route('/printers')
def printers():
    config = get_config()
    queue_mgr = get_queue_manager()
    printer_list = queue_mgr.get_printers()
    return render_template('admin/printers.html', config=config, printers=printer_list)


@admin_bp.route('/upload')
def upload_page():
    config = get_config()
    queue_mgr = get_queue_manager()
    printers = queue_mgr.get_printers()
    return render_template('admin/upload.html',
        config=config,
        printers=printers,
        allowed_extensions=config.allowed_extensions
    )


@admin_bp.route('/api/upload', methods=['POST'])
def upload_file():
    """Web 上传打印（内网无鉴权）"""
    if 'file' not in request.files:
        return jsonify({'error': '未选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '文件名为空'}), 400

    config = get_config()
    original_name = file.filename
    ext = os.path.splitext(original_name)[1].lower()

    # 校验扩展名
    if ext not in config.allowed_extensions:
        return jsonify({'error': f'文件类型 {ext} 不允许'}), 400

    # 先检查 Content-Length 避免大文件写入
    max_size = config.max_file_size_mb * 1024 * 1024
    cl = request.headers.get('Content-Length')
    if cl and int(cl) > max_size:
        return jsonify({'error': f'文件过大，最大 {config.max_file_size_mb}MB'}), 400

    # 保存文件
    import uuid
    from app._paths import app_root, ensure_dir
    jobs_dir = ensure_dir(app_root(), 'jobs')
    safe_name = f"{uuid.uuid4()}_{secure_filename(original_name) or f'file{ext}'}"
    save_path = os.path.join(jobs_dir, safe_name)
    file.save(save_path)
    file_size = os.path.getsize(save_path)

    # 校验大小（fallback）
    if file_size > max_size:
        os.remove(save_path)
        return jsonify({'error': f'文件过大，最大 {config.max_file_size_mb}MB'}), 400

    # 获取打印参数
    printer = request.form.get('printer') or None
    copies_s = request.form.get('copies')
    copies = int(copies_s) if copies_s and copies_s.isdigit() else None
    duplex_s = request.form.get('duplex')
    duplex = int(duplex_s) if duplex_s in ('0', '1') else None
    color_s = request.form.get('color')
    color = int(color_s) if color_s in ('0', '1') else None
    paper_size = request.form.get('paper_size') or None

    if copies is not None and (copies < 1 or copies > 99):
        return jsonify({'error': '份数必须在 1-99 之间'}), 400

    queue_mgr = get_queue_manager()
    job_id = queue_mgr.add_job(
        original_name, save_path, file_size, ext,
        duplex=duplex, color=color, copies=copies,
        paper_size=paper_size, printer_name=printer
    )

    logger.info(f'Web 上传成功: {original_name} -> job_id={job_id}')
    return jsonify({
        'success': True,
        'job_id': job_id,
        'filename': original_name,
        'file_size': file_size,
        'file_type': ext
    })


@admin_bp.route('/api/set_default_printer', methods=['POST'])
def set_default_printer():
    config = get_config()
    data = request.get_json()
    printer = data.get('printer', '')
    config.set('default_printer', printer)
    config.save()
    logger.info(f'默认打印机已设置: {printer}')
    return jsonify({'success': True})


@admin_bp.route('/api/retry/<job_id>', methods=['POST'])
def retry_job(job_id):
    queue_mgr = get_queue_manager()
    new_id, error = queue_mgr.retry_job(job_id)
    if error:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True, 'new_job_id': new_id})


@admin_bp.route('/api/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    queue_mgr = get_queue_manager()
    success, error = queue_mgr.cancel_job(job_id)
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True})
