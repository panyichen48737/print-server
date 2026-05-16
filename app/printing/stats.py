"""任务统计查询 — 概览/每日统计/清理过期"""

from datetime import datetime, timedelta


def get_stats(execute_fn) -> dict:
    """返回任务统计概览"""
    today = datetime.now().strftime('%Y-%m-%d')
    row = execute_fn(
        """SELECT
            COUNT(CASE WHEN status='queued' THEN 1 END) AS queued,
            COUNT(CASE WHEN status='printing' THEN 1 END) AS printing,
            COUNT(CASE WHEN status='completed' THEN 1 END) AS completed_total,
            COUNT(CASE WHEN status='failed' THEN 1 END) AS failed_total,
            COUNT(*) AS total,
            SUM(CASE WHEN status='completed' AND created_at >= ? THEN 1 ELSE 0 END) AS today_completed,
            SUM(CASE WHEN status='failed' AND created_at >= ? THEN 1 ELSE 0 END) AS today_failed
        FROM jobs""",
        (today, today),
        fetchone=True,
    )
    success_total = row['completed_total']
    failed_total = row['failed_total']
    success_rate = (
        (success_total / (success_total + failed_total) * 100)
        if (success_total + failed_total) > 0
        else 100
    )
    return {
        'queued': row['queued'],
        'printing': row['printing'],
        'today_completed': row['today_completed'],
        'today_failed': row['today_failed'],
        'total': row['total'],
        'success_rate': success_rate,
    }


def get_daily_counts(execute_fn, days: int = 7) -> dict[str, int]:
    """返回过去 N 天的每日任务量"""
    cursor = execute_fn(
        'SELECT DATE(created_at) as day, COUNT(*) as cnt FROM jobs '
        "WHERE created_at >= datetime('now', ? || ' days') "
        'GROUP BY day ORDER BY day',
        (-days,),
        fetchall=True,
    )
    return {row['day']: row['cnt'] for row in cursor} if cursor else {}


def cleanup_old_jobs(execute_fn, retention_days: int = 30) -> int:
    """删除超过保留天数的旧任务"""
    cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
    cur = execute_fn('DELETE FROM jobs WHERE created_at < ?', (cutoff,), commit=True)
    deleted = cur.rowcount if hasattr(cur, 'rowcount') else 0
    if deleted > 0:
        from loguru import logger

        logger.info(f'已清理 {deleted} 条过期任务记录')
    return deleted
