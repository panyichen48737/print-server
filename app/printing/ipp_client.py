"""IPP (Internet Printing Protocol) client for sending PDFs to network printers.

Implements a minimal IPP 1.1 Print-Job client per RFC 8010 / RFC 8011,
targeting IPP Everywhere endpoints at http://{ip}:631/ipp/print.
"""

from __future__ import annotations

import contextlib
import http.client
import re
import struct
from pathlib import Path

from loguru import logger

try:
    import win32print
except ImportError:
    win32print = None


_IPP_VERSION = b'\x01\x01'
_OP_PRINT_JOB = b'\x00\x02'
_REQUEST_ID = b'\x00\x00\x00\x01'

_TAG_OPERATION_ATTRIBUTES = b'\x01'
_TAG_JOB_ATTRIBUTES = b'\x02'
_TAG_END_OF_ATTRIBUTES = b'\x03'

_TAG_INTEGER = 0x21
_TAG_NAME_WITHOUT_LANGUAGE = 0x42
_TAG_KEYWORD = 0x44
_TAG_URI = 0x45
_TAG_CHARSET = 0x47
_TAG_NATURAL_LANGUAGE = 0x48

_IPP_PORT = 631
_IPP_PATH = '/ipp/print'
_HTTP_TIMEOUT = 60

_IP_REGEX = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')


def _encode_attribute(tag: int, name: str, value: bytes) -> bytes:
    """Encode a single IPP attribute as tag + name + value with length prefixes."""
    name_bytes = name.encode('ascii')
    return (
        bytes([tag])
        + struct.pack('>H', len(name_bytes))
        + name_bytes
        + struct.pack('>H', len(value))
        + value
    )


def _encode_string_attribute(tag: int, name: str, value: str) -> bytes:
    """Encode a string-valued IPP attribute (UTF-8)."""
    return _encode_attribute(tag, name, value.encode('utf-8'))


def _encode_integer_attribute(name: str, value: int) -> bytes:
    """Encode an integer-valued IPP attribute (4-byte big-endian per RFC 8010)."""
    return _encode_attribute(_TAG_INTEGER, name, struct.pack('>i', value))


def _build_ipp_request(printer_ip: str, copies: int, duplex: bool) -> bytes:
    """Build the IPP Print-Job request header (without the PDF payload)."""
    printer_uri = f'ipp://{printer_ip}:{_IPP_PORT}{_IPP_PATH}'

    header = _IPP_VERSION + _OP_PRINT_JOB + _REQUEST_ID

    op_attrs = (
        _TAG_OPERATION_ATTRIBUTES
        + _encode_string_attribute(_TAG_CHARSET, 'attributes-charset', 'utf-8')
        + _encode_string_attribute(_TAG_NATURAL_LANGUAGE, 'attributes-natural-language', 'en')
        + _encode_string_attribute(_TAG_URI, 'printer-uri', printer_uri)
        + _encode_string_attribute(
            _TAG_NAME_WITHOUT_LANGUAGE, 'requesting-user-name', 'print-server'
        )
    )

    job_attrs = (
        _TAG_JOB_ATTRIBUTES
        + _encode_string_attribute(_TAG_KEYWORD, 'document-format', 'application/pdf')
        + _encode_attribute(_TAG_INTEGER, 'copies', struct.pack('>i', copies))
    )
    if duplex:
        job_attrs += _encode_string_attribute(_TAG_KEYWORD, 'sides', 'two-sided-long-edge')

    return header + op_attrs + job_attrs + _TAG_END_OF_ATTRIBUTES


def _parse_ipp_response(data: bytes) -> int | None:
    """Parse the status code out of an IPP response header.

    Returns the 2-byte status code as an int, or None if the response is malformed.
    """
    if len(data) < 8:
        return None
    return struct.unpack('>H', data[2:4])[0]


