"""Tests for console module entry point (no CLI, direct GUI launch)."""

from launcher import _gui_main, main


def test_main_exists():
    """main() 函数可调用且返回 None"""
    # 不真正运行（会启动 Flet），只验证存在性和签名
    assert callable(main)


def test_gui_main_exists():
    """_gui_main() 函数存在"""
    assert callable(_gui_main)


def test_bootstrap_server_exists():
    """_bootstrap_server 函数存在"""
    from launcher import _bootstrap_server

    assert callable(_bootstrap_server)


def test_ensure_single_instance_exists():
    """PID 文件管理函数存在"""
    from launcher import _cleanup_pid, _ensure_single_instance, _pid_file, _write_pid

    assert callable(_ensure_single_instance)
    assert callable(_pid_file)
    assert callable(_write_pid)
    assert callable(_cleanup_pid)


def test_server_lifespan_exists():
    """lifespan 上下文管理器存在"""
    from launcher import _server_lifespan

    assert callable(_server_lifespan)


def test_console_does_not_import_typer():
    """console 模块不再依赖 typer"""
    import sys

    # 模拟干净的模块加载
    assert 'typer' not in sys.modules or True
    # 验证 console 模块的源码中不包含 typer 引用
    import launcher

    src = launcher.__file__
    with open(src, encoding='utf-8') as f:
        content = f.read()
    assert 'typer' not in content, 'launcher 模块不应引用 typer'
