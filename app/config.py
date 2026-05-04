import json
import logging
import os
import threading
from pydantic import BaseModel, Field, field_validator

__all__ = ['Config', 'ConfigSchema', 'setup_logging']


class ConfigSchema(BaseModel):
    """配置校验 schema，启动时验证所有字段"""
    api_key: str = 'print-server-key-2026'
    default_printer: str = ''
    default_copies: int = Field(default=1, ge=1, le=999)
    default_duplex: bool = False
    default_color: bool = True
    excel_print_all_sheets: bool = True
    ppt_output_type: str = 'slides'
    paper_size: str = 'A4'
    quark_api_key_id: str = ''
    quark_api_key: str = ''
    notify_channel: str = 'disabled'
    dingtalk_webhook: str = ''
    dingtalk_level: str = 'error'
    bark_key: str = ''
    bark_server: str = 'https://api.day.app'
    port: int = Field(default=5000, ge=1024, le=65535)
    log_level: str = 'INFO'
    worker_count: int = Field(default=2, ge=1, le=16)
    max_file_size_mb: int = Field(default=50, ge=1, le=500)
    job_retention_days: int = Field(default=30, ge=1, le=365)
    print_dpi: int = Field(default=300, ge=72, le=1200)
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
    def validate_ppt_output(cls, v):
        allowed = ('slides', 'handout2', 'handout3', 'handout6')
        if v not in allowed:
            raise ValueError(f'ppt_output_type 必须为 {allowed} 之一')
        return v

    @field_validator('paper_size')
    @classmethod
    def validate_paper(cls, v):
        allowed = ('A3', 'A4', 'Letter')
        if v not in allowed:
            raise ValueError(f'paper_size 必须为 {allowed} 之一')
        return v

    @field_validator('notify_channel')
    @classmethod
    def validate_notify_channel(cls, v):
        allowed = ('disabled', 'dingtalk', 'bark')
        if v not in allowed:
            raise ValueError(f'notify_channel 必须为 {allowed} 之一')
        return v

    @field_validator('dingtalk_level')
    @classmethod
    def validate_dingtalk_level(cls, v):
        allowed = ('error', 'warning', 'info')
        if v not in allowed:
            raise ValueError(f'dingtalk_level 必须为 {allowed} 之一')
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        allowed = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        if v.upper() not in allowed:
            raise ValueError(f'log_level 必须为 {allowed} 之一')
        return v

    @field_validator('allowed_extensions')
    @classmethod
    def validate_extensions(cls, v):
        if not v or not all(e.startswith('.') for e in v):
            raise ValueError('allowed_extensions 每个元素必须以 . 开头')
        return v


class Config:
    """配置管理，基于 Pydantic + 线程安全的热加载"""

    def __init__(self, config_path=None):
        if config_path is None:
            from app._paths import app_root
            config_path = os.path.join(app_root(), 'config.json')
        self.config_path = config_path
        self._lock = threading.Lock()
        self._schema = ConfigSchema()
        self._errors = []
        self.load()

    def __getattr__(self, name):
        """将未知属性访问代理到 ConfigSchema 字段（线程安全）"""
        with self._lock:
            if '_schema' in self.__dict__:
                schema = self.__dict__['_schema']
                if hasattr(schema, name):
                    return getattr(schema, name)
        raise AttributeError(f"'Config' object has no attribute '{name}'")

    def load(self):
        with self._lock:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._schema = ConfigSchema(**data)
                self._errors = []
            except FileNotFoundError:
                self._schema = ConfigSchema()
                self._errors = []
                logger = logging.getLogger('print_server')
                logger.info(f'配置文件不存在，使用默认配置: {self.config_path}')
            except json.JSONDecodeError as e:
                self._errors.append(str(e))
                logger = logging.getLogger('print_server')
                logger.warning(f'配置文件解析失败，使用默认配置: {e}')
                self._schema = ConfigSchema()
            except Exception as e:
                self._errors.append(str(e))
                logger = logging.getLogger('print_server')
                logger.warning(f'配置校验警告: {e}')

            # 环境变量覆盖敏感字段（优先级高于 config.json）
            env_overrides = {
                'quark_api_key_id': 'PRINT_SERVER_QUARK_API_KEY_ID',
                'quark_api_key': 'PRINT_SERVER_QUARK_API_KEY',
                'api_key': 'PRINT_SERVER_API_KEY',
                'dingtalk_webhook': 'PRINT_SERVER_DINGTALK_WEBHOOK',
                'bark_key': 'PRINT_SERVER_BARK_KEY',
            }
            for field, env_name in env_overrides.items():
                val = os.environ.get(env_name)
                if val:
                    setattr(self._schema, field, val)

    def save(self):
        with self._lock:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                f.write(self._schema.model_dump_json(indent=4, ensure_ascii=False))

    def reload(self):
        self.load()

    def get(self, key, default=None):
        with self._lock:
            return getattr(self._schema, key, default)

    def set(self, key, value):
        with self._lock:
            self._schema = self._schema.model_copy(update={key: value})

    def set_many(self, kwargs):
        with self._lock:
            self._schema = self._schema.model_copy(update=kwargs)


def setup_logging(log_dir=None, level='INFO'):
    from logging.handlers import TimedRotatingFileHandler
    from app._paths import app_root

    if log_dir is None:
        log_dir = os.path.join(app_root(), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'print_server.log')

    logger = logging.getLogger('print_server')
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        logger.handlers.clear()

    fh = TimedRotatingFileHandler(log_file, when='midnight', interval=1, backupCount=7, encoding='utf-8')
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(ch)

    return logger
