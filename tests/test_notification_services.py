"""测试 BarkNotifier 和 DingTalk 通知服务"""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.bark import BarkNotifier
from app.services.dingtalk import DingTalk


def make_config(**kwargs) -> MagicMock:
    """创建 duck-typed config，支持 .get(key, default)"""
    cfg = MagicMock()

    def fake_get(key, default=None):
        return kwargs.get(key, default)

    cfg.get.side_effect = fake_get
    return cfg


# ─── BarkNotifier ────────────────────────────────────────────────────────────


class TestBarkNotifierSendNotification:
    """BarkNotifier.send_notification 基础路径"""

    def test_disabled_channel_is_noop(self):
        """notify_channel != 'bark' 时不发送"""
        config = make_config(notify_channel='disabled')
        notifier = BarkNotifier(config)

        with patch('app.services.bark._client') as mock_client:
            notifier.send_notification('title', 'message')

        mock_client.post.assert_not_called()

    def test_empty_key_is_noop(self):
        """bark_key 为空时不发送"""
        config = make_config(notify_channel='bark', bark_key='')
        notifier = BarkNotifier(config)

        with patch('app.services.bark._client') as mock_client:
            notifier.send_notification('title', 'message')

        mock_client.post.assert_not_called()

    def test_success_200(self):
        """200 响应时记录 info 日志"""
        config = make_config(notify_channel='bark', bark_key='mykey')
        notifier = BarkNotifier(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch('app.services.bark._client') as mock_client:
            mock_client.post.return_value = mock_resp
            notifier.send_notification('Title', 'Body')

        mock_client.post.assert_called_once_with(
            'https://api.day.app/mykey',
            json={'title': 'Title', 'body': 'Body', 'group': 'PrintServer'},
            timeout=10,
        )

    def test_non_200_status(self):
        """非 200 状态码记录 warning，不抛异常"""
        config = make_config(notify_channel='bark', bark_key='mykey')
        notifier = BarkNotifier(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 400

        with patch('app.services.bark._client') as mock_client:
            mock_client.post.return_value = mock_resp
            notifier.send_notification('Title', 'Body')

        mock_client.post.assert_called_once()

    def test_http_exception_caught(self):
        """HTTP 异常被捕获，不冒泡"""
        config = make_config(notify_channel='bark', bark_key='mykey')
        notifier = BarkNotifier(config)

        with patch('app.services.bark._client') as mock_client:
            mock_client.post.side_effect = httpx.ConnectError('connection refused')
            notifier.send_notification('Title', 'Body')

        mock_client.post.assert_called_once()

    def test_timeout_exception_caught(self):
        """超时异常被捕获，不冒泡"""
        config = make_config(notify_channel='bark', bark_key='mykey')
        notifier = BarkNotifier(config)

        with patch('app.services.bark._client') as mock_client:
            mock_client.post.side_effect = httpx.TimeoutException('timed out')
            notifier.send_notification('Title', 'Body')

        mock_client.post.assert_called_once()

    def test_custom_server(self):
        """自定义 bark_server"""
        config = make_config(
            notify_channel='bark',
            bark_key='mykey',
            bark_server='https://custom.bark.example',
        )
        notifier = BarkNotifier(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch('app.services.bark._client') as mock_client:
            mock_client.post.return_value = mock_resp
            notifier.send_notification('Title', 'Body')

        url = mock_client.post.call_args[0][0]
        assert url.startswith('https://custom.bark.example')


class TestBarkNotifierDelegates:
    """BarkNotifier.notify_job_* 委托验证"""

    def test_notify_job_completed(self):
        """notify_job_completed 调用 send_notification 包含文件名和时间"""
        config = make_config(notify_channel='bark', bark_key='mykey')
        notifier = BarkNotifier(config)

        with patch.object(notifier, 'send_notification') as mock_send:
            notifier.notify_job_completed('report.pdf', '12:00')

        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert '打印任务完成' in args[0]
        assert 'report.pdf' in args[1]
        assert '12:00' in args[1]

    def test_notify_job_failed(self):
        """notify_job_failed 调用 send_notification 含格式化的错误信息"""
        config = make_config(notify_channel='bark', bark_key='mykey')
        notifier = BarkNotifier(config)

        with patch.object(notifier, 'send_notification') as mock_send:
            notifier.notify_job_failed('bad.docx', 'Chromium not found', '12:05')

        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        assert '打印任务失败' in args[0]
        assert 'bad.docx' in args[1]
        assert 'Chrome' in args[1]
        assert '12:05' in args[1]


# ─── DingTalk ────────────────────────────────────────────────────────────────


class TestDingTalkSendNotification:
    """DingTalk.send_notification 基础路径"""

    def test_empty_webhook_is_noop(self):
        """dingtalk_webhook 为空时不发送"""
        config = make_config(dingtalk_webhook='')
        notifier = DingTalk(config)

        with patch('app.services.dingtalk._client') as mock_client:
            notifier.send_notification('title', 'message')

        mock_client.post.assert_not_called()

    def test_level_filtered_when_dingtalk_level_is_error(self):
        """dingtalk_level=error 时，level='info' 不发送"""
        config = make_config(
            dingtalk_webhook='https://oapi.dingtalk.com/robot/send',
            dingtalk_level='error',
        )
        notifier = DingTalk(config)

        with patch('app.services.dingtalk._client') as mock_client:
            notifier.send_notification('title', 'message', level='info')

        mock_client.post.assert_not_called()

    def test_level_error_passes_filter(self):
        """dingtalk_level=error 时，level='error' 正常发送"""
        config = make_config(
            dingtalk_webhook='https://oapi.dingtalk.com/robot/send',
            dingtalk_level='error',
        )
        notifier = DingTalk(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch('app.services.dingtalk._client') as mock_client:
            mock_client.post.return_value = mock_resp
            notifier.send_notification('Title', 'Message', level='error')

        mock_client.post.assert_called_once()

    def test_success_200(self):
        """200 响应时记录 info 日志"""
        config = make_config(
            dingtalk_webhook='https://oapi.dingtalk.com/robot/send',
        )
        notifier = DingTalk(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch('app.services.dingtalk._client') as mock_client:
            mock_client.post.return_value = mock_resp
            notifier.send_notification('Title', 'Message body')

        mock_client.post.assert_called_once_with(
            'https://oapi.dingtalk.com/robot/send',
            json={
                'msgtype': 'text',
                'text': {'content': 'Title\n\nMessage body'},
            },
            timeout=10,
        )

    def test_non_200_status(self):
        """非 200 状态码记录 warning，不抛异常"""
        config = make_config(
            dingtalk_webhook='https://oapi.dingtalk.com/robot/send',
        )
        notifier = DingTalk(config)

        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch('app.services.dingtalk._client') as mock_client:
            mock_client.post.return_value = mock_resp
            notifier.send_notification('Title', 'Message')

        mock_client.post.assert_called_once()

    def test_http_exception_caught(self):
        """HTTP 异常被捕获，不冒泡"""
        config = make_config(
            dingtalk_webhook='https://oapi.dingtalk.com/robot/send',
        )
        notifier = DingTalk(config)

        with patch('app.services.dingtalk._client') as mock_client:
            mock_client.post.side_effect = httpx.ConnectError('connection refused')
            notifier.send_notification('Title', 'Message')

        mock_client.post.assert_called_once()

    def test_timeout_exception_caught(self):
        """超时异常被捕获，不冒泡"""
        config = make_config(
            dingtalk_webhook='https://oapi.dingtalk.com/robot/send',
        )
        notifier = DingTalk(config)

        with patch('app.services.dingtalk._client') as mock_client:
            mock_client.post.side_effect = httpx.TimeoutException('timed out')
            notifier.send_notification('Title', 'Message')

        mock_client.post.assert_called_once()


class TestDingTalkDelegates:
    """DingTalk.notify_job_* 委托验证"""

    def test_notify_job_completed_uses_info_level(self):
        """notify_job_completed 以 level='info' 调用 send_notification"""
        config = make_config(
            dingtalk_webhook='https://oapi.dingtalk.com/robot/send',
        )
        notifier = DingTalk(config)

        with patch.object(notifier, 'send_notification') as mock_send:
            notifier.notify_job_completed('done.pdf', '13:00')

        mock_send.assert_called_once_with(
            '打印任务完成',
            '文件: done.pdf\n时间: 13:00',
            level='info',
        )

    def test_notify_job_failed_uses_error_level(self):
        """notify_job_failed 以 level='error' 调用 send_notification"""
        config = make_config(
            dingtalk_webhook='https://oapi.dingtalk.com/robot/send',
        )
        notifier = DingTalk(config)

        with patch.object(notifier, 'send_notification') as mock_send:
            notifier.notify_job_failed('fail.docx', 'Chromium not found', '13:05')

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert '打印任务失败' in args[0]
        assert 'fail.docx' in args[1]
        assert kwargs['level'] == 'error'
