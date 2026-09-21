#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path

from vmlinux_to_elf.core.auto_unpack import VmlinuzDecompressor
from vmlinux_to_elf.core.kallsyms import KallsymsFinder

SECTION_SPECS = [
    (
        "normal",
        "__start___ksymtab",
        "__stop___ksymtab",
        "__start___kcrctab",
        "__start___kcrctab_gpl",
    ),
    (
        "gpl",
        "__start___ksymtab_gpl",
        "__stop___ksymtab_gpl",
        "__start___kcrctab_gpl",
        "__start___kcrctab_gpl_future",
    ),
    (
        "gpl_future",
        "__start___ksymtab_gpl_future",
        "__stop___ksymtab_gpl_future",
        "__start___kcrctab_gpl_future",
        "__start___kcrctab_unused",
    ),
    (
        "unused",
        "__start___ksymtab_unused",
        "__stop___ksymtab_unused",
        "__start___kcrctab_unused",
        "__start___kcrctab_unused_gpl",
    ),
]


def load_kallsyms(path):
    symbols = {}
    types = {}
    for line in Path(path).read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            addr = int(parts[0], 16)
        except ValueError:
            continue
        name = parts[-1]
        symbols[name] = addr
        types[name] = parts[1]
    return symbols, types


def load_oracle(path):
    oracle = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"bad oracle line: {line}")
        oracle[parts[0]] = int(parts[1], 0)
    return oracle


class ImageMemory:
    def __init__(self, data, base):
        self.data = bytes(data)
        self.base = base

    def offset(self, va, size=1):
        off = va - self.base
        if off < 0 or off + size > len(self.data):
            raise ValueError(
                f"VA 0x{va:x}+{size} outside raw Image "
                f"base=0x{self.base:x} size=0x{len(self.data):x}"
            )
        return off

    def read(self, va, size):
        off = self.offset(va, size)
        return self.data[off : off + size]

    def u32(self, va):
        return struct.unpack("<I", self.read(va, 4))[0]

    def s32(self, va):
        return struct.unpack("<i", self.read(va, 4))[0]

    def u64(self, va):
        return struct.unpack("<Q", self.read(va, 8))[0]

    def cstring(self, va, max_len=512):
        off = self.offset(va)
        end = self.data.find(b"\0", off, min(len(self.data), off + max_len))
        if end < 0:
            raise ValueError(f"unterminated string at 0x{va:x}")
        return self.data[off:end].decode("ascii")


def valid_symbol_name(name):
    if not name or len(name) > 256:
        return False
    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.$"
    )
    return all(ch in allowed for ch in name)


def choose_image_base(symbols, image_path):
    candidates = []
    for name in ("_text", "_stext", "stext"):
        if name in symbols and symbols[name] not in candidates:
            candidates.append(symbols[name])

    if not candidates:
        raise ValueError("kallsyms has no _text/_stext/stext base candidate")

    image_size = Path(image_path).stat().st_size
    ksym = symbols.get("__start___ksymtab")
    if ksym is None:
        raise ValueError("missing __start___ksymtab")

    for base in candidates:
        off = ksym - base
        print(
            f"IMAGE_BASE_CANDIDATE name_va=0x{base:x} "
            f"ksymtab_offset=0x{off:x} image_size=0x{image_size:x}"
        )
        if 0 <= off < image_size:
            return base

    raise ValueError(
        "no kernel text symbol produces a valid raw Image VA mapping"
    )


