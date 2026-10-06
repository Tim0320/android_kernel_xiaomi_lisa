#!/usr/bin/env python3
from pathlib import Path

import candidate_0061_batch_a_manual as batch_a
import candidate_0061_batch_b_manual as batch_b


def once(s: str, old: str, new: str, label: str) -> str:
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: anchor count={n}")
    return s.replace(old, new, 1)


def ensure_once_after(s: str, anchor: str, addition: str, label: str) -> str:
    if addition in s:
        return s
    return once(s, anchor, anchor + addition, label)


def adapt_makefile(root: Path):
    p = root / "Makefile"
    s = p.read_text()

    # Final release identity. Never reuse the retired Batch-B 292->296-only adapter.
    for old in ("SUBLEVEL = 289\n", "SUBLEVEL = 292\n", "SUBLEVEL = 296\n", "SUBLEVEL = 299\n"):
        if old in s:
            s = s.replace(old, "SUBLEVEL = 302\n", 1)
            break
    if "SUBLEVEL = 302\n" not in s:
        raise RuntimeError("Direct-302 Makefile: cannot establish SUBLEVEL=302")

    # Stable C endpoint: propagate CLANG_FLAGS through preprocessor flags while
    # preserving Lisa's downstream Clang-11 target/prefix/no-integrated-as setup.
    old = "KBUILD_CFLAGS\t+= $(CLANG_FLAGS)\nKBUILD_AFLAGS\t+= $(CLANG_FLAGS)\n"
    if old in s:
        s = s.replace(old, "KBUILD_CPPFLAGS\t+= $(CLANG_FLAGS)\n", 1)
    elif "KBUILD_CPPFLAGS\t+= $(CLANG_FLAGS)\n" not in s:
        raise RuntimeError("Direct-302 Makefile: CLANG_FLAGS propagation anchor missing")

    # Stable B endpoint: suppress warning added by newer clang, without importing
    # MiYume's newer LLVM plumbing or custom optimization policy.
    warning = "KBUILD_CFLAGS += $(call cc-disable-warning, default-const-init-unsafe)\n"
    if warning not in s:
        anchors = [
            "KBUILD_CFLAGS += $(call cc-disable-warning, undefined-optimized)\n",
            "KBUILD_CFLAGS += -Wno-tautological-compare\n",
        ]
        for anchor in anchors:
            if anchor in s:
                s = s.replace(anchor, anchor + warning, 1)
                break
        else:
            raise RuntimeError("Direct-302 Makefile: warning insertion anchor missing")

    # Stable B endpoint.
    builtin = "KBUILD_CFLAGS += -fno-builtin-wcslen\n"
    if builtin not in s:
        anchor = "KBUILD_CFLAGS\t+= $(call cc-option,-fmacro-prefix-map=$(srctree)/=)\n"
        if anchor not in s:
            raise RuntimeError("Direct-302 Makefile: fmacro-prefix-map anchor missing")
        s = s.replace(anchor, builtin + "\n" + anchor, 1)

    # Stable A endpoint: use clang's linker path for userspace helper links.
    userld = "KBUILD_USERLDFLAGS += $(call cc-option, --ld-path=$(LD))\n"
    if userld not in s:
        anchor = "KBUILD_LDFLAGS += $(KCPPFLAGS)\n"
        if anchor in s:
            s = s.replace(anchor, anchor + userld, 1)
        else:
            # Upstream places this near final user flags; keep Lisa layout and add
            # immediately before the first scripts/Makefile.* include as a safe,
            # toolchain-local insertion point.
            marker = "include scripts/Makefile.kasan\n"
            if marker not in s:
                raise RuntimeError("Direct-302 Makefile: userld insertion anchor missing")
            s = s.replace(marker, userld + "\n" + marker, 1)

    p.write_text(s)


def adapt(root: Path, path: str, target_ref: str, target_blob, reviewed_segments):
    segments = tuple(reviewed_segments)

    if path == "Makefile":
        adapt_makefile(root)
        return "DIRECT_302_MAKEFILE"

    # Reuse historical reviewed adapters only when the path is affected by that
    # single provenance segment. Multi-segment paths need a Direct-302 endpoint
    # adapter so later stable semantics cannot be silently skipped.
    if segments == ("A",) and batch_a.MANUAL.get(path) == "ADAPT":
        batch_a.adapt(root, path, target_ref, target_blob)
        return "REUSED_BATCH_A_ADAPTER"

    if segments == ("B",) and batch_b.MANUAL.get(path) == "ADAPT":
        batch_b.adapt(root, path, target_ref, target_blob)
        return "REUSED_BATCH_B_ADAPTER"

    raise RuntimeError(
        f"{path}: reviewed Direct-302 ADAPT decision exists but source adapter "
        f"is not implemented yet (segments={','.join(segments)})"
    )
