# Candidate0061 Windows + WSL2 offline analysis workstation

Status: **READ-ONLY ANALYSIS, NOT FLASHABLE**. A Windows PC can prepare evidence, compare module ABI and AVB descriptors and create test artifacts, but it cannot replace OEM signing authority, provide device rollback attestation, or prove a guarded NFC module was actually loaded.

## Environment
- Windows 10/11 with WSL2 Ubuntu and adequate free disk space. Use PowerShell (Administrator) once: `wsl --install -d Ubuntu`, then reboot if prompted.
- Ubuntu: `sudo apt update && sudo apt install -y git git-lfs python3 python3-venv unzip zip file binutils jq e2fsprogs erofs-utils`.
- Git clone inside the **WSL Linux filesystem** (`~/src`), not `/mnt/c` for big kernel builds. `git lfs install`; `git clone https://github.com/Tim0320/android_kernel_xiaomi_lisa.git`; `cd android_kernel_xiaomi_lisa && git lfs pull`.
- Verify real 8192/4096-byte stock vbmeta payloads: `python3 reconstruction/scripts/c0061_stock_vbmeta_lfs_audit.py reconstruction/stock/stock-Image-3.09/vbmeta.img reconstruction/stock/stock-Image-3.09/vbmeta_system.img`.
- This program reports header/descriptor/rollback **metadata only** with signature_verified/device_rollback_verified/flash_authorized all false; it cannot authorize partition writes.
- WSL2 for read-only `avbtool info_image --image ...` (when avbtool is available), `dump.erofs` read-only inspection, `modinfo`, `readelf`, checksum comparisons and image-building tests. Building/signed vendor_a requires further OEM AVB/rollback and entire dependent module-set gates.
- Windows PowerShell remains the simplest way to interact with TWRP `adb get-state` returning `recovery`; do **not** require Android `device`, and never use `adb push /vendor` or write vendor_a EROFS.
- Private TWRP ZIPs, raw partitions, and user data must be kept off the public repository. Use Windows directory `D:\\1.ROM_Prot\\lisa\\pull_log` only for local collection/inspection.
- The already-built C0061 `nfc_i2c.ko` cdev guard is not installed on the handset. Boot-only reflashing cannot deliver it; do not flash prior prototype ZIP.
- Do not disable AVB, vbmeta verification, SELinux, thermal or lock CPU clocks to bypass a gate.

## Offline success criteria before considering a test
1. Confirm `vendor_modprobe.sh` first unblocked QGKI probe from the real device module `modules.load`, `modules.blocklist`, `modules.dep` and map the selected **whole batch** versus 5.4-gki fallback, not one NFC file.
2. Confirm the module ABI/imported symbol CRC matching the exact kernel build, and actual intended load stage (vendor or first-stage ramdisk).
3. Verify actual signed vbmeta/vbmeta_system/vbmeta footer/chain descriptors and real device rollback constraints, plus per-slot stock backup hashes and a recovery strategy.
4. Only after independently reviewable signed/reversible paired package and tests exist consider a single user physical boot test. The current status is **BLOCKED_NOT_FLASHABLE**.

## Windows + WSL2 MCP gateway (2026-10-11)
- Local installation kit: `Lisa-C0061-Windows-WSL2-MCP-Kit.zip` delivered separately to the operator; **it is not stored in GitHub**. Never assume Windows installation or TCP handshake passed until local tests report success.
- MCP transport A (recommended when networking fails): the Windows MCP client starts `wsl.exe -d Ubuntu -- bash -lc 'exec "$HOME/.local/share/lisa-c0061-mcp/start-stdio.sh"'`. Linux-only STDIO servers can be launched this way without Windows-native executables.
- MCP transport B: the WSL2 Python SDK 2.3.0 workstation serves `http://127.0.0.1:8765/mcp` over TCP-based Streamable HTTP; test both Windows TCP and a **real MCP initialize/list-tools handshake** before claiming working connectivity.
- External Linux-only STDIO MCP servers may be exposed on a separate localhost port using a trusted `mcp-proxy` binary. The proxy release 0.13.0 requires MCP SDK <2: install in its **own** venv, not alongside the gateway SDK v2.
- Default exposed tools: bounded read of local Plan/State, recent public Actions metadata, allowlisted repository text, local evidence ZIP filenames/hashes, always-fail-closed preliminary flash gate, and controlled local-only State preview. No arbitrary execution, GitHub push, partition flash, or OEM signing tool is exposed.
- Opt-in local State write must verify the exact Git HEAD and clean State file. Codex can modify sources using its **separately approved local workspace capability**, never because of an implicit MCP privilege escalation. Private TWRP archives must remain local.
- Current verified CI: Direct-302 integrated build run [38112707005](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38112707005) SUCCESS with static artifact 11692514228. Repaired audit run [38118610699](https://github.com/Tim0320/android_kernel_xiaomi_lisa/actions/runs/38118610699) SUCCESS, `VERIFIED_STATIC_CI=SUCCESS`, `DEVICE_RUNTIME=UNVERIFIED`. **No paired verified Boot + NFC module deployment exists yet; no flash authorization.**
- References: https://learn.microsoft.com/en-us/windows/wsl/networking ; https://github.com/modelcontextprotocol/python-sdk ; https://github.com/sparfenyuk/mcp-proxy ; https://developers.openai.com/learn/docs-mcp
