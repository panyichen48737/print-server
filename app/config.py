import json
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
    """配置管理，支持热加载 + Pydantic 校验"""

    def __init__(self, config_path=None):
        if config_path is None:
            from app._paths import app_root
            config_path = os.path.join(app_root(), 'config.json')
        self.config_path = config_path
        self._lock = threading.Lock()
        self._data = {}
        self._errors = []  # 上次校验的警告/错误
        self.load()

    def load(self):
        with self._lock:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
        self._validate()

    def _validate(self):
        """Pydantic 校验，校验失败记录但不阻止启动"""
        self._errors = []
        try:
            ConfigSchema(**self._data)
        except Exception as e:
            self._errors.append(str(e))
            import logging
            logger = logging.getLogger('print_server')
            for err in self._errors:
                logger.warning(f'配置校验警告: {err}')

    def save(self):
        with self._lock:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)

    def reload(self):
        """热加载配置"""
        self.load()

    def get(self, key, default=None):
        """安全读取，缺失键返回 default 而非 KeyError"""
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def set_many(self, kwargs):
        with self._lock:
            self._data.update(kwargs)

    @property
    def allowed_extensions(self):
        return self.get('allowed_extensions', [])

    @property
    def max_file_size_mb(self):
        return self.get('max_file_size_mb', 50)

    @property
    def api_key(self):
        return self.get('api_key', '')

    @property
    def quark_api_key_id(self):
        return self.get('quark_api_key_id', '')

    @property
    def quark_api_key(self):
        return self.get('quark_api_key', '')

    @property
    def log_level(self):
        return self.get('log_level', 'INFO')

    @property
    def worker_count(self):
        return self.get('worker_count', 2)


def setup_logging(log_dir=None, level='INFO'):
    import logging
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
