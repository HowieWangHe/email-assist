#!/usr/bin/env python3
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path


def write_png(path: Path, width: int, height: int, rows: list[bytes]) -> None:
    raw = b"".join(b"\x00" + row for row in rows)
    payload = b"\x89PNG\r\n\x1a\n"
    payload += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += _chunk(b"IDAT", zlib.compress(raw, 9))
    payload += _chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def blend(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rect(
    pixels: list[list[tuple[int, int, int]]],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    radius: int = 0,
) -> None:
    height = len(pixels)
    width = len(pixels[0])
    for y in range(max(0, y0), min(height, y1)):
        for x in range(max(0, x0), min(width, x1)):
            if radius:
                dx = max(x0 + radius - x, 0, x - (x1 - radius - 1))
                dy = max(y0 + radius - y, 0, y - (y1 - radius - 1))
                if dx * dx + dy * dy > radius * radius:
                    continue
            pixels[y][x] = color


def line(
    pixels: list[list[tuple[int, int, int]]],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
    width: int = 2,
) -> None:
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(steps + 1):
        t = i / steps
        x = round(x0 + (x1 - x0) * t)
        y = round(y0 + (y1 - y0) * t)
        rect(pixels, x - width, y - width, x + width + 1, y + width + 1, color, radius=width)


def main() -> int:
    width, height = 960, 420
    top = (241, 248, 246)
    bottom = (226, 238, 242)
    pixels: list[list[tuple[int, int, int]]] = []
    for y in range(height):
        row = []
        for x in range(width):
            t = y / (height - 1)
            base = blend(top, bottom, t)
            wave = int(7 * math.sin((x + y * 0.7) / 42))
            row.append(tuple(max(0, min(255, c + wave)) for c in base))
        pixels.append(row)

    # Workflow board.
    rect(pixels, 74, 64, 470, 346, (255, 255, 255), radius=18)
    rect(pixels, 98, 94, 278, 120, (15, 118, 110), radius=8)
    rect(pixels, 98, 144, 420, 164, (221, 229, 233), radius=5)
    rect(pixels, 98, 184, 360, 204, (221, 229, 233), radius=5)
    rect(pixels, 98, 224, 392, 244, (221, 229, 233), radius=5)
    rect(pixels, 98, 276, 210, 310, (20, 184, 166), radius=10)
    rect(pixels, 228, 276, 340, 310, (30, 64, 175), radius=10)

    # Message cards and attachment flow.
    rect(pixels, 540, 80, 820, 154, (255, 255, 255), radius=14)
    rect(pixels, 562, 104, 650, 118, (15, 118, 110), radius=5)
    rect(pixels, 562, 130, 778, 140, (203, 213, 225), radius=4)
    rect(pixels, 596, 206, 876, 280, (255, 255, 255), radius=14)
    rect(pixels, 618, 230, 706, 244, (30, 64, 175), radius=5)
    rect(pixels, 618, 256, 834, 266, (203, 213, 225), radius=4)
    line(pixels, 470, 184, 540, 118, (20, 184, 166), width=3)
    line(pixels, 470, 220, 596, 244, (30, 64, 175), width=3)

    # Attachment chip.
    rect(pixels, 690, 318, 852, 362, (236, 253, 245), radius=12)
    rect(pixels, 714, 332, 748, 348, (20, 184, 166), radius=5)
    rect(pixels, 762, 332, 826, 348, (100, 116, 139), radius=4)

    rows = [b"".join(bytes(pixel) for pixel in row) for row in pixels]
    write_png(Path("app/static/mail-workflow.png"), width, height, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
