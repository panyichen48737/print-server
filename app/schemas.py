"""API 请求/响应 Pydantic 模型 — 自动生成 OpenAPI 文档 + 运行时校验"""

from pydantic import BaseModel

# ── 响应模型 ──


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: int = 0
    queue_size: int
    db_size_mb: float = 0.0
    port: int = 5000


class PrintResponse(BaseModel):
    success: bool
    job_id: str


class ErrorDetail(BaseModel):
    detail: str


class StatusResponse(BaseModel):
    success: bool
    status: str
    job_id: str
    error: str | None = None


class CancelResponse(BaseModel):
    success: bool


class CancelAllResponse(BaseModel):
    success: bool
    cancelled: int


class PrinterListResponse(BaseModel):
    printers: list


class PrinterStatusResponse(BaseModel):
    printers: dict


class RetryResponse(BaseModel):
    success: bool
    new_job_id: str


class LogsResponse(BaseModel):
    lines: list[str]


class NotificationTestResponse(BaseModel):
    success: bool
    channel: str


# ── 请求模型 ──


class SetDefaultPrinterRequest(BaseModel):
    printer: str


# ── 管理后台 ──


class AdminActionResponse(BaseModel):
    success: bool
