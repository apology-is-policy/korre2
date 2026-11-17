"""Scan a FLAC file for valid frame headers and report contiguous runs.

Useful for damaged files: shows exactly which byte ranges / frame numbers still hold
decodable audio. Prints only offsets and frame numbers, never file content.

    python flacscan.py <file.flac>
"""
from __future__ import annotations

import os
import sys

CHUNK = 64 << 20


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def parse_header(buf: bytes, i: int, sr_code: int | None, ss_code: int | None):
    """Return the frame/sample number if a CRC-valid frame header starts at buf[i]."""
    if i + 16 > len(buf) or buf[i] != 0xFF or (buf[i + 1] & 0xFE) != 0xF8:
        return None
    bs, sr = buf[i + 2] >> 4, buf[i + 2] & 0xF
    ch, ss, reserved = buf[i + 3] >> 4, (buf[i + 3] >> 1) & 7, buf[i + 3] & 1
    if bs == 0 or sr == 15 or ch > 10 or ss == 3 or reserved:
        return None
    if (sr_code is not None and sr != sr_code) or (ss_code is not None and ss != ss_code):
        return None
    j = i + 4
    first = buf[j]
    for mask, value, extra in ((0x80, 0x00, 0), (0xE0, 0xC0, 1), (0xF0, 0xE0, 2),
                               (0xF8, 0xF0, 3), (0xFC, 0xF8, 4), (0xFE, 0xFC, 5), (0xFF, 0xFE, 6)):
        if first & mask == value:
            num = first & ~mask & 0xFF
            break
    else:
        return None
    j += 1
    for _ in range(extra):
        if buf[j] & 0xC0 != 0x80:
            return None
        num = (num << 6) | (buf[j] & 0x3F)
        j += 1
    j += {6: 1, 7: 2}.get(bs, 0)
    j += {12: 1, 13: 2, 14: 2}.get(sr, 0)
    return num if crc8(buf[i:j]) == buf[j] else None


def scan(path: str) -> None:
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(1 << 20)
        sr_code = ss_code = None
        k = head.find(b"\xff\xf8")
        while k >= 0:
            if parse_header(head, k, None, None) is not None:
                sr_code, ss_code = head[k + 2] & 0xF, (head[k + 3] >> 1) & 7
                break
            k = head.find(b"\xff\xf8", k + 1)
        print(f"first frame at byte {k} (sample-rate code {sr_code}, sample-size code {ss_code})")

        runs: list[list[int]] = []  # [first_off, last_off, first_num, last_num, count]
        pos = 0
        while pos < size:
            f.seek(pos)
            buf = f.read(CHUNK + 64)
            if not buf:
                break
            i = buf.find(b"\xff")
            while 0 <= i < min(len(buf), CHUNK):
                num = parse_header(buf, i, sr_code, ss_code)
                if num is not None:
                    off = pos + i
                    if runs and num == runs[-1][3] + 1:
                        runs[-1][1], runs[-1][3] = off, num
                        runs[-1][4] += 1
                    else:
                        runs.append([off, off, num, num, 1])
                i = buf.find(b"\xff", i + 1)
            pos += CHUNK

    real = [r for r in runs if r[4] >= 3]
    print(f"file size {size} bytes; runs of >=3 consecutive frames: {len(real)}; "
          f"stray header-like matches: {sum(r[4] < 3 for r in runs)}")
    for a, b, n0, n1, cnt in real:
        print(f"  bytes {a:>11}..{b:>11} ({a / size * 100:5.2f}%..{b / size * 100:5.2f}%)"
              f"  frames {n0}..{n1}  ({cnt} frames)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    scan(sys.argv[1])
