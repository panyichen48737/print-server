"""GUI entry point (python -m gui)."""
import sys
from pathlib import Path

# 确保项目根在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from launcher import main  # noqa: E402

main()
