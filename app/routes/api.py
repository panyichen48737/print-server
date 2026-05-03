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
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config.allowed_extensions:
        return jsonify({'error': f'File type {ext} not allowed'}), 400

    # Save file
    job_id = str(uuid.uuid4())
    jobs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'jobs')
    os.makedirs(jobs_dir, exist_ok=True)
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
    new_job_id = queue_mgr.add_job(filename, save_path, file_size, ext)

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
