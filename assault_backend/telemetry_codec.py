"""
Binary Telemetry & Replay Codec (MessagePack + Compressed Envelope)
===================================================================
Implements Roadmap Section 6.5:
Compact binary serialization (MessagePack specification + optional deflate Ext
envelope for large multi-turn payloads) between `assault_backend`, `mlops/reporting`,
and web clients (`GameController.ts`, `GameCanvas.tsx`, `MLOps Viewer`), while
preserving human-readable JSON for offline forensic inspection.
"""

from __future__ import annotations

import math
import struct
import zlib
from enum import Enum
from pathlib import Path
from typing import Any, Tuple

try:
    import msgpack as _c_msgpack  # type: ignore
except ImportError:
    _c_msgpack = None

MSGPACK_MIME_TYPE = "application/x-msgpack"
_EXT_ZLIB_COMPRESSED = 1


def sanitize_telemetry_value(value: Any) -> Any:
    """Normalize domain objects (HexCoord, Enum, Path, NaN/Inf) into MessagePack-safe primitives."""
    if value is None or isinstance(value, (bool, int, str, bytes)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "q") and hasattr(value, "r") and not isinstance(value, dict):
        return {"q": int(getattr(value, "q")), "r": int(getattr(value, "r"))}
    if isinstance(value, dict):
        return {str(k): sanitize_telemetry_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [sanitize_telemetry_value(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return sanitize_telemetry_value(value.to_dict())
    return str(value)


def _py_pack(obj: Any, buf: bytearray) -> None:
    if obj is None:
        buf.append(0xC0)
    elif obj is False:
        buf.append(0xC2)
    elif obj is True:
        buf.append(0xC3)
    elif isinstance(obj, int):
        if 0 <= obj <= 0x7F:
            buf.append(obj)
        elif -32 <= obj < 0:
            buf.append(obj & 0xFF)
        elif 0 <= obj <= 0xFF:
            buf.extend(struct.pack(">BB", 0xCC, obj))
        elif 0 <= obj <= 0xFFFF:
            buf.extend(struct.pack(">BH", 0xCD, obj))
        elif 0 <= obj <= 0xFFFFFFFF:
            buf.extend(struct.pack(">BI", 0xCE, obj))
        elif 0 <= obj <= 0xFFFFFFFFFFFFFFFF:
            buf.extend(struct.pack(">BQ", 0xCF, obj))
        elif -128 <= obj < 0:
            buf.extend(struct.pack(">Bb", 0xD0, obj))
        elif -32768 <= obj < 0:
            buf.extend(struct.pack(">Bh", 0xD1, obj))
        elif -2147483648 <= obj < 0:
            buf.extend(struct.pack(">Bi", 0xD2, obj))
        else:
            buf.extend(struct.pack(">Bq", 0xD3, obj))
    elif isinstance(obj, float):
        if not math.isfinite(obj):
            buf.append(0xC0)
        else:
            buf.extend(struct.pack(">Bd", 0xCB, obj))
    elif isinstance(obj, str):
        raw = obj.encode("utf-8")
        n = len(raw)
        if n <= 31:
            buf.append(0xA0 | n)
        elif n <= 0xFF:
            buf.extend(struct.pack(">BB", 0xD9, n))
        elif n <= 0xFFFF:
            buf.extend(struct.pack(">BH", 0xDA, n))
        else:
            buf.extend(struct.pack(">BI", 0xDB, n))
        buf.extend(raw)
    elif isinstance(obj, (bytes, bytearray, memoryview)):
        raw = bytes(obj)
        n = len(raw)
        if n <= 0xFF:
            buf.extend(struct.pack(">BB", 0xC4, n))
        elif n <= 0xFFFF:
            buf.extend(struct.pack(">BH", 0xC5, n))
        else:
            buf.extend(struct.pack(">BI", 0xC6, n))
        buf.extend(raw)
    elif isinstance(obj, (list, tuple)):
        n = len(obj)
        if n <= 15:
            buf.append(0x90 | n)
        elif n <= 0xFFFF:
            buf.extend(struct.pack(">BH", 0xDC, n))
        else:
            buf.extend(struct.pack(">BI", 0xDD, n))
        for item in obj:
            _py_pack(item, buf)
    elif isinstance(obj, dict):
        n = len(obj)
        if n <= 15:
            buf.append(0x80 | n)
        elif n <= 0xFFFF:
            buf.extend(struct.pack(">BH", 0xDE, n))
        else:
            buf.extend(struct.pack(">BI", 0xDF, n))
        for k, v in obj.items():
            _py_pack(str(k), buf)
            _py_pack(v, buf)
    else:
        _py_pack(sanitize_telemetry_value(obj), buf)


def _py_unpack(mv: memoryview, offset: int = 0) -> Tuple[Any, int]:
    b = mv[offset]
    offset += 1

    if b <= 0x7F:
        return b, offset
    if b >= 0xE0:
        return b - 256, offset
    if 0x80 <= b <= 0x8F:
        n = b & 0x0F
        out = {}
        for _ in range(n):
            k, offset = _py_unpack(mv, offset)
            v, offset = _py_unpack(mv, offset)
            out[str(k)] = v
        return out, offset
    if 0x90 <= b <= 0x9F:
        n = b & 0x0F
        out_list = []
        for _ in range(n):
            item, offset = _py_unpack(mv, offset)
            out_list.append(item)
        return out_list, offset
    if 0xA0 <= b <= 0xBF:
        n = b & 0x1F
        s = bytes(mv[offset : offset + n]).decode("utf-8")
        return s, offset + n
    if b == 0xC0:
        return None, offset
    if b == 0xC2:
        return False, offset
    if b == 0xC3:
        return True, offset
    if b == 0xC4:
        n = mv[offset]
        offset += 1
        return bytes(mv[offset : offset + n]), offset + n
    if b == 0xC5:
        (n,) = struct.unpack_from(">H", mv, offset)
        offset += 2
        return bytes(mv[offset : offset + n]), offset + n
    if b == 0xC6:
        (n,) = struct.unpack_from(">I", mv, offset)
        offset += 4
        return bytes(mv[offset : offset + n]), offset + n
    if b == 0xC7:
        n, ext_type = struct.unpack_from(">Bb", mv, offset)
        offset += 2
        data = bytes(mv[offset : offset + n])
        offset += n
        if ext_type == _EXT_ZLIB_COMPRESSED:
            return decode_msgpack(zlib.decompress(data)), offset
        return data, offset
    if b == 0xC8:
        n, ext_type = struct.unpack_from(">Hb", mv, offset)
        offset += 3
        data = bytes(mv[offset : offset + n])
        offset += n
        if ext_type == _EXT_ZLIB_COMPRESSED:
            return decode_msgpack(zlib.decompress(data)), offset
        return data, offset
    if b == 0xC9:
        n, ext_type = struct.unpack_from(">Ib", mv, offset)
        offset += 5
        data = bytes(mv[offset : offset + n])
        offset += n
        if ext_type == _EXT_ZLIB_COMPRESSED:
            return decode_msgpack(zlib.decompress(data)), offset
        return data, offset
    if b == 0xCA:
        (val,) = struct.unpack_from(">f", mv, offset)
        return float(val), offset + 4
    if b == 0xCB:
        (val,) = struct.unpack_from(">d", mv, offset)
        return float(val), offset + 8
    if b == 0xCC:
        return mv[offset], offset + 1
    if b == 0xCD:
        (val,) = struct.unpack_from(">H", mv, offset)
        return val, offset + 2
    if b == 0xCE:
        (val,) = struct.unpack_from(">I", mv, offset)
        return val, offset + 4
    if b == 0xCF:
        (val,) = struct.unpack_from(">Q", mv, offset)
        return val, offset + 8
    if b == 0xD0:
        (val,) = struct.unpack_from(">b", mv, offset)
        return val, offset + 1
    if b == 0xD1:
        (val,) = struct.unpack_from(">h", mv, offset)
        return val, offset + 2
    if b == 0xD2:
        (val,) = struct.unpack_from(">i", mv, offset)
        return val, offset + 4
    if b == 0xD3:
        (val,) = struct.unpack_from(">q", mv, offset)
        return val, offset + 8
    if b == 0xD9:
        n = mv[offset]
        offset += 1
        return bytes(mv[offset : offset + n]).decode("utf-8"), offset + n
    if b == 0xDA:
        (n,) = struct.unpack_from(">H", mv, offset)
        offset += 2
        return bytes(mv[offset : offset + n]).decode("utf-8"), offset + n
    if b == 0xDB:
        (n,) = struct.unpack_from(">I", mv, offset)
        offset += 4
        return bytes(mv[offset : offset + n]).decode("utf-8"), offset + n
    if b == 0xDC:
        (n,) = struct.unpack_from(">H", mv, offset)
        offset += 2
        out_list = []
        for _ in range(n):
            item, offset = _py_unpack(mv, offset)
            out_list.append(item)
        return out_list, offset
    if b == 0xDD:
        (n,) = struct.unpack_from(">I", mv, offset)
        offset += 4
        out_list = []
        for _ in range(n):
            item, offset = _py_unpack(mv, offset)
            out_list.append(item)
        return out_list, offset
    if b == 0xDE:
        (n,) = struct.unpack_from(">H", mv, offset)
        offset += 2
        out = {}
        for _ in range(n):
            k, offset = _py_unpack(mv, offset)
            v, offset = _py_unpack(mv, offset)
            out[str(k)] = v
        return out, offset
    if b == 0xDF:
        (n,) = struct.unpack_from(">I", mv, offset)
        offset += 4
        out = {}
        for _ in range(n):
            k, offset = _py_unpack(mv, offset)
            v, offset = _py_unpack(mv, offset)
            out[str(k)] = v
        return out, offset

    raise ValueError(f"Unsupported MessagePack marker byte: 0x{b:02X}")


def encode_msgpack(payload: Any, compress_threshold: int = 0) -> bytes:
    """
    Encode arbitrary Python telemetry/state payload into RFC-8949 MessagePack binary bytes.
    If `compress_threshold > 0` and the serialized byte length exceeds `compress_threshold`,
    wraps the payload in a MessagePack Ext (type=1) zlib envelope (~80-90% size reduction).
    """
    clean = sanitize_telemetry_value(payload)
    if _c_msgpack is not None:
        raw = bytes(_c_msgpack.packb(clean, use_bin_type=True))
    else:
        buf = bytearray()
        _py_pack(clean, buf)
        raw = bytes(buf)

    if compress_threshold > 0 and len(raw) >= compress_threshold:
        comp = zlib.compress(raw, level=6)
        n = len(comp)
        out = bytearray()
        if n <= 0xFF:
            out.extend(struct.pack(">BBb", 0xC7, n, _EXT_ZLIB_COMPRESSED))
        elif n <= 0xFFFF:
            out.extend(struct.pack(">BHb", 0xC8, n, _EXT_ZLIB_COMPRESSED))
        else:
            out.extend(struct.pack(">BIb", 0xC9, n, _EXT_ZLIB_COMPRESSED))
        out.extend(comp)
        return bytes(out)
    return raw


def decode_msgpack(data: bytes | bytearray | memoryview) -> Any:
    """Decode MessagePack binary bytes (including compressed Ext=1 envelopes) back to Python."""
    mv = memoryview(data)
    if len(mv) == 0:
        return None
    first = mv[0]
    if _c_msgpack is not None and first not in (0xC7, 0xC8, 0xC9):
        return _c_msgpack.unpackb(mv, raw=False)
    val, _ = _py_unpack(mv, 0)
    return val
