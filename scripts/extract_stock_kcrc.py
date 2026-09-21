#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile


SECTIONS = [
    ("normal", "__start___ksymtab", "__stop___ksymtab", "__start___kcrctab"),
    ("gpl", "__start___ksymtab_gpl", "__stop___ksymtab_gpl", "__start___kcrctab_gpl"),
    ("gpl_future", "__start___ksymtab_gpl_future", "__stop___ksymtab_gpl_future", "__start___kcrctab_gpl_future"),
    ("unused", "__start___ksymtab_unused", "__stop___ksymtab_unused", "__start___kcrctab_unused"),
    ("unused_gpl", "__start___ksymtab_unused_gpl", "__stop___ksymtab_unused_gpl", "__start___kcrctab_unused_gpl"),
]


def parse_int(text):
    return int(text, 0)


def load_kallsyms(path):
    out = {}
    for line in Path(path).read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            addr = int(parts[0], 16)
        except ValueError:
            continue
        out[parts[-1]] = addr
    return out


class ElfMemory:
    def __init__(self, path):
        self.fp = open(path, "rb")
        self.elf = ELFFile(self.fp)
        self.loads = [s for s in self.elf.iter_segments() if s["p_type"] == "PT_LOAD"]

    def close(self):
        self.fp.close()

    def _offset(self, va, size=1):
        for seg in self.loads:
            start = int(seg["p_vaddr"])
            filesz = int(seg["p_filesz"])
            if start <= va and va + size <= start + filesz:
                return int(seg["p_offset"]) + (va - start)
        raise ValueError(f"virtual address 0x{va:x}+{size} is outside ELF PT_LOAD ranges")

    def read(self, va, size):
        off = self._offset(va, size)
        self.fp.seek(off)
        data = self.fp.read(size)
        if len(data) != size:
            raise ValueError(f"short read at virtual address 0x{va:x}")
        return data

    def u32(self, va):
        return struct.unpack("<I", self.read(va, 4))[0]

    def s32(self, va):
        return struct.unpack("<i", self.read(va, 4))[0]

    def u64(self, va):
        return struct.unpack("<Q", self.read(va, 8))[0]

    def cstring(self, va, limit=512):
        data = bytearray()
        for i in range(limit):
            ch = self.read(va + i, 1)
            if ch == b"\0":
                return data.decode("ascii")
            data += ch
        raise ValueError(f"unterminated string at 0x{va:x}")


def parse_oracle(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"bad oracle line: {line}")
        out[parts[0]] = parse_int(parts[1])
    return out


def looks_like_symbol_name(name):
    if not name or len(name) > 256:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.$")
    return all(ch in allowed for ch in name)


