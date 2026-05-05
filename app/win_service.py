"""pywin32 ServiceFramework 包装 — 将打印服务器注册为 Windows 服务

用法：
    注册服务: iOSPrintServer.exe --autostart-install (管理员)
    SCM 启动: iOSPrintServer.exe --server-daemon --service

SCM 通过 StartServiceCtrlDispatcher 与服务通信，sc query 正确显示状态。
"""
import sys

import servicemanager
import win32event
import win32service
import win32serviceutil

from loguru import logger


class DaemonService(win32serviceutil.ServiceFramework):
    """Windows 服务 — 将 server_daemon 包装为 SCM 可管理的服务"""

    _svc_name_ = 'iOSPrintServer'
    _svc_display_name_ = 'iOS 云打印服务器'

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)

    def SvcDoRun(self):
        """服务主入口 — SCM 调用此方法启动服务"""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ''),
        )
        logger.info('Windows 服务启动中...')
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)

        from app import server_daemon

        # 标记服务模式，让 server_daemon 跳过互斥体检查
        server_daemon._is_service = True
        # 将自身引用传给 server_daemon，SvcStop 可触发 uvicorn 优雅关闭
        server_daemon._win_service_handle = self

        self.ReportServiceStatus(win32service.SERVICE_RUNNING)

        try:
            # server_daemon.main() 阻塞直到 uvicorn 退出
            server_daemon.main()
        finally:
            # SvcStop 已设置 should_exit，uvicorn 返回后标记服务已停止
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STOPPED,
                (self._svc_name_, ''),
            )

    def SvcStop(self):
        """服务停止 — SCM 从另一线程调用"""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        logger.info('Windows 服务停止中...')

        from app import server_daemon

        if server_daemon._uvicorn_server:
            server_daemon._uvicorn_server.should_exit = True

        win32event.SetEvent(self.stop_event)


def run_as_service():
    """以 Windows 服务方式启动

    由 console/__init__.py 在检测到 --service 时调用。
    清理 sys.argv 后委托 win32serviceutil 处理 SCM 通信。
    """
    sys.argv = [sys.argv[0]]
    win32serviceutil.HandleCommandLine(DaemonService)