def get_printer_ip(printer_name: str) -> str | None:
    """Return the IPv4 address of a Windows network printer, or None.

    Looks up the printer's port via win32print.GetPrinter() and scans the port
    name for an IPv4 pattern (covers TCP/IP ports named ``IP_192.168.1.100``,
    ``192.168.1.100``, WSD ports carrying an IP, etc.).
    """
    if win32print is None:
        logger.warning('win32print is not available; cannot resolve printer IP')
        return None

    try:
        handle = win32print.OpenPrinter(printer_name)
    except Exception as exc:
        logger.warning(f"Failed to open printer '{printer_name}': {exc}")
        return None

    try:
        info = win32print.GetPrinter(handle, 2)
    except Exception as exc:
        logger.warning(f"Failed to get printer info for '{printer_name}': {exc}")
        return None
    finally:
        with contextlib.suppress(Exception):
            win32print.ClosePrinter(handle)

    port_name = info.get('pPortName') if isinstance(info, dict) else None
    if not port_name:
        return None

    match = _IP_REGEX.search(port_name)
    if not match:
        return None

    ip = match.group(0)
    if not all(0 <= int(octet) <= 255 for octet in ip.split('.')):
        return None
    return ip


def print_via_ipp(printer_ip: str, pdf_path: str, copies: int = 1, duplex: bool = False) -> bool:
    """Send a PDF to a network printer via IPP Print-Job.

    Builds a minimal IPP 1.1 request per RFC 8010 and POSTs it to
    ``http://{printer_ip}:631/ipp/print`` with ``application/ipp`` content type.

    Args:
        printer_ip: IPv4 address of the target printer.
        pdf_path: Absolute path to the PDF file to print.
        copies: Number of copies (default 1).
        duplex: If True, request two-sided-long-edge printing.

    Returns:
        True on IPP success status (0x0000), False on any failure.

    Raises:
        FileNotFoundError: If pdf_path does not exist.
    """
    if not Path(pdf_path).is_file():
        raise FileNotFoundError(f'PDF file not found: {pdf_path}')

    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()

    request_body = _build_ipp_request(printer_ip, copies, duplex) + pdf_bytes

    conn: http.client.HTTPConnection | None = None
    try:
        conn = http.client.HTTPConnection(printer_ip, _IPP_PORT, timeout=_HTTP_TIMEOUT)
        conn.request(
            'POST',
            _IPP_PATH,
            body=request_body,
            headers={
                'Content-Type': 'application/ipp',
                'Content-Length': str(len(request_body)),
            },
        )
        response = conn.getresponse()
        response_data = response.read()

        if response.status != 200:
            logger.warning(f'IPP HTTP error from {printer_ip}: {response.status} {response.reason}')
            return False

        status_code = _parse_ipp_response(response_data)
        if status_code is None:
            logger.warning(f'IPP response from {printer_ip} too short to parse')
            return False

        if status_code == 0x0000:
            logger.info(f'IPP Print-Job accepted by {printer_ip} ({len(pdf_bytes)} bytes)')
            return True

        logger.warning(f'IPP Print-Job rejected by {printer_ip}: status=0x{status_code:04x}')
        return False

    except TimeoutError as exc:
        logger.warning(f'IPP connection to {printer_ip} timed out: {exc}')
        return False
    except (ConnectionRefusedError, OSError) as exc:
        logger.warning(f'IPP connection to {printer_ip} failed: {exc}')
        return False
    except http.client.HTTPException as exc:
        logger.warning(f'IPP HTTP exchange with {printer_ip} failed: {exc}')
        return False
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()


def is_printer_ipp_supported(printer_name: str) -> bool:
    """Return True if the printer looks like a network printer with an IP port.

    This is a necessary-but-not-sufficient check: it only confirms that the
    printer's port contains a routable IPv4 address. The actual IPP capability
    is only confirmed when ``print_via_ipp`` succeeds.
    """
    return get_printer_ip(printer_name) is not None
