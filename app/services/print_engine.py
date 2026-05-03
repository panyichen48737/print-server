import os
import logging
import io

logger = logging.getLogger('print_server')


class PrintEngine:
    def __init__(self, config, dingtalk=None, excel_lock=None, ppt_lock=None):
        self.config = config
        self.dingtalk = dingtalk
        self.excel_lock = excel_lock or threading.Lock()
        self.ppt_lock = ppt_lock or threading.Lock()

    def print_file(self, filepath, file_type, job_id, word_lock):
        """根据文件类型分发到对应的打印方法"""
        ext = file_type.lower()
        if ext in ('.doc', '.docx'):
            return self._print_word(filepath, word_lock)
        elif ext == '.pdf':
            return self._print_pdf(filepath)
        elif ext in ('.xls', '.xlsx'):
            return self._print_excel(filepath)
        elif ext in ('.ppt', '.pptx'):
            return self._print_ppt(filepath)
        elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.heif'):
            return self._print_image(filepath, job_id)
        else:
            raise ValueError(f'不支持的文件类型: {ext}')

    def _print_word(self, filepath, word_lock):
        """通过 win32com 调用 Word 打印"""
        with word_lock:
            import win32com.client
            import pythoncom
            word = None
            try:
                pythoncom.CoInitialize()
                word = win32com.client.Dispatch('Word.Application')
                word.Visible = False
                word.DisplayAlerts = 0  # wdAlertsNone

                doc = word.Documents.Open(os.path.abspath(filepath))

                printer = self.config.get('default_printer', '')
                if printer:
                    word.ActivePrinter = printer

                copies = self.config.get('default_copies', 1)
                doc.PrintOut(Background=False, Copies=copies)

                doc.Close(SaveChanges=0)  # wdDoNotSaveChanges
                word.Quit(SaveChanges=0)  # wdDoNotSaveChanges
                word = None
                pythoncom.CoUninitialize()
                return True
            except Exception as e:
                logger.error(f'Word 打印失败: {e}')
                raise
            finally:
                try:
                    if word:
                        word.Quit(SaveChanges=0)
                except:
                    pass
                try:
                    pythoncom.CoUninitialize()
                except:
                    pass

    def _print_excel(self, filepath):
        """通过 win32com 调用 Excel 打印"""
        with self.excel_lock:
            import win32com.client
            import pythoncom
            excel = None
            try:
                pythoncom.CoInitialize()
                excel = win32com.client.Dispatch('Excel.Application')
                excel.Visible = False
                excel.DisplayAlerts = False
                workbook = excel.Workbooks.Open(os.path.abspath(filepath))

                printer = self.config.get('default_printer', '')
                if printer:
                    excel.ActivePrinter = printer

                copies = self.config.get('default_copies', 1)
                all_sheets = self.config.get('excel_print_all_sheets', True)

                if all_sheets:
                    for ws in workbook.Worksheets:
                        ws.Select(False)
                workbook.PrintOut(Copies=copies)

                workbook.Close(SaveChanges=False)
                excel.Quit()
                excel = None
                pythoncom.CoUninitialize()
                return True
            except Exception as e:
                logger.error(f'Excel 打印失败: {e}')
                raise
            finally:
                try:
                    if excel:
                        excel.Quit()
                except:
                    pass
                try:
                    pythoncom.CoUninitialize()
                except:
                    pass

    def _print_ppt(self, filepath):
        """通过 win32com 调用 PowerPoint 打印"""
        with self.ppt_lock:
            import win32com.client
            import pythoncom
            ppt = None
            try:
                pythoncom.CoInitialize()
                ppt = win32com.client.Dispatch('PowerPoint.Application')
                ppt.Visible = False
                presentation = ppt.Presentations.Open(os.path.abspath(filepath))

                printer = self.config.get('default_printer', '')
                if printer:
                    ppt.ActivePrinter = printer

                copies = self.config.get('default_copies', 1)
                output_type = self.config.get('ppt_output_type', 'slides')

                output_map = {
                    'slides': 1,       # ppOutputTypeSlides
                    'handout2': 2,     # ppOutputTypeTwoSlideHandout
                    'handout3': 3,     # ppOutputTypeThreeSlideHandout
                    'handout6': 4,     # ppOutputTypeSixSlideHandout
                }
                presentation.PrintOptions.OutputType = output_map.get(output_type, 1)
                presentation.PrintOut(Copies=copies)

                presentation.Close(SaveChanges=0)
                ppt.Quit()
                ppt = None
                pythoncom.CoUninitialize()
                return True
            except Exception as e:
                logger.error(f'PPT 打印失败: {e}')
                raise
            finally:
                try:
                    if ppt:
                        ppt.Quit()
                except:
                    pass
                try:
                    pythoncom.CoUninitialize()
                except:
                    pass

    def _print_pdf(self, filepath):
        """使用 Chromium (Chrome/Edge) headless 模式直接打印 PDF，质量最佳"""
        chrome_path = self._find_chromium()
        if not chrome_path:
            raise RuntimeError('未找到 Chromium 浏览器 (Chrome/Edge)')

        import subprocess
        printer_name = self.config.get('default_printer', '')
        if not printer_name:
            import win32print
            printer_name = win32print.GetDefaultPrinter()

        result = subprocess.run(
            [chrome_path, '--headless', '--disable-gpu',
             f'--print-to-printer="{printer_name}"',
             '--no-margins', '--no-pdf-header-footer',
             os.path.abspath(filepath)],
            capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            error_msg = f'Chrome 打印失败: {result.returncode}\n{result.stderr[:500]}'
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(f'Chromium PDF 打印成功: {filepath}')
        return True

    def _find_chromium(self):
        """查找 Edge 或 Chrome 的安装路径（优先 Edge）"""
        import subprocess
        # 先查 PATH — Edge 优先
        try:
            result = subprocess.run(['where', 'msedge.exe'], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if os.path.exists(path):
                    return path
        except:
            pass
        try:
            result = subprocess.run(['where', 'chrome.exe'], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip().split('\n')[0]
                if os.path.exists(path):
                    return path
        except:
            pass

        # 常见安装路径 — Edge 优先
        candidates = [
            os.path.expandvars(r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%LocalAppData%\Microsoft\Edge\Application\msedge.exe'),
            os.path.expandvars(r'%ProgramFiles%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe'),
            os.path.expandvars(r'%LocalAppData%\Google\Chrome\Application\chrome.exe'),
        ]
        for path in candidates:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                return expanded

        return None

    def _print_image(self, filepath, job_id):
        """处理图片：Quark API 预处理 → PIL 排版 → win32print 打印"""
        try:
            from PIL import Image, ImageOps
            import requests

            # Step 1: Quark API 预处理
            processed = self._quark_enhance(filepath)

            # Step 2: 加载图片
            if processed:
                img = Image.open(io.BytesIO(processed))
            else:
                img = Image.open(filepath)

            # Auto rotate based on EXIF
            if self.config.get('auto_rotate', True):
                try:
                    img = ImageOps.exif_transpose(img)
                except:
                    pass

            # Step 3: 适配 A4 居中
            dpi = self.config.get('print_dpi', 300)
            paper_size = self.config.get('paper_size', 'A4')
            if paper_size == 'A4':
                pw, ph = int(8.27 * dpi), int(11.69 * dpi)
            elif paper_size == 'Letter':
                pw, ph = int(8.5 * dpi), int(11 * dpi)
            elif paper_size == 'A3':
                pw, ph = int(11.69 * dpi), int(16.54 * dpi)
            else:
                pw, ph = int(8.27 * dpi), int(11.69 * dpi)

            # Match orientation: 横图横排, 竖图竖排
            img_w, img_h = img.size
            if (img_w > img_h and pw < ph) or (img_w < img_h and pw > ph):
                pw, ph = ph, pw

            # Scale to fit full page
            scale = min(pw / img_w, ph / img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)

            if self.config.get('default_color', True):
                canvas = Image.new('RGB', (pw, ph), (255, 255, 255))
                img_resized = img.resize((new_w, new_h), Image.LANCZOS)
            else:
                canvas = Image.new('L', (pw, ph), (255))
                img_resized = img.resize((new_w, new_h), Image.LANCZOS).convert('L')

            x = (pw - new_w) // 2
            y = (ph - new_h) // 2
            canvas.paste(img_resized, (x, y))

            # Step 4: Print via win32print
            self._send_to_printer(canvas)

            return True

        except Exception as e:
            logger.error(f'图片打印失败: {e}')
            raise

    def _quark_enhance(self, filepath):
        """调用 Quark 扫描 API 进行图片增强"""
        try:
            import requests
            api_key_id = self.config.quark_api_key_id
            api_key = self.config.quark_api_key
            if not api_key_id or not api_key:
                logger.warning('Quark API 未配置，跳过图片增强')
                return None

            url = 'https://scan.quark.cn/blm/scank-business-docs-703/docs-v2'
            params = {
                'type': 'ability',
                'name_en': 'auto_select',
                'referenceId': '29',
                'tab': 'api'
            }

            with open(filepath, 'rb') as f:
                files = {'file': f}
                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'X-Api-Key-Id': api_key_id
                }
                resp = requests.post(url, params=params, files=files, headers=headers, timeout=60)

            if resp.status_code == 200:
                data = resp.json()
                if 'data' in data and 'image' in data['data']:
                    import base64
                    img_data = base64.b64decode(data['data']['image'])
                    logger.info('Quark API 图片增强成功')
                    return img_data

            content_type = resp.headers.get('Content-Type', '')
            if 'image' in content_type:
                logger.info('Quark API 返回图片数据')
                return resp.content

            logger.warning(f'Quark API 返回非预期格式: {resp.status_code}')
            return None

        except Exception as e:
            logger.warning(f'Quark API 调用失败，使用原图: {e}')
            return None

    def _send_to_printer(self, pil_image):
        """使用 Windows GDI 将 PIL Image 渲染到打印机（兼容 Epson/HP/Canon 等）"""
        import win32ui
        import win32print
        import win32gui
        from PIL import ImageWin

        printer_name = self.config.get('default_printer', '')
        if not printer_name:
            printer_name = win32print.GetDefaultPrinter()

        logger.info(f'_send_to_printer: image={pil_image.size} mode={pil_image.mode} printer={printer_name}')

        # Determine required page orientation from image
        img_w, img_h = pil_image.size
        need_landscape = img_w > img_h

        # Create DEVMODE with correct orientation + simplex duplex
        handle = win32print.OpenPrinter(printer_name)
        try:
            dm = win32print.GetPrinter(handle, 2)['pDevMode']
            dm.Orientation = 2 if need_landscape else 1
            dm.Duplex = 1  # DMDUP_SIMPLEX
            dm.Fields = dm.Fields | 1 | 0x1000  # DM_ORIENTATION | DM_DUPLEX
            dc_handle = win32gui.CreateDC('WINSPOOL', printer_name, dm)
        finally:
            win32print.ClosePrinter(handle)

        hdc = win32ui.CreateDCFromHandle(dc_handle)

        try:
            hdc.StartDoc('Print Job')
            hdc.StartPage()

            page_width = hdc.GetDeviceCaps(110)   # HORZRES
            page_height = hdc.GetDeviceCaps(111)  # VERTRES

            color = self.config.get('default_color', True)
            if color:
                img = pil_image.convert('RGB')
            else:
                img = pil_image.convert('L')

            img_w, img_h = img.size

            # Scale to fit printable area, maintain aspect ratio
            scale = min(page_width / img_w, page_height / img_h)
            draw_w = int(img_w * scale)
            draw_h = int(img_h * scale)
            x = (page_width - draw_w) // 2
            y = (page_height - draw_h) // 2

            # Draw image onto printer DC via GDI
            dib = ImageWin.Dib(img)
            dib.draw(hdc.GetHandleOutput(), (x, y, x + draw_w, y + draw_h))

            hdc.EndPage()
            hdc.EndDoc()
            logger.info(f'GDI 打印发送成功: 页面 {page_width}x{page_height}, 图片 {draw_w}x{draw_h}')
        finally:
            hdc.DeleteDC()
