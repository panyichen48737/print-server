import logging
import hashlib
import uuid
import time
import base64
import io
import os
from typing import Optional
from PIL import Image
import requests

logger = logging.getLogger('print_server')


class QuarkEnhancer:
    """夸克扫描王 API 图片增强"""

    def __init__(self, config) -> None:
        self.config = config

    def enhance(self, filepath: str) -> Optional[bytes]:
        """
        对图片进行 Quark API 增强处理

        返回:
            bytes: 增强后的图片数据
            None: 增强失败或未配置
        """
        try:
            client_id = self.config.quark_api_key_id
            client_secret = self.config.quark_api_key
            if not client_id or not client_secret:
                logger.warning('Quark API 未配置，跳过图片增强')
                return None

            ext = os.path.splitext(filepath)[1].lower()
            max_api_size = 10 * 1024 * 1024

            # 统一转 JPG：PIL 打开后转 RGB，按需压缩
            img = Image.open(filepath)
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')

            quality = 95
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=quality)

            # 超过 10MB 才逐步降质量压缩
            while buf.tell() > max_api_size and quality > 20:
                quality -= 10
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=quality)

            if buf.tell() > max_api_size:
                logger.warning(
                    f'图片压缩至 quality={quality} 仍超过 {max_api_size // 1024 // 1024}MB，跳过 Quark API'
                )
                return None

            img_data = buf.getvalue()
            logger.info(f'Quark API: {ext} → JPG ({len(img_data) // 1024}KB, quality={quality})')

            img_b64 = base64.b64encode(img_data).decode('utf-8')

            # 构建签名参数（官方示例：所有参数放 JSON body）
            business = 'vision'
            sign_method = 'SHA3-256'
            sign_nonce = uuid.uuid4().hex
            timestamp = int(time.time() * 1000)

            signature = self._sign(client_id, client_secret, business, sign_method, sign_nonce, timestamp)

            headers = {
                'Content-Type': 'application/json',
            }

            payload = {
                'serviceOption': 'scan',
                'inputConfigs': '{"function_option":"auto_select","auto_crop":"true","auto_rotate":"true"}',
                'outputConfigs': '{"need_return_image":"True"}',
                'dataType': 'image',
                'dataBase64': img_b64,
                'reqId': uuid.uuid4().hex,
                'clientId': client_id,
                'signMethod': sign_method,
                'signNonce': sign_nonce,
                'timestamp': timestamp,
                'signature': signature,
            }

            resp = requests.post(
                'https://scan-business.quark.cn/vision',
                json=payload,
                headers=headers,
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

    def _sign(self, client_id: str, client_secret: str, business: str,
               sign_method: str, sign_nonce: str, timestamp: int) -> str:
        """计算签名"""
        sign_str = f'{client_id}_{business}_{sign_method}_{sign_nonce}_{timestamp}_{client_secret}'
        return hashlib.sha3_256(sign_str.encode('utf-8')).hexdigest().lower()
