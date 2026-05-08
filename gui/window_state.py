"""Window state persistence for position, size, and active page."""
import json
import os
from pathlib import Path

PERSISTENT_DIR = Path(os.environ.get("APPDATA", ".")) / "iOSPrintServer"
STATE_FILE = PERSISTENT_DIR / "window_state.json"


def save_state(page) -> None:
    state = {
        "width": page.window.width,
        "height": page.window.height,
        "left": page.window.left,
        "top": page.window.top,
        "active_page": getattr(page, "_active_index", 0),
    }
    PERSISTENT_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def load_state(page) -> int:
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        if state.get("width"):
            page.window.width = state["width"]
        if state.get("height"):
            page.window.height = state["height"]
        if state.get("left"):
            page.window.left = state["left"]
        if state.get("top"):
            page.window.top = state["top"]
        return state.get("active_page", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0
