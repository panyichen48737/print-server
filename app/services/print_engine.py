import os
import logging
import io
import threading

logger = logging.getLogger('print_server')


class PrintEngine:
    def __init__(self, config, dingtalk=None, excel_lock=None, ppt_lock=None):
        self.config = config
        self.dingtalk = dingtalk
        self.excel_lock = excel_lock or threading.Lock()
        self.ppt_lock = ppt_lock or threading.Lock()
        self._active_jobs = {}
        self._active_jobs_lock = threading.Lock()

    def print_file(self, filepath, file_type, job_id, word_lock, print_params=None):
        """根据文件类型分发到对应的打印方法"""
        ext = file_type.lower()
        if ext in ('.doc', '.docx'):
            return self._print_word(filepath, job_id, word_lock, print_params)
        elif ext == '.pdf':
            return self._print_pdf(filepath, job_id, print_params)
        elif ext in ('.xls', '.xlsx'):
            return self._print_excel(filepath, job_id, print_params)
        elif ext in ('.ppt', '.pptx'):
            return self._print_ppt(filepath, job_id, print_params)
        elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.heif'):
            return self._print_image(filepath, job_id, print_params)
        else:
            raise ValueError(f'不支持的文件类型: {ext}')

    def _print_word(self, filepath, job_id, word_lock, print_params=None):
        """通过 win32com 调用 Word 打印"""
        if print_params is None:
            print_params = {}
        # Get printer name for tracking
        _printer_com = print_params.get('printer_name') if print_params else None
        if not _printer_com:
            _printer_com = self.config.get('default_printer', '')
        with self._active_jobs_lock:
            self._active_jobs[job_id] = {
                'printer': _printer_com,
                'method': 'com'
            }
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

                printer = print_params.get('printer_name') or self.config.get('default_printer', '')
                if printer:
                    word.ActivePrinter = printer

                copies = print_params.get('copies') or self.config.get('default_copies', 1)
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
                with self._active_jobs_lock:
                    self._active_jobs.pop(job_id, None)

    def _print_excel(self, filepath, job_id, print_params=None):
        """通过 win32com 调用 Excel 打印"""
        if print_params is None:
            print_params = {}
        # Get printer name for tracking
        _printer_com = print_params.get('printer_name') if print_params else None
        if not _printer_com:
            _printer_com = self.config.get('default_printer', '')
        with self._active_jobs_lock:
            self._active_jobs[job_id] = {
                'printer': _printer_com,
                'method': 'com'
            }
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

                printer = print_params.get('printer_name') or self.config.get('default_printer', '')
                if printer:
                    excel.ActivePrinter = printer

                copies = print_params.get('copies') or self.config.get('default_copies', 1)
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
                with self._active_jobs_lock:
                    self._active_jobs.pop(job_id, None)

    def _print_ppt(self, filepath, job_id, print_params=None):
        """通过 win32com 调用 PowerPoint 打印"""
        if print_params is None:
            print_params = {}
        # Get printer name for tracking
        _printer_com = print_params.get('printer_name') if print_params else None
        if not _printer_com:
            _printer_com = self.config.get('default_printer', '')
        with self._active_jobs_lock:
            self._active_jobs[job_id] = {
                'printer': _printer_com,
                'method': 'com'
            }
        with self.ppt_lock:
            import win32com.client
            import pythoncom
            ppt = None
            try:
                pythoncom.CoInitialize()
                ppt = win32com.client.Dispatch('PowerPoint.Application')
                ppt.Visible = False
                presentation = ppt.Presentations.Open(os.path.abspath(filepath))

                printer = print_params.get('printer_name') or self.config.get('default_printer', '')
                if printer:
                    ppt.ActivePrinter = printer

                copies = print_params.get('copies') or self.config.get('default_copies', 1)
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
                with self._active_jobs_lock:
                    self._active_jobs.pop(job_id, None)

    def _print_pdf(self, filepath, job_id, print_params=None):
        """使用 Chromium (Chrome/Edge) headless 模式直接打印 PDF，质量最佳"""
        if print_params is None:
            print_params = {}
        import subprocess
        chrome_path = self._find_chromium()
        if not chrome_path:
            raise RuntimeError('未找到 Chromium 浏览器 (Chrome/Edge)')

        printer_name = print_params.get('printer_name') or self.config.get('default_printer', '')
        if not printer_name:
            import win32print
            printer_name = win32print.GetDefaultPrinter()

        proc = subprocess.Popen(
            [chrome_path, '--headless', '--disable-gpu',
             f'--print-to-printer="{printer_name}"',
             '--no-margins', '--no-pdf-header-footer',
             os.path.abspath(filepath)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        with self._active_jobs_lock:
            self._active_jobs[job_id] = {
                'printer': printer_name,
                'pid': proc.pid,
                'method': 'chromium'
            }
        stdout, stderr = proc.communicate(timeout=self.config.get('job_timeout', 300))
        if proc.returncode != 0:
            raise RuntimeError(f'Chrome 打印失败: {proc.returncode}\n{stderr[:500]}')
        with self._active_jobs_lock:
            self._active_jobs.pop(job_id, None)

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

    def _print_image(self, filepath, job_id, print_params=None):
        """处理图片：Quark API 预处理 → PIL 排版 → win32print 打印"""
        if print_params is None:
            print_params = {}
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
            paper_size = print_params.get('paper_size') or self.config.get('paper_size', 'A4')
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

            color_val = print_params.get('color')
            if color_val is not None:
                use_color = bool(color_val)
            else:
                use_color = self.config.get('default_color', True)

            if use_color:
                canvas = Image.new('RGB', (pw, ph), (255, 255, 255))
                img_resized = img.resize((new_w, new_h), Image.LANCZOS)
            else:
                canvas = Image.new('L', (pw, ph), (255))
                img_resized = img.resize((new_w, new_h), Image.LANCZOS).convert('L')

            x = (pw - new_w) // 2
            y = (ph - new_h) // 2
            # Handle alpha channel if present
            if img_resized.mode == 'RGBA':
                canvas.paste(img_resized, (x, y), img_resized)
            elif img_resized.mode == 'P':
                img_resized = img_resized.convert('RGBA')
                canvas.paste(img_resized, (x, y), img_resized)
            else:
                canvas.paste(img_resized, (x, y))

            # Step 4: Print via win32print
            self._send_to_printer(canvas, job_id, print_params)

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

    def _send_to_printer(self, pil_image, job_id, print_params=None):
        """使用 Windows GDI 将 PIL Image 渲染到打印机（兼容 Epson/HP/Canon 等）"""
        if print_params is None:
            print_params = {}
        import win32ui
        import win32print
        import win32gui
        from PIL import ImageWin

        printer_name = print_params.get('printer_name') or self.config.get('default_printer', '')
        if not printer_name:
            printer_name = win32print.GetDefaultPrinter()

        logger.info(f'_send_to_printer: image={pil_image.size} mode={pil_image.mode} printer={printer_name}')

        # Determine required page orientation from image
        img_w, img_h = pil_image.size
        need_landscape = img_w > img_h

        # Create DEVMODE with correct orientation + duplex
        handle = win32print.OpenPrinter(printer_name)
        try:
            dm = win32print.GetPrinter(handle, 2)['pDevMode']
            dm.Orientation = 2 if need_landscape else 1
            import win32con
            dm.Fields = dm.Fields | win32con.DM_ORIENTATION

            # Duplex handling — use per-job value if set
            duplex_val = print_params.get('duplex')
            if duplex_val is not None:
                dm.Duplex = 2 if duplex_val else 1  # 2 = DMDUP_VERTICAL, 1 = DMDUP_SIMPLEX
                dm.Fields = dm.Fields | win32con.DM_DUPLEX
            elif self.config.get('default_duplex', False):
                dm.Duplex = 2
                dm.Fields = dm.Fields | win32con.DM_DUPLEX
            else:
                dm.Duplex = 1  # simplex
                dm.Fields = dm.Fields | win32con.DM_DUPLEX

            dc_handle = win32gui.CreateDC('WINSPOOL', printer_name, dm)
        finally:
            win32print.ClosePrinter(handle)

        hdc = win32ui.CreateDCFromHandle(dc_handle)

        try:
            spool_job_id = hdc.StartDoc('Print Job')
            with self._active_jobs_lock:
                self._active_jobs[job_id] = {
                    'printer': printer_name,
                    'spool_job_id': spool_job_id,
                    'method': 'gdi'
                }
            try:
                hdc.StartPage()

                page_width = hdc.GetDeviceCaps(110)   # HORZRES
                page_height = hdc.GetDeviceCaps(111)  # VERTRES

                # Color handling — use per-job value if set
                color_val = print_params.get('color')
                if color_val is not None:
                    use_color = bool(color_val)
                else:
                    use_color = self.config.get('default_color', True)

                if use_color:
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
                with self._active_jobs_lock:
                    self._active_jobs.pop(job_id, None)
                logger.info(f'GDI 打印发送成功: 页面 {page_width}x{page_height}, 图片 {draw_w}x{draw_h}')
            except:
                with self._active_jobs_lock:
                    self._active_jobs.pop(job_id, None)
                raise
        finally:
            hdc.DeleteDC()
            with self._active_jobs_lock:
                self._active_jobs.pop(job_id, None)

    def cancel_active_job(self, job_id):
        with self._active_jobs_lock:
            info = self._active_jobs.get(job_id)
            if not info:
                return False
            del self._active_jobs[job_id]

        import win32print
        import subprocess
        printer = info['printer']

        if info['method'] == 'gdi':
            handle = win32print.OpenPrinter(printer)
            try:
                win32print.SetJob(handle, info['spool_job_id'], 0, win32print.JOB_CONTROL_DELETE)
                logger.info(f'GDI Spooler 作业 #{info["spool_job_id"]} 已取消')
            finally:
                win32print.ClosePrinter(handle)
            return True

        elif info['method'] == 'chromium':
            pid = info.get('pid')
            if pid:
                try:
                    subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=5)
                except Exception:
                    pass
            _cancel_all_spooler_jobs(printer)
            return True

        elif info['method'] == 'com':
            _cancel_all_spooler_jobs(printer)
            return True

        return False


def _cancel_all_spooler_jobs(printer_name):
    import win32print
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
            for job in info.get('cJobs', []):
                win32print.SetJob(handle, job['JobId'], 0, win32print.JOB_CONTROL_DELETE)
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        logger.warning(f'取消 Spooler 作业失败: {e}')
