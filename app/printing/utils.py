"""打印模块共享工具函数"""

from loguru import logger


def cancel_all_spooler_jobs(printer_name: str) -> None:
    """取消指定打印机的所有 Spooler 作业"""
    import win32print

    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(handle, 0, 0xFFFFFFFF, 1)
            for job in jobs:
                win32print.SetJob(handle, job['JobId'], 0, win32print.JOB_CONTROL_DELETE)
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        logger.warning(f'取消 Spooler 作业失败: {e}')
