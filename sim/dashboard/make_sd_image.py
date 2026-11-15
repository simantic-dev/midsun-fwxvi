#!/usr/bin/env python3
"""Write an empty 16 MB FAT16 volume (no partition table), the telemetry board's SD card.

    python3 sim/dashboard/make_sd_image.py sim/dashboard/sd.img

FatFs mounts a volume with no partition table. Layout: 512-byte sectors, 4 sectors a cluster, 1 reserved
sector, 2 FATs of 32 sectors, 512 root entries (32 sectors), 32768 sectors in all.
"""
import struct
import sys

SECTOR, TOTAL, PER_CLUSTER, RESERVED, FATS, FAT_SECTORS, ROOT_ENTRIES = 512, 32768, 4, 1, 2, 32, 512


def image():
    boot = bytearray(SECTOR)
    boot[0:3] = b"\xEB\x3C\x90"                                   # jump over the BPB
    boot[3:11] = b"SIMANTIC"                                      # OEM name
    struct.pack_into("<HBHBHHBHHHII", boot, 11,
                     SECTOR, PER_CLUSTER, RESERVED, FATS, ROOT_ENTRIES,
                     TOTAL, 0xF8, FAT_SECTORS, 32, 16, 0, 0)      # BPB: geometry 32 sectors/track, 16 heads
    struct.pack_into("<BBBI11s8s", boot, 36, 0x80, 0, 0x29, 0x12345678, b"SDCARD     ", b"FAT16   ")
    boot[510:512] = b"\x55\xAA"
    fat = bytearray(FAT_SECTORS * SECTOR)
    fat[0:4] = b"\xF8\xFF\xFF\xFF"                                # media byte, end-of-chain for cluster 1
    img = bytearray(TOTAL * SECTOR)
    img[0:SECTOR] = boot
    for i in range(FATS):
        start = (RESERVED + i * FAT_SECTORS) * SECTOR
        img[start:start + len(fat)] = fat
    return img


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sim/dashboard/sd.img"
    with open(out, "wb") as f:
        f.write(image())
