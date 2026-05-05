"""配置管理测试 — Config 读写、校验、持久化、线程安全、环境变量覆盖"""

import json
import threading

import pytest


class TestConfigDefaults:
    """Config 默认值"""

    def test_default_api_key(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        assert cfg.api_key == 'print-server-key-2026'

    def test_default_port(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        assert cfg.port == 5000

    def test_default_log_level(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        assert cfg.log_level == 'INFO'

    def test_default_allowed_extensions(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        assert '.pdf' in cfg.allowed_extensions
        assert '.docx' in cfg.allowed_extensions


class TestConfigValidation:
    """字段校验器"""

    def test_invalid_ppt_output(self, tmp_path):
        from app.config import Config

        with pytest.raises(ValueError):
            Config(
                ppt_output_type='invalid',
                config_path=str(tmp_path / 'config.json'),
                _skip_file=True,
            )

    def test_invalid_paper_size(self, tmp_path):
        from app.config import Config

        with pytest.raises(ValueError):
            Config(paper_size='A5', config_path=str(tmp_path / 'config.json'), _skip_file=True)

    def test_invalid_notify_channel(self, tmp_path):
        from app.config import Config

        with pytest.raises(ValueError):
            Config(notify_channel='sms', config_path=str(tmp_path / 'config.json'), _skip_file=True)

    def test_invalid_dingtalk_level(self, tmp_path):
        from app.config import Config

        with pytest.raises(ValueError):
            Config(
                dingtalk_level='critical',
                config_path=str(tmp_path / 'config.json'),
                _skip_file=True,
            )

    def test_invalid_log_level(self, tmp_path):
        import pydantic

        from app.config import Config

        with pytest.raises(pydantic.ValidationError):
            Config(
                **{'PRINT_SERVER_LOG_LEVEL': 'TRACE'},
                config_path=str(tmp_path / 'config.json'),
                _skip_file=True,
            )

    def test_invalid_extensions_not_dot(self, tmp_path):
        from app.config import Config

        with pytest.raises(ValueError):
            Config(
                allowed_extensions=['pdf'],
                config_path=str(tmp_path / 'config.json'),
                _skip_file=True,
            )

    def test_port_clamped(self, tmp_path):
        """pydantic Field(ge=1024, le=65535) 约束 — 通过别名设置"""
        import pydantic

        from app.config import Config

        with pytest.raises(pydantic.ValidationError):
            Config(
                **{'PRINT_SERVER_PORT': 80},
                config_path=str(tmp_path / 'config.json'),
                _skip_file=True,
            )
        with pytest.raises(pydantic.ValidationError):
            Config(
                **{'PRINT_SERVER_PORT': 99999},
                config_path=str(tmp_path / 'config.json'),
                _skip_file=True,
            )


class TestConfigPersistence:
    """保存和加载"""

    def test_save_and_reload(self, tmp_path):
        cfg_path = tmp_path / 'config.json'
        from app.config import Config

        cfg = Config(config_path=str(cfg_path), _skip_file=True)
        cfg.port = 8080
        cfg.save()

        cfg2 = Config(config_path=str(cfg_path))
        assert cfg2.port == 8080

    def test_save_creates_file(self, tmp_path):
        cfg_path = tmp_path / 'config.json'
        from app.config import Config

        cfg = Config(config_path=str(cfg_path), _skip_file=True)
        cfg.save()
        assert cfg_path.exists()

    def test_reload_applies_file_changes(self, tmp_path):
        cfg_path = tmp_path / 'config.json'
        from app.config import Config

        cfg = Config(config_path=str(cfg_path), _skip_file=True)
        cfg.port = 3000
        cfg.save()

        cfg2 = Config(config_path=str(cfg_path), _skip_file=True)
        cfg2.reload()
        assert cfg2.port == 3000

    def test_corrupt_json_on_load(self, tmp_path):
        cfg_path = tmp_path / 'config.json'
        cfg_path.write_text('{invalid json}', encoding='utf-8')
        from app.config import Config

        cfg = Config(config_path=str(cfg_path))
        assert cfg.errors  # 有解析错误记录


class TestConfigFileLoading:
    """文件加载行为"""

    def test_load_from_file(self, tmp_path):
        cfg_path = tmp_path / 'config.json'
        data = {'port': 9000, 'default_copies': 3}
        cfg_path.write_text(json.dumps(data), encoding='utf-8')

        from app.config import Config

        cfg = Config(config_path=str(cfg_path))
        assert cfg.port == 9000
        assert cfg.default_copies == 3

    def test_file_not_found_uses_defaults(self, tmp_path):
        cfg_path = tmp_path / 'nonexistent.json'
        from app.config import Config

        cfg = Config(config_path=str(cfg_path))
        assert cfg.port == 5000

    def test_skip_file_flag(self, tmp_path):
        cfg_path = tmp_path / 'config.json'
        # 先写一个文件
        cfg_path.write_text(json.dumps({'port': 7000}), encoding='utf-8')
        from app.config import Config

        cfg = Config(config_path=str(cfg_path), _skip_file=True)
        # 文件被跳过，使用默认值
        assert cfg.port == 5000


class TestConfigGetSet:
    """get/set/set_many 接口"""

    def test_get_existing(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        assert cfg.get('port') == 5000

    def test_get_nonexistent_with_default(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        assert cfg.get('nonexistent', 'fallback') == 'fallback'

    def test_get_nonexistent_no_default(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        assert cfg.get('nonexistent') is None

    def test_set_single_value(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        cfg.set('port', 1234)
        assert cfg.port == 1234

    def test_set_many(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        cfg.set_many({'port': 1111, 'default_copies': 5})
        assert cfg.port == 1111
        assert cfg.default_copies == 5

    def test_set_many_updates_saved_file(self, tmp_path):
        cfg_path = tmp_path / 'config.json'
        from app.config import Config

        cfg = Config(config_path=str(cfg_path), _skip_file=True)
        cfg.set_many({'port': 2222, 'log_level': 'DEBUG'})
        cfg.save()

        cfg2 = Config(config_path=str(cfg_path))
        assert cfg2.port == 2222
        assert cfg2.log_level == 'DEBUG'


class TestConfigThreadSafety:
    """并发写入不会丢失值"""

    def test_concurrent_set(self, tmp_path):
        from app.config import Config

        cfg = Config(config_path=str(tmp_path / 'config.json'), _skip_file=True)
        n = 50
        results = set()

        def worker(key):
            for i in range(10):
                cfg.set(key, i)
                results.add((key, i))

        threads = [threading.Thread(target=worker, args=(f'key_{j}',)) for j in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 只是验证不会崩溃，最后一次写入的值应该存在
        assert cfg.get('key_0') is not None
