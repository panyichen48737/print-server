"""异常层次体系 — 统一打印服务器异常"""


class PrintServerError(Exception):
    """所有打印服务器异常的基类"""


class ConfigError(PrintServerError, ValueError):
    """配置相关错误 — 同时继承 ValueError 以兼容 pydantic field_validator"""


class AuthError(PrintServerError):
    """认证/授权错误"""


class PrintError(PrintServerError, RuntimeError):
    """打印执行错误 — 同时继承 RuntimeError 以兼容既有调用点"""


class FileTypeError(PrintServerError, ValueError):
    """不支持的文件类型 — 同时继承 ValueError 以兼容既有调用点"""


class JobCanceled(PrintServerError):
    """任务已被取消"""