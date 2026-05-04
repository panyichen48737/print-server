"""网页内容抓取 — 获取 URL 文本内容并转为 Markdown"""
import httpx
import html2text

from loguru import logger

_converter = html2text.HTML2Text()
_converter.body_width = 0
_converter.ignore_links = False
_converter.ignore_images = True
_converter.ignore_emphasis = False
_converter.skip_internal_links = True

_client = httpx.Client(timeout=30, follow_redirects=True)

DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


def fetch_text(url: str, max_length: int = 50000) -> str:
    """获取网页文本内容，返回 Markdown 格式"""
    try:
        resp = _client.get(url, headers={'User-Agent': DEFAULT_USER_AGENT})
        resp.raise_for_status()
        content_type = resp.headers.get('content-type', '')
        if 'text/html' not in content_type:
            return resp.text[:max_length] if len(resp.text) > max_length else resp.text
        text = _converter.handle(resp.text)
        text = _clean_text(text)
        if len(text) > max_length:
            text = text[:max_length] + '\n\n...（内容已截断）'
        return text
    except httpx.TimeoutException:
        logger.warning(f'抓取超时: {url}')
        return f'错误: 请求超时 (30s)'
    except httpx.HTTPStatusError as e:
        logger.warning(f'HTTP 错误: {url} - {e.response.status_code}')
        return f'错误: HTTP {e.response.status_code}'
    except Exception as e:
        logger.warning(f'抓取失败: {url} - {e}')
        return f'错误: {e}'


def _clean_text(text: str) -> str:
    lines = [line.strip() for line in text.split('\n')]
    lines = [l for l in lines if l]
    return '\n\n'.join(lines)
