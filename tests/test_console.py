"""Tests for console CLI (Typer)."""

from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


def test_cli_help():
    """根命令 --help 显示帮助文本"""
    from console import app

    result = runner.invoke(app, ['--help'])
    assert result.exit_code == 0
    assert 'iOS' in result.output


def test_cli_status():
    """status 子命令可独立运行（不需要服务器）"""
    from console import app

    result = runner.invoke(app, ['status'])
    assert result.exit_code == 0
    assert '端口' in result.output


def test_cli_autostart_install():
    """autostart-install 命令存在且可调用"""
    from console import app

    with patch('console.install_autostart', return_value=(True, '已注册')):
        result = runner.invoke(app, ['autostart-install'])
    assert result.exit_code == 0
    assert '已注册' in result.output


def test_cli_autostart_uninstall():
    """autostart-uninstall 命令存在且可调用"""
    from console import app

    with patch('console.uninstall_autostart', return_value=(True, '已卸载')):
        result = runner.invoke(app, ['autostart-uninstall'])
    assert result.exit_code == 0
    assert '已卸载' in result.output


def test_cli_autostart_install_failure():
    """安装失败时退出码为 1"""
    from console import app

    with patch('console.install_autostart', return_value=(False, '失败')):
        result = runner.invoke(app, ['autostart-install'])
    assert result.exit_code == 1


def test_cli_stop_no_server():
    """无 PID 文件时 stop 提示未运行"""
    from console import app

    with patch('console._pid_file') as mock_pid:
        mock_pid.return_value.exists.return_value = False
        result = runner.invoke(app, ['stop'])
    assert result.exit_code == 0
    assert '未运行' in result.output


def test_cli_unknown_command():
    """未知子命令退出码非 0"""
    from console import app

    result = runner.invoke(app, ['nonexistent-command'])
    assert result.exit_code != 0


def test_cli_subcommands_registered():
    """所有 7 个子命令均已注册"""
    from console import app

    result = runner.invoke(app, ['--help'])
    assert result.exit_code == 0
    expected = [
        'headless',
        'gui',
        'stop',
        'status',
        'restart',
        'autostart-install',
        'autostart-uninstall',
    ]
    for cmd in expected:
        assert cmd in result.output, f'missing command: {cmd}'