def decode_section(mem, symbols, spec):
    label, ksym_start_name, ksym_stop_name, crc_start_name, crc_stop_name = spec
    required = (
        ksym_start_name,
        ksym_stop_name,
        crc_start_name,
        crc_stop_name,
    )
    missing = [name for name in required if name not in symbols]
    if missing:
        print(f"KCRC_SECTION {label} absent missing={','.join(missing)}")
        return {}

    ksym_start = symbols[ksym_start_name]
    ksym_stop = symbols[ksym_stop_name]
    crc_start = symbols[crc_start_name]
    crc_stop = symbols[crc_stop_name]

    ksym_span = ksym_stop - ksym_start
    crc_span = crc_stop - crc_start

    if ksym_span == 0 and crc_span == 0:
        print(f"KCRC_SECTION {label} empty")
        return {}
    if crc_span <= 0 or crc_span % 4:
        raise ValueError(
            f"{label}: invalid kcrctab span 0x{crc_span:x}"
        )

    count = crc_span // 4
    if count <= 0:
        print(f"KCRC_SECTION {label} empty")
        return {}
    if ksym_span <= 0 or ksym_span % count:
        raise ValueError(
            f"{label}: ksymtab span 0x{ksym_span:x} "
            f"does not divide by CRC count {count}"
        )

    entry_size = ksym_span // count
    if entry_size not in (12, 24):
        raise ValueError(
            f"{label}: unexpected kernel_symbol size {entry_size}; "
            f"ksym_span=0x{ksym_span:x} crc_count={count}"
        )

    fmt = "prel32" if entry_size == 12 else "absolute64"
    print(
        f"KCRC_SECTION {label} count={count} "
        f"kernel_symbol_size={entry_size} format={fmt} "
        f"ksymtab=0x{ksym_start:x}-0x{ksym_stop:x} "
        f"kcrctab=0x{crc_start:x}-0x{crc_stop:x}"
    )

    result = {}
    for idx in range(count):
        entry = ksym_start + idx * entry_size

        if entry_size == 24:
            value_va = mem.u64(entry)
            name_va = mem.u64(entry + 8)
            namespace_va = mem.u64(entry + 16)
        else:
            value_field = entry
            name_field = entry + 4
            ns_field = entry + 8
            value_va = value_field + mem.s32(value_field)
            name_va = name_field + mem.s32(name_field)
            ns_delta = mem.s32(ns_field)
            namespace_va = 0 if ns_delta == 0 else ns_field + ns_delta

        name = mem.cstring(name_va)
        if not valid_symbol_name(name):
            raise ValueError(
                f"{label}[{idx}] invalid symbol name {name!r} "
                f"entry=0x{entry:x} name_va=0x{name_va:x}"
            )

        crc_entry = crc_start + idx * 4
        direct_crc = mem.u32(crc_entry)

        rel_delta = struct.unpack(
            "<i", struct.pack("<I", direct_crc)
        )[0]
        rel_target = crc_entry + rel_delta
        rel_crc = None
        try:
            rel_crc = mem.u32(rel_target)
        except ValueError:
            pass

        result[name] = {
            "section": label,
            "index": idx,
            "entry": entry,
            "value_va": value_va,
            "name_va": name_va,
            "namespace_va": namespace_va,
            "crc_entry": crc_entry,
            "direct_crc": direct_crc,
            "relative_crc": rel_crc,
            "relative_target": rel_target,
        }

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--kallsyms", required=True)
    ap.add_argument("--oracle", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument(
        "--full-output",
        help="Optional path for all recovered exported-symbol CRCs",
    )
    args = ap.parse_args()

    symbols, _types = load_kallsyms(args.kallsyms)
    oracle = load_oracle(args.oracle)

    base = choose_image_base(symbols, args.image)
    print(f"STOCK_IMAGE_VA_BASE=0x{base:x}")

    raw_image = Path(args.image).read_bytes()
    normal_ksymtab = symbols["__start___ksymtab"]
    raw_off = normal_ksymtab - base
    if 0 <= raw_off <= len(raw_image) - 24:
        raw_words = struct.unpack_from("<QQQ", raw_image, raw_off)
        print(
            "RAW_KSYMTAB_ENTRY0="
            + ",".join(f"0x{x:016x}" for x in raw_words)
        )

    # The stock arm64 Image carries absolute kernel_symbol pointers that are
    # initialized by R_AARCH64_RELATIVE relocations during boot.  Reuse the
    # same relocation recovery already used successfully by kallsyms-finder
    # instead of interpreting the unrelocated raw zeros as real pointers.
    finder = KallsymsFinder(
        VmlinuzDecompressor(raw_image).decompressed,
        64,
        False,
        base,
    )
    relocated_image = finder.kernel_img
    if len(relocated_image) != len(raw_image):
        raise ValueError(
            f"relocated image size changed: raw={len(raw_image)} "
            f"relocated={len(relocated_image)}"
        )

    relocated_words = struct.unpack_from("<QQQ", relocated_image, raw_off)
    print(
        "RELOCATED_KSYMTAB_ENTRY0="
        + ",".join(f"0x{x:016x}" for x in relocated_words)
    )
    if relocated_words[1] == 0:
        raise ValueError(
            "first relocated ksymtab name pointer is still zero"
        )

    mem = ImageMemory(relocated_image, base)

    exports = {}
    for spec in SECTION_SPECS:
        parsed = decode_section(mem, symbols, spec)
        overlap = set(exports).intersection(parsed)
        if overlap:
            sample = sorted(overlap)[:5]
            raise ValueError(f"duplicate exported symbols: {sample}")
        exports.update(parsed)

    print(f"STOCK_IMAGE_EXPORTED_SYMBOLS={len(exports)}")

    if args.full_output:
        full_lines = [
            "# crc\tsymbol\tsection",
        ]
        for name in sorted(exports):
            item = exports[name]
            full_lines.append(
                f"0x{item['direct_crc']:08x}\t{name}\t{item['section']}"
            )
        Path(args.full_output).write_text("\n".join(full_lines) + "\n")
        print(
            f"STOCK_IMAGE_FULL_CRC_ORACLE={args.full_output} "
            f"entries={len(exports)}"
        )

    direct_score = 0
    relative_score = 0
    present = 0

    for name, expected in oracle.items():
        item = exports.get(name)
        if item is None:
            continue
        present += 1
        if item["direct_crc"] == expected:
            direct_score += 1
        if item["relative_crc"] == expected:
            relative_score += 1

    print(f"STOCK_IMAGE_KCRC_FOUND={present}/{len(oracle)}")
    print(f"STOCK_IMAGE_KCRC_DIRECT_SCORE={direct_score}/{len(oracle)}")
    print(f"STOCK_IMAGE_KCRC_RELATIVE_SCORE={relative_score}/{len(oracle)}")

    # The exact stock IKCONFIG has CONFIG_MODVERSIONS=y and does not set
    # CONFIG_MODULE_REL_CRCS. Prefer direct CRCs, while keeping the relative
    # score as a corruption/sanity check.
    mode = "direct"
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
            actual = item["direct_crc"]
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

    print(f"STOCK_IMAGE_CRC_PRESENT={present}/{len(oracle)}")
    print(f"STOCK_IMAGE_MODULE_CRC_SCORE={score}/{len(oracle)}")
    print(
        "STOCK_IMAGE_MODULE_ABI_IDENTICAL="
        + ("1" if score == len(oracle) else "0")
    )

    Path(args.output).write_text(
        "\n".join(
            [
                f"base=0x{base:x}",
                f"mode={mode}",
                f"present={present}/{len(oracle)}",
                f"score={score}/{len(oracle)}",
                f"direct_score={direct_score}/{len(oracle)}",
                f"relative_score={relative_score}/{len(oracle)}",
                *lines,
                "",
            ]
        )
    )

    if present < 35:
        raise SystemExit(
            f"insufficient exported-symbol coverage: {present}/{len(oracle)}"
        )


if __name__ == "__main__":
    main()
