"""图片增强处理 — 夸克扫描王 API 封装"""

import base64
import contextlib
import hashlib
import io
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from loguru import logger
from PIL import Image


class QuarkEnhancer:
    """夸克扫描王 API 图片增强"""

    def __init__(self, config: Any, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=60)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        with contextlib.suppress(Exception):
            self._client.close()

    def enhance(self, filepath: str) -> bytes | None:
        client_id = self.config.get('quark_api_key_id', '')
        client_secret = self.config.get('quark_api_key', '')
        if not client_id or not client_secret:
            logger.error('Quark API 未配置，无法处理图片')
            raise ValueError('Quark API 未配置，请在设置中配置 API 密钥')

        try:
            max_api_size = 10 * 1024 * 1024
            valid_exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.webp'}

            ext = Path(filepath).suffix.lower()
            if ext not in valid_exts:
                logger.warning(f'Quark API 不支持的格式: {ext}')
                return None

            # 校验尺寸和比例
            img = Image.open(filepath)
            w, h = img.size
            if w < 15 or h < 15 or w > 8192 or h > 8192:
                logger.warning(f'Quark API 尺寸超限: {w}x{h}（需 15~8192 像素）')
                return None
            if max(w, h) / min(w, h) > 50:
                logger.warning(
                    f'Quark API 长宽比超限: {max(w, h)}/{min(w, h)}={max(w, h) / min(w, h):.1f} > 50'
                )
                return None

            raw_size = Path(filepath).stat().st_size
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')

            # 转 JPEG，≤10MB 用 quality=100（不压缩），>10MB 逐步降 quality
            quality = 100 if raw_size <= max_api_size else 95
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality)
            while buf.tell() > max_api_size and quality > 50:
                quality -= 5
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=quality)

            if buf.tell() > max_api_size:
                logger.warning(
                    f'JPEG quality={quality} 仍超过 {max_api_size // 1024 // 1024}MB，跳过 Quark API'
                )
                return None

            img_data = buf.getvalue()
            logger.info(
                f'Quark API: JPEG quality={quality} ({raw_size // 1024}KB → {len(img_data) // 1024}KB)'
            )

            img_b64 = base64.b64encode(img_data).decode('utf-8')

            sign_nonce = uuid.uuid4().hex
            timestamp = int(time.time() * 1000)
            signature = self._sign(
                client_id, client_secret, 'vision', 'SHA3-256', sign_nonce, timestamp
            )

            payload = {
                'serviceOption': 'scan',
                'inputConfigs': '{"function_option":"auto_select","auto_crop":"true","auto_rotate":"true"}',
                'outputConfigs': '{"need_return_image":"True"}',
                'dataType': 'image',
                'dataBase64': img_b64,
                'reqId': uuid.uuid4().hex,
                'clientId': client_id,
                'signMethod': 'SHA3-256',
                'signNonce': sign_nonce,
                'timestamp': timestamp,
                'signature': signature,
            }

            resp = self._client.post(
                'https://scan-business.quark.cn/vision',
                json=payload,
                timeout=60,
            )

            if resp.status_code != 200:
                logger.warning(f'Quark API HTTP {resp.status_code}: {resp.text[:200]}')
                return None

            result = resp.json()
            code = result.get('code', '')
            if code and code != '00000':
                logger.warning(f'Quark API 返回错误: code={code} msg={result.get("msg", "")}')
                return None

            data = result.get('data', {})
            image_info = data.get('ImageInfo', []) if data else result.get('ImageInfo', [])
            if image_info and image_info[0].get('ImageBase64'):
                enhanced = base64.b64decode(image_info[0]['ImageBase64'])
                logger.info('Quark API 图片增强成功')
                return enhanced

            logger.warning('Quark API 返回无图片数据')
            return None

        except Exception as e:
            logger.warning(f'Quark API 调用失败，使用原图: {e}')
            return None

    def _sign(
        self,
        client_id: str,
        client_secret: str,
        business: str,
        sign_method: str,
        sign_nonce: str,
        timestamp: int,
    ) -> str:
        sign_str = f'{client_id}_{business}_{sign_method}_{sign_nonce}_{timestamp}_{client_secret}'
        return hashlib.sha3_256(sign_str.encode('utf-8')).hexdigest().lower()
