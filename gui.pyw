"""GUI 入口 — 无控制台窗口 (双击运行 / pythonw gui.pyw)"""

import sys
from pathlib import Path

_proj = Path(__file__).resolve().parent
if str(_proj) not in sys.path:
    sys.path.insert(0, str(_proj))

# 重定向 stderr 到日志文件方便调试
_log = _proj / 'gui_error.log'

try:
    from launcher import main

    main()
except Exception:
    import traceback

    with open(_log, 'w', encoding='utf-8') as f:
        traceback.print_exc(file=f)
    raise
