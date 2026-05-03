import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

api_bp = Blueprint('api', __name__)


def get_queue_manager():
    return current_app.config['queue_manager']


def get_config():
    return current_app.config['app_config']


def check_auth():
    """验证 Bearer Token"""
    auth = request.headers.get('Authorization', '')
    config = get_config()
    expected = f'Bearer {config.api_key}'
    return auth == expected


@api_bp.route('/print', methods=['POST'])
def print_file():
    """提交打印任务"""
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    # Check extension
    config = get_config()
    # Preserve original filename but sanitize for filesystem safety
    original_name = file.filename
    safe_name = secure_filename(original_name) or f"file{os.path.splitext(original_name)[1].lower()}"
    filename = safe_name
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in config.allowed_extensions:
        return jsonify({'error': f'File type {ext} not allowed'}), 400

    # Save file
    job_id = str(uuid.uuid4())
    from app._paths import app_root, ensure_dir
    jobs_dir = ensure_dir(app_root(), 'jobs')
    save_path = os.path.join(jobs_dir, f'{job_id}_{filename}')
    file.save(save_path)
    file_size = os.path.getsize(save_path)

    # Check max file size
    max_size = config.max_file_size_mb * 1024 * 1024
    if file_size > max_size:
        os.remove(save_path)
        return jsonify({'error': f'File too large, max {config.max_file_size_mb}MB'}), 400

    # Queue job
    queue_mgr = get_queue_manager()
    new_job_id = queue_mgr.add_job(original_name, save_path, file_size, ext, source='ios')

    return jsonify({'status': 'queued', 'job_id': new_job_id}), 200


@api_bp.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    """查询任务状态"""
    queue_mgr = get_queue_manager()
    job = queue_mgr.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    response = {
        'status': job['status'],
        'job_id': job['id']
    }
    if job['status'] == 'failed' and job['error_message']:
        response['error'] = job['error_message']

    return jsonify(response), 200


@api_bp.route('/printers', methods=['GET'])
def list_printers():
    """获取可用打印机列表"""
    queue_mgr = get_queue_manager()
    printers = queue_mgr.get_printers()
    return jsonify({'printers': printers}), 200


@api_bp.route('/printers/status', methods=['GET'])
def printer_status():
    """获取全部打印机实时状态"""
    from flask import current_app
    pm = current_app.config.get('printer_monitor')
    if not pm:
        return jsonify({'printers': {}})
    return jsonify({'printers': pm.get_all_statuses()})


@api_bp.route('/cancel/<job_id>', methods=['POST'])
def cancel_job_api(job_id):
    """API 取消任务（带鉴权）"""
    if not check_auth():
        return jsonify({'error': 'Unauthorized'}), 401
    queue_mgr = get_queue_manager()
    success, error = queue_mgr.cancel_job(job_id)
    if not success:
        return jsonify({'error': error}), 400
    return jsonify({'success': True})


@api_bp.route('/events')
def sse_events():
    """Server-Sent Events endpoint — multiplexes all real-time event types."""
    from flask import Response, stream_with_context, current_app
    from app.services.sse_broadcaster import get_broadcaster
    import json

    broadcaster = get_broadcaster()
    sub_id, q = broadcaster.subscribe()

    def generate():
        try:
            while True:
                event_type, data = q.get()
                yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except GeneratorExit:
            broadcaster.unsubscribe(sub_id)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )
