"""测试 JobRepository"""

import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.printing.repository import JobRepository


@pytest.fixture
def db_path():
    """创建临时 SQLite 数据库"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def repo(db_path):
    """创建 JobRepository 实例"""
    return JobRepository(db_path)


class TestJobRepository:
    """测试 JobRepository CRUD 操作"""

    def test_init_db_creates_table(self, db_path):
        """初始化应创建 jobs 表"""
        repo = JobRepository(db_path)
        import sqlite3

        with sqlite3.connect(db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
            ).fetchone()
        assert tables is not None

    def test_add_job_returns_id(self, repo):
        """添加任务应返回非空 job_id"""
        job_id = repo.add_job('test.pdf', '/path/to/test.pdf')
        assert job_id is not None
        assert len(job_id) > 0

    def test_get_job_returns_correct_data(self, repo):
        """查询任务应返回匹配的数据"""
        job_id = repo.add_job(
            'test.pdf',
            '/path/to/test.pdf',
            file_size=1024,
            file_type='.pdf',
            copies=2,
            source='web',
        )
        job = repo.get_job(job_id)
        assert job is not None
        assert job['filename'] == 'test.pdf'
        assert job['filepath'] == '/path/to/test.pdf'
        assert job['file_size'] == 1024
        assert job['file_type'] == '.pdf'
        assert job['status'] == 'queued'
        assert job['copies'] == 2
        assert job['source'] == 'web'

    def test_get_nonexistent_job(self, repo):
        """查询不存在的任务应返回 None"""
        assert repo.get_job('nonexistent') is None

    def test_update_status_to_completed(self, repo):
        """更新状态为 completed 应记录时间"""
        job_id = repo.add_job('test.pdf', '/path/to/test.pdf')
        repo.update_status(job_id, 'completed')
        job = repo.get_job(job_id)
        assert job['status'] == 'completed'
        assert job['completed_at'] is not None

    def test_update_status_to_failed(self, repo):
        """更新状态为 failed 应记录错误信息"""
        job_id = repo.add_job('test.pdf', '/path/to/test.pdf')
        repo.update_status(job_id, 'failed', '打印机离线')
        job = repo.get_job(job_id)
        assert job['status'] == 'failed'
        assert job['error_message'] == '打印机离线'
        assert job['completed_at'] is not None

    def test_update_status_no_timestamp(self, repo):
        """更新非终态不记录 completed_at"""
        job_id = repo.add_job('test.pdf', '/path/to/test.pdf')
        repo.update_status(job_id, 'printing')
        job = repo.get_job(job_id)
        assert job['status'] == 'printing'
        assert job['completed_at'] is None

    def test_get_jobs_pagination(self, repo):
        """分页查询应返回正确的数量和偏移"""
        ids = []
        for i in range(5):
            ids.append(repo.add_job(f'test{i}.pdf', f'/path/{i}.pdf'))

        page1 = repo.get_jobs(limit=2, offset=0)
        assert len(page1) == 2

        page2 = repo.get_jobs(limit=2, offset=2)
        assert len(page2) == 2

        # 确认分页不重叠
        assert page1[0]['id'] != page2[0]['id']

    def test_get_jobs_filter_by_status(self, repo):
        """按状态筛选任务"""
        job1 = repo.add_job('a.pdf', '/p/a.pdf')
        job2 = repo.add_job('b.pdf', '/p/b.pdf')
        repo.update_status(job2, 'completed')

        queued = repo.get_jobs_by_status('queued')
        assert any(j['id'] == job1 for j in queued)
        assert not any(j['id'] == job2 for j in queued)

    def test_count_jobs(self, repo):
        """统计总任务数"""
        repo.add_job('a.pdf', '/p/a.pdf')
        repo.add_job('b.pdf', '/p/b.pdf')
        repo.add_job('c.pdf', '/p/c.pdf')

        assert repo.count_jobs() == 3

    def test_count_jobs_with_status_filter(self, repo):
        """按状态筛选统计"""
        job = repo.add_job('a.pdf', '/p/a.pdf')
        repo.add_job('b.pdf', '/p/b.pdf')
        repo.update_status(job, 'completed')

        assert repo.count_jobs(status='completed') == 1
        assert repo.count_jobs(status='queued') == 1

    def test_get_stats(self, repo):
        """统计信息应正确"""
        job1 = repo.add_job('a.pdf', '/p/a.pdf')
        job2 = repo.add_job('b.pdf', '/p/b.pdf')
        repo.update_status(job1, 'completed')
        repo.update_status(job2, 'failed')

        stats = repo.get_stats()
        assert stats['total'] == 2
        assert stats['success_rate'] == 50.0  # 1 completed, 1 failed

    def test_cleanup_old_jobs(self, repo):
        """清理过期任务"""
        repo.add_job('old.pdf', '/p/old.pdf')
        # 直接操作数据库设置过去的日期
        import sqlite3

        with sqlite3.connect(repo.db_path) as conn:
            conn.execute(
                "UPDATE jobs SET created_at = ? WHERE filename = 'old.pdf'",
                ((datetime.now() - timedelta(days=60)).isoformat(),),
            )

        repo.add_job('new.pdf', '/p/new.pdf')

        deleted = repo.cleanup_old_jobs(retention_days=30)
        assert deleted >= 1
        assert repo.count_jobs() == 1

    def test_increment_retry(self, repo):
        """重试计数应递增"""
        job_id = repo.add_job('a.pdf', '/p/a.pdf')
        repo.increment_retry(job_id)
        repo.increment_retry(job_id)
        job = repo.get_job(job_id)
        assert job['retry_count'] == 2

    def test_migrate_db_adds_new_columns(self, db_path):
        """migrate_db 应为旧表添加缺失列"""
        # 先创建旧表（无新列）
        import sqlite3

        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

        # 运行迁移
        repo = JobRepository(db_path)

        # 验证列已添加
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute('PRAGMA table_info(jobs)')
            columns = {row[1] for row in cursor.fetchall()}
        assert 'duplex' in columns
        assert 'color' in columns
        assert 'source' in columns
