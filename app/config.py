"""配置管理 — pydantic-settings + config.json 持久化 + 线程安全

优先级：环境变量 > config.json > 默认值
"""
import json
import os
import threading
from typing import Any

from loguru import logger
from pydantic import Field, PrivateAttr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """服务器配置，继承 BaseSettings 自动加载 .env 和环境变量"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    # ── 字段定义（默认值即缺省值） ──
    api_key: str = Field('print-server-key-2026', validation_alias='PRINT_SERVER_API_KEY')
    default_printer: str = ''
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
        '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.heif',
    ])
    job_timeout: int = Field(default=300, ge=30, le=3600)
    auto_retry_count: int = Field(default=0, ge=0, le=10)

    # ── 内部状态（PrivateAttr 不会被 .model_dump() 导出） ──
    _config_path: str = PrivateAttr()
    _lock: threading.Lock = PrivateAttr()
    _errors: list[str] = PrivateAttr(default_factory=list)

    # ── 校验器 ──

    @field_validator('ppt_output_type')
    @classmethod
    def _check_ppt_output(cls, v: str) -> str:
        allowed = ('slides', 'handout2', 'handout3', 'handout6')
        if v not in allowed:
            raise ValueError(f'ppt_output_type 必须为 {allowed} 之一')
        return v

    @field_validator('paper_size')
    @classmethod
    def _check_paper(cls, v: str) -> str:
        allowed = ('A3', 'A4', 'Letter')
        if v not in allowed:
            raise ValueError(f'paper_size 必须为 {allowed} 之一')
        return v

    @field_validator('notify_channel')
    @classmethod
    def _check_notify(cls, v: str) -> str:
        allowed = ('disabled', 'dingtalk', 'bark')
        if v not in allowed:
            raise ValueError(f'notify_channel 必须为 {allowed} 之一')
        return v

    @field_validator('dingtalk_level')
    @classmethod
    def _check_dingtalk_level(cls, v: str) -> str:
        allowed = ('error', 'warning', 'info')
        if v not in allowed:
            raise ValueError(f'dingtalk_level 必须为 {allowed} 之一')
        return v

    @field_validator('log_level')
    @classmethod
    def _check_log_level(cls, v: str) -> str:
        allowed = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        if v.upper() not in allowed:
            raise ValueError(f'log_level 必须为 {allowed} 之一')
        return v

    @field_validator('allowed_extensions')
    @classmethod
    def _check_extensions(cls, v: list[str]) -> list[str]:
        if not v or not all(e.startswith('.') for e in v):
            raise ValueError('allowed_extensions 每个元素必须以 . 开头')
        return v

    # ── 构造与持久化 ──

    def __init__(self, config_path: str | None = None, **kwargs: Any) -> None:
        _skip_file = kwargs.pop('_skip_file', False)
        super().__init__(**kwargs)
        from app._paths import persistent_dir

        object.__setattr__(self, '_config_path',
                           config_path or os.path.join(persistent_dir(), 'config.json'))
        object.__setattr__(self, '_lock', threading.Lock())
        object.__setattr__(self, '_errors', [])
        if not _skip_file:
            self._load_file()

    def _load_file(self) -> None:
        """从 config.json 加载，不覆盖已通过环境变量设置的字段"""
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
        except FileNotFoundError:
            return
        except json.JSONDecodeError as e:
            self._errors.append(str(e))
            logger.warning(f'配置文件解析失败: {e}')
            return

        # 检测环境变量覆盖：新建实例取 exclude_defaults
        env_only = self.__class__(_skip_file=True)
        env_keys = set(env_only.model_dump(exclude_defaults=True))

        for key, val in file_data.items():
            if key not in env_keys and hasattr(self, key) and val is not None:
                setattr(self, key, val)

    # ── 公共接口 ──

    def get(self, key: str, default: Any = None) -> Any:
        """读取配置值。字段有默认值时无需传 default。"""
        return getattr(self, key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            object.__setattr__(self, key, value)

    def set_many(self, kwargs: dict[str, Any]) -> None:
        with self._lock:
            for key, val in kwargs.items():
                object.__setattr__(self, key, val)

    def save(self) -> None:
        data = self.model_dump_json(indent=4, ensure_ascii=False)
        with open(self._config_path, 'w', encoding='utf-8') as f:
            f.write(data)

    def reload(self) -> None:
        self._load_file()

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def __repr__(self) -> str:
        return f'Config(path={self._config_path})'
