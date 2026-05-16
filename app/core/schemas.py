"""API 请求/响应 Pydantic 模型 — 自动生成 OpenAPI 文档 + 运行时校验"""

from pydantic import BaseModel, Field

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


class PrintOptions(BaseModel):
    printer: str | None = None
    copies: int | None = Field(default=None, ge=1, le=99)
    duplex: bool | None = None
    color: bool | None = None
    paper_size: str | None = None


class SettingsUpdate(BaseModel):
    api_key: str | None = None
    default_printer: str | None = None
    default_copies: int | None = Field(default=None, ge=1, le=99)
    default_duplex: bool | None = None
    default_color: bool | None = None
    excel_print_all_sheets: bool | None = None
    ppt_output_type: str | None = None
    paper_size: str | None = None
    quark_api_key_id: str | None = None
    quark_api_key: str | None = None
    notify_channel: str | None = None
    dingtalk_webhook: str | None = None
    dingtalk_level: str | None = None
    bark_key: str | None = None
    bark_server: str | None = None
    port: int | None = Field(default=None, ge=1024, le=65535)
    log_level: str | None = None
    worker_count: int | None = Field(default=None, ge=1, le=16)
    max_file_size_mb: int | None = Field(default=None, ge=1, le=500)
    job_retention_days: int | None = Field(default=None, ge=1, le=365)
    ssl_enabled: bool | None = None
    auto_retry_count: int | None = Field(default=None, ge=0, le=10)


class PrintConfigResponse(BaseModel):
    default_printer: str
    printers: list[str]
    default_copies: int
    default_duplex: bool
    default_color: bool
    paper_size: str


class QueuePositionResponse(BaseModel):
    job_id: str
    position: int
    queue_size: int


class JobFilter(BaseModel):
    status: str | None = None
    search: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
