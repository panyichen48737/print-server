"""测试 LogBroadcaster"""

from unittest.mock import MagicMock

from app.services.log_broadcaster import LogBroadcaster


class TestLogBroadcaster:
    def test_write_empty_skips(self):
        broadcaster = MagicMock()
        lb = LogBroadcaster(broadcaster)
        lb.write('')
        lb.write('   ')
        broadcaster.publish.assert_not_called()

    def test_write_publishes_to_broadcaster(self):
        broadcaster = MagicMock()
        lb = LogBroadcaster(broadcaster)
        lb.write('hello world')
        broadcaster.publish.assert_called_once_with(
            'log',
            {
                'message': 'hello world',
                'level': 'INFO',
                'source': 'Server',
            },
        )

    def test_write_parses_source_and_level(self):
        broadcaster = MagicMock()
        lb = LogBroadcaster(broadcaster)
        lb.write('[GUI] [WARNING] some qt warning')
        broadcaster.publish.assert_called_once_with(
            'log',
            {
                'message': 'some qt warning',
                'level': 'WARNING',
                'source': 'GUI',
            },
        )

    def test_no_broadcaster_does_not_crash(self):
        lb = LogBroadcaster(None)
        lb.write('test')  # 不应抛出
