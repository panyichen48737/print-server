from flask import Blueprint, request, jsonify, current_app

from app.auth import require_auth, check_auth
from app.upload_helper import handle_file_upload

api_bp = Blueprint('api', __name__)


def get_queue_manager():
    return current_app.config['queue_manager']


def get_config():
    return current_app.config['app_config']


@api_bp.route('/print', methods=['POST'])
@require_auth
def print_file():
    """提交打印任务"""
    config = get_config()
    queue_mgr = get_queue_manager()
    job_id, error = handle_file_upload(request, config, queue_mgr, source='ios')
    if error:
        return error
    return jsonify({'status': 'queued', 'job_id': job_id}), 200


@api_bp.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    """查询任务状态"""
    queue_mgr = get_queue_manager()
    job = queue_mgr.get_job(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Job not found'}), 404

    response = {
        'success': True,
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
@require_auth
def cancel_job_api(job_id):
    """API 取消任务（带鉴权）"""
    queue_mgr = get_queue_manager()
    success, error = queue_mgr.cancel_job(job_id)
    if not success:
        return jsonify({'success': False, 'error': error}), 400
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
