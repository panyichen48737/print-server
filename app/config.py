import json
import os
import sys
import threading
from typing import Any

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigSchema(BaseSettings):
    """配置校验 schema，启动时验证所有字段"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    api_key: str = Field('print-server-key-2026', validation_alias='PRINT_SERVER_API_KEY')
    default_printer: str = Field('', validation_alias='PRINT_SERVER_DEFAULT_PRINTER')
    default_copies: int = Field(default=1, ge=1, le=999)
    default_duplex: bool = False
    default_color: bool = True
    excel_print_all_sheets: bool = True
    ppt_output_type: str = 'slides'
    paper_size: str = 'A4'
    quark_api_key_id: str = Field('', validation_alias='QUARK_API_KEY_ID')
    quark_api_key: str = Field('', validation_alias='QUARK_API_KEY')
    notify_channel: str = 'disabled'
    dingtalk_webhook: str = ''
    dingtalk_level: str = 'error'
    bark_key: str = ''
    bark_server: str = 'https://api.day.app'
    port: int = Field(default=5000, ge=1024, le=65535, validation_alias='PRINT_SERVER_PORT')
    log_level: str = Field('INFO', validation_alias='PRINT_SERVER_LOG_LEVEL')
    worker_count: int = Field(default=2, ge=1, le=16)
    max_file_size_mb: int = Field(default=50, ge=1, le=500)
    job_retention_days: int = Field(default=30, ge=1, le=365)
    print_dpi: int = Field(default=600, ge=72, le=1200)
    auto_rotate: bool = True
    word_timeout: int = Field(default=120, ge=30, le=600)
    allowed_extensions: list[str] = Field(default_factory=lambda: [
        '.doc', '.docx', '.pdf', '.xls', '.xlsx', '.ppt', '.pptx',
        '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.heif'
    ])
    job_timeout: int = Field(default=300, ge=30, le=3600)
    auto_retry_count: int = Field(default=0, ge=0, le=10)

    @field_validator('ppt_output_type')
    @classmethod
    def validate_ppt_output(cls, v: str) -> str:
        allowed = ('slides', 'handout2', 'handout3', 'handout6')
        if v not in allowed:
            raise ValueError(f'ppt_output_type 必须为 {allowed} 之一')
        return v

    @field_validator('paper_size')
    @classmethod
    def validate_paper(cls, v: str) -> str:
        allowed = ('A3', 'A4', 'Letter')
        if v not in allowed:
            raise ValueError(f'paper_size 必须为 {allowed} 之一')
        return v

    @field_validator('notify_channel')
    @classmethod
    def validate_notify_channel(cls, v: str) -> str:
        allowed = ('disabled', 'dingtalk', 'bark')
        if v not in allowed:
            raise ValueError(f'notify_channel 必须为 {allowed} 之一')
        return v

    @field_validator('dingtalk_level')
    @classmethod
    def validate_dingtalk_level(cls, v: str) -> str:
        allowed = ('error', 'warning', 'info')
        if v not in allowed:
            raise ValueError(f'dingtalk_level 必须为 {allowed} 之一')
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        if v.upper() not in allowed:
            raise ValueError(f'log_level 必须为 {allowed} 之一')
        return v

    @field_validator('allowed_extensions')
    @classmethod
    def validate_extensions(cls, v: list[str]) -> list[str]:
        if not v or not all(e.startswith('.') for e in v):
            raise ValueError('allowed_extensions 每个元素必须以 . 开头')
        return v


class Config:
    """配置管理，基于 Pydantic + 线程安全的热加载"""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            from app._paths import app_root
            config_path = os.path.join(app_root(), 'config.json')
        self.config_path = config_path
        self._lock = threading.Lock()
        self._schema = ConfigSchema()
        self._errors: list[str] = []
        self.load()

    @property
    def schema(self):
        return self._schema

    def load(self) -> None:
        with self._lock:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                try:
                    env_schema = ConfigSchema()
                    env_overrides = env_schema.model_dump(exclude_defaults=True)
                    self._schema = ConfigSchema(**{**data, **env_overrides})
                except Exception as e:
                    logger.warning(f'环境变量解析失败，使用配置文件值: {e}')
                    self._schema = ConfigSchema(**data)
                self._errors = []
            except FileNotFoundError:
                self._schema = ConfigSchema()
                self._errors = []
                logger.info(f'配置文件不存在，使用默认配置: {self.config_path}')
            except json.JSONDecodeError as e:
                self._errors.append(str(e))
                logger.warning(f'配置文件解析失败，使用默认配置: {e}')
                self._schema = ConfigSchema()
            except Exception as e:
                self._errors.append(str(e))
                logger.warning(f'配置校验警告: {e}')

    def save(self) -> None:
        with self._lock:
            data = self._schema.model_dump_json(indent=4, ensure_ascii=False)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(data)

    def reload(self) -> None:
        self.load()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return getattr(self._schema, key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._schema = self._schema.model_copy(update={key: value})

    def set_many(self, kwargs: dict[str, Any]) -> None:
        with self._lock:
            self._schema = self._schema.model_copy(update=kwargs)


def setup_logging(log_dir: str | None = None, level: str = 'INFO') -> Any:
    """配置 loguru 日志"""
    import loguru
    from app._paths import app_root

    if log_dir is None:
        log_dir = os.path.join(app_root(), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'print_server.log')

    loguru.logger.remove()

    loguru.logger.add(
        log_file,
        rotation='00:00',
        retention=7,
        encoding='utf-8',
        format='{time:YYYY-MM-DD HH:mm:ss} [{level}] {message}',
        level=level,
    )

    loguru.logger.add(
        sys.stderr,
        format='{time:HH:mm:ss} [{level}] {message}',
        level=level,
    )

    return loguru.logger
