from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
import json

from app.auth import require_auth

api_bp = Blueprint('api', __name__)


def get_job_service():
    return current_app.config['job_service']


def get_config():
    return current_app.config['app_config']


@api_bp.route('/print', methods=['POST'])
@require_auth
def print_file():
    """提交打印任务"""
    config = get_config()
    job_service = get_job_service()
    result = job_service.submit(request, source='ios')
    if not result['success']:
        return jsonify({'success': False, 'error': result['error']}), 400
    return jsonify({'status': 'queued', 'job_id': result['job_id']}), 200


@api_bp.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    """查询任务状态"""
    job_service = get_job_service()
    result = job_service.get_status(job_id)
    if not result:
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    return jsonify({'success': True, **result}), 200


@api_bp.route('/printers', methods=['GET'])
def list_printers():
    """获取可用打印机列表"""
    job_service = get_job_service()
    printers = job_service.list_printers()
    return jsonify({'printers': printers}), 200


@api_bp.route('/printers/status', methods=['GET'])
def printer_status():
    """获取全部打印机实时状态"""
    job_service = get_job_service()
    return jsonify({'printers': job_service.get_printer_statuses()})


@api_bp.route('/cancel/<job_id>', methods=['POST'])
@require_auth
def cancel_job_api(job_id):
    """API 取消任务（带鉴权）"""
    job_service = get_job_service()
    success, error = job_service.cancel(job_id)
    if not success:
        return jsonify({'success': False, 'error': error}), 400
    return jsonify({'success': True})


@api_bp.route('/events')
def sse_events():
    """Server-Sent Events endpoint — multiplexes all real-time event types."""
    broadcaster = current_app.extensions['sse']
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
