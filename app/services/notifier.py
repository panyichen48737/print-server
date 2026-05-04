from abc import ABC, abstractmethod
import re


# 已知错误模式 → 中文文案
KNOWN_ERROR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'未找到 Chromium|Chrome.*打印失败|chromium', re.I),
     '未检测到 Chrome/Edge 浏览器，请确认已安装'),
    (re.compile(r'打印超时|timeout', re.I),
     '打印任务超时，请检查打印机是否在线'),
    (re.compile(r'用户取消', re.I),
     '用户已手动取消'),
    (re.compile(r'打印机.*未找|printer.*not found|win32print.*print', re.I),
     '找不到目标打印机，请检查打印机名称和连接状态'),
    (re.compile(r'Word.*失败|win32com.*Word|Word\.Application', re.I),
     'Microsoft Word 调用失败，请检查 Office 安装'),
    (re.compile(r'Excel.*失败|win32com.*Excel|Excel\.Application', re.I),
     'Microsoft Excel 调用失败，请检查 Office 安装'),
    (re.compile(r'PowerPoint.*失败|win32com.*PowerPoint|PPT\.Application', re.I),
     'Microsoft PowerPoint 调用失败，请检查 Office 安装'),
    (re.compile(r'不支持的文件类型|file type', re.I),
     '文件格式不支持'),
    (re.compile(r'文件过大', re.I),
     '文件超过大小限制'),
    (re.compile(r'磁盘|space|disk|存储', re.I),
     '磁盘空间不足，请清理后重试'),
    (re.compile(r'权限|permission|denied|access', re.I),
     '权限不足，请以管理员身份运行'),
    (re.compile(r'Quark|夸克', re.I),
     '图片增强（夸克 API）调用失败，将使用原图打印'),
    (re.compile(r'nssm.*install|服务.*创建|service', re.I),
     'Windows 服务注册失败，请以管理员身份运行'),
]


# 本地系统错误模式（只记日志，不发送通知）
LOCAL_ERROR_PATTERNS: list[re.Pattern] = [
    re.compile(r'磁盘|space|disk|存储', re.I),
    re.compile(r'权限|permission|denied|access', re.I),
    re.compile(r'nssm.*install|服务.*创建|service', re.I),
    re.compile(r'文件过大', re.I),
]


def is_print_related_error(raw_error: str) -> bool:
    """返回 False 表示属于本地系统错误，不应发送通知"""
    if not raw_error:
        return True
    for pattern in LOCAL_ERROR_PATTERNS:
        if pattern.search(raw_error):
            return False
    return True


def format_error_message(raw_error: str) -> str:
    """将原始错误信息转为直观的中文文案"""
    if not raw_error:
        return ''
    for pattern, message in KNOWN_ERROR_PATTERNS:
        if pattern.search(raw_error):
            return message
    # 未知错误：截断过长信息
    if len(raw_error) > 200:
        raw_error = raw_error[:200] + '...'
    return f'未知错误: {raw_error}'


class Notifier(ABC):
    """通知服务抽象接口"""

    @abstractmethod
    def send_notification(self, title: str, message: str, level: str = 'info') -> None:
        ...

    @abstractmethod
    def notify_job_completed(self, filename: str, time_str: str) -> None:
        ...

    @abstractmethod
    def notify_job_failed(self, filename: str, error: str, time_str: str) -> None:
        ...