def detect_entry_format(mem, start, stop):
    candidates = []
    if (stop - start) % 12 == 0:
        candidates.append(("prel32", 12))
    if (stop - start) % 24 == 0:
        candidates.append(("absolute64", 24))

    for fmt, size in candidates:
        ok = 0
        count = min(20, (stop - start) // size)
        for idx in range(count):
            entry = start + idx * size
            try:
                if fmt == "prel32":
                    field = entry + 4
                    name_va = field + mem.s32(field)
                else:
                    name_va = mem.u64(entry + 8)
                name = mem.cstring(name_va)
                if looks_like_symbol_name(name):
                    ok += 1
            except Exception:
                pass
        if count and ok >= max(3, count * 3 // 4):
            return fmt, size

    raise ValueError(
        f"unable to infer kernel_symbol format for 0x{start:x}-0x{stop:x}"
    )


def extract_section(mem, syms, label, start_name, stop_name, crc_name):
    if start_name not in syms or stop_name not in syms or crc_name not in syms:
        return {}, {
            "label": label,
            "present": False,
            "missing": [
                n for n in (start_name, stop_name, crc_name) if n not in syms
            ],
        }

    start = syms[start_name]
    stop = syms[stop_name]
    crc_start = syms[crc_name]
    fmt, entry_size = detect_entry_format(mem, start, stop)
    count = (stop - start) // entry_size
    result = {}

    for idx in range(count):
        entry = start + idx * entry_size
        if fmt == "prel32":
            name_field = entry + 4
            name_va = name_field + mem.s32(name_field)
        else:
            name_va = mem.u64(entry + 8)

        try:
            name = mem.cstring(name_va)
        except Exception as exc:
            raise ValueError(
                f"{label}: failed to read symbol name for entry {idx} at 0x{entry:x}: {exc}"
            ) from exc

        crc_entry = crc_start + idx * 4
        raw_u32 = mem.u32(crc_entry)
        raw_s32 = struct.unpack("<i", struct.pack("<I", raw_u32))[0]

        abs_crc = raw_u32
        rel_crc = None
        rel_target = crc_entry + raw_s32
        try:
            rel_crc = mem.u32(rel_target)
        except Exception:
            pass

        result[name] = {
            "section": label,
            "index": idx,
            "entry": entry,
            "crc_entry": crc_entry,
            "raw": raw_u32,
            "abs": abs_crc,
            "rel": rel_crc,
            "rel_target": rel_target,
        }

    meta = {
        "label": label,
        "present": True,
        "start": start,
        "stop": stop,
        "crc_start": crc_start,
        "format": fmt,
        "entry_size": entry_size,
        "count": count,
    }
    return result, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--elf", required=True)
    ap.add_argument("--kallsyms", required=True)
    ap.add_argument("--oracle", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    syms = load_kallsyms(args.kallsyms)
    oracle = parse_oracle(args.oracle)
    mem = ElfMemory(args.elf)

    try:
        exports = {}
        metas = []
        for section in SECTIONS:
            parsed, meta = extract_section(mem, syms, *section)
            metas.append(meta)
            for name, data in parsed.items():
                if name in exports:
                    raise ValueError(f"duplicate exported symbol {name}")
                exports[name] = data

        for meta in metas:
            if meta["present"]:
                print(
                    "KCRC_SECTION "
                    f"{meta['label']} count={meta['count']} "
                    f"format={meta['format']} "
                    f"ksymtab=0x{meta['start']:x}-0x{meta['stop']:x} "
                    f"kcrctab=0x{meta['crc_start']:x}"
                )
            else:
                print(
                    "KCRC_SECTION "
                    f"{meta['label']} absent missing={','.join(meta['missing'])}"
                )

        abs_score = 0
        rel_score = 0
        found = 0
        for name, expected in oracle.items():
            item = exports.get(name)
            if item is None:
                continue
            found += 1
            if item["abs"] == expected:
                abs_score += 1
            if item["rel"] == expected:
                rel_score += 1

        print(f"STOCK_IMAGE_KCRC_FOUND={found}/{len(oracle)}")
        print(f"STOCK_IMAGE_KCRC_ABS_SCORE={abs_score}/{len(oracle)}")
        print(f"STOCK_IMAGE_KCRC_REL_SCORE={rel_score}/{len(oracle)}")

        if rel_score > abs_score:
            mode = "relative"
        elif abs_score > rel_score:
            mode = "absolute"
        else:
            raise SystemExit(
                f"cannot determine kcrctab mode: abs={abs_score} rel={rel_score}"
            )

        print(f"STOCK_IMAGE_KCRC_MODE={mode}")

        score = 0
        lines = []
        for name, expected in oracle.items():
            item = exports.get(name)
            if item is None:
                actual = None
                status = "MISSING"
                section = "-"
            else:
                actual = item["rel"] if mode == "relative" else item["abs"]
                section = item["section"]
                status = "MATCH" if actual == expected else "MISMATCH"
                if status == "MATCH":
                    score += 1

            actual_text = "MISSING" if actual is None else f"0x{actual:08x}"
            line = (
                f"{name} image={actual_text} module=0x{expected:08x} "
                f"status={status} section={section}"
            )
            print("stock-image-kcrc: " + line)
            lines.append(line)

        print(f"STOCK_IMAGE_CRC_PRESENT={found}/{len(oracle)}")
        print(f"STOCK_IMAGE_MODULE_CRC_SCORE={score}/{len(oracle)}")
        print(
            "STOCK_IMAGE_MODULE_ABI_IDENTICAL="
            + ("1" if score == len(oracle) else "0")
        )

        Path(args.output).write_text(
            "\n".join(
                [
                    f"mode={mode}",
                    f"present={found}/{len(oracle)}",
                    f"score={score}/{len(oracle)}",
                    *lines,
                    "",
                ]
            )
        )

        if found < 35:
            raise SystemExit("insufficient exported-symbol coverage")
    finally:
        mem.close()


if __name__ == "__main__":
    main()
