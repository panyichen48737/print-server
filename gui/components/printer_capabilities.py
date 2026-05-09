"""Query printer capabilities via win32print.DeviceCapabilities."""
from __future__ import annotations

from dataclasses import dataclass, field

import win32print


DC_COPIES = 17
DC_PAPERNAMES = 16
DC_COLORDEVICE = 23
DC_DUPLEX = 29


@dataclass
class PrinterCapabilities:
    copies_max: int = 99
    supports_color: bool = True
    supports_duplex: bool = True
    paper_names: list[str] = field(default_factory=lambda: ["A4", "Letter", "A3"])


def query_capabilities(printer_name: str) -> PrinterCapabilities:
    """Query printer capabilities from Windows print system."""
    caps = PrinterCapabilities()
    try:
        copies = win32print.DeviceCapabilities(printer_name, None, DC_COPIES, None)
        if copies and copies[0] > 0:
            caps.copies_max = copies[0]
    except Exception:
        pass

    try:
        color = win32print.DeviceCapabilities(printer_name, None, DC_COLORDEVICE, None)
        if color and color[0] == 0:
            caps.supports_color = False
    except Exception:
        pass

    try:
        duplex = win32print.DeviceCapabilities(printer_name, None, DC_DUPLEX, None)
        if duplex and duplex[0] == 0:
            caps.supports_duplex = False
    except Exception:
        pass

    try:
        papers = win32print.DeviceCapabilities(printer_name, None, DC_PAPERNAMES, None)
        if papers and len(papers) > 0:
            caps.paper_names = list(papers)
    except Exception:
        pass

    return caps
