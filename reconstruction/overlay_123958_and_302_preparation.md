# Lisa: 123958 overlay capture, author suffix, and 5.4.302 preparation

## Scope and build distinction

This is a read-only device-evidence review and a queued naming change. It does not change the currently running kernel build, flash a phone, or claim a graphics repair.

The user explicitly says Candidate0057 is not yet installed. Treat the new capture as the existing pre-0057 device baseline, not a regression test of 0057. The version still reports the old 5.4.289-qgki-g5987d69e25da string; that old string alone cannot uniquely identify a candidate. The preceding 121508 evidence and user report identify the battery-working baseline as 0056.

Private input: lisa-graphics-camera-20261004-123958-overlay_bad.zip.
SHA256: f1e183ab0ce3746ffd406dc87ed5dfd62bdb281bf92ce979e2261987f5de74e2.
Raw device logs and screenshot are NOT included in this public note. The line numbers below refer to the original archive members decoded to UTF-8, preserving their text line boundaries.

At the first current check, Run37177089277 / commit fdf1a54 was in progress at step10 Build and package; validation and final boot upload were pending. Always re-read Actions before reporting current status. Early artifact11293103376 is ONLY source review (ZIP SHA256 d3709e7f6dfc10ded39abafdcd4c065b1e79f15a6d99e7e91e8d3d8bbcb945dc), not a boot release.

## Concrete graphics observations

SurfaceFlinger was captured at 12:39:59.025-12:39:59.193 (+08:00). The subsequent files and screenshot are sequential, not a frame-atomic capture.

| Evidence | Observation |
|---|---|
| surfaceflinger.txt:1491-1497 | Display on, 1080x2400, active90Hz, 60/90Hz modes listed |
| surfaceflinger.txt:1506-1507 | usesDeviceComposition=true, usesClientComposition=false |
| surfaceflinger.txt:1543-1640 | Five visible output layers, all DEVICE: wallpaper, launcher, screen-recorder floating layer, status bar, navigation bar |
| surfaceflinger.txt:754-768 | Floating layer #687: 470x128, PREMULTIPLIED alpha, plane alpha1.0, isOpaque=false, sRGB, backgroundBlurRadius=0, selfBlurRadius=0 |
| surfaceflinger.txt:1584-1602 | Floating output rectangle [590,1702,1060,1830], source470x128, DEVICE composition |
| surfaceflinger.txt:1822-1826 | HWC reports wallpaper RGBX_8888_UBWC and other four layers RGBA_8888_UBWC |
| surfaceflinger.txt:1861-1865 | All five layers assigned SDE pipes; floating layer pipe87, allocated512x128, cropped470x128 |
| surfaceflinger.txt:1881-1886 | Floating buffers have2048-byte stride, compressed=true; matching512-pixel allocation width for4-byte RGBA |
| surfaceflinger.txt:2415-2432 | Layer#687 belongs to the screen-recorder application overlay, window type2038 |
| graphics_properties.txt | vendor.gralloc.disable_ubwc=0; background blur support enabled |

These values narrow the next experiment to hardware composition of compressed alpha layers. They do NOT prove a bad stride, a broken UBWC implementation, an incorrect alpha mode, or a faulty panel. Padding from470 to512 pixels is consistent between allocator and HWC; do not 'fix' it by forcing packed470-pixel rows. Plane alpha1.0 does not make a premultiplied per-pixel-alpha layer opaque.

The floating layer's blur radius is zero in this snapshot. Therefore the earlier general suspicion of a SurfaceFlinger background-blur pass is not the leading explanation for this captured frame. App rendering, transient state and other frames are not ruled out.

The PNG contains the recorder overlay and readable desktop; inspection does not expose an unambiguous pixel-corruption pattern to identify the exact bug. This does not disprove the user's report on the physical display. AOSP screenshot composition uses a separate capture output/RenderEngine path and is not a readback of every physical SDE plane. Timing also differs from the SurfaceFlinger dump.

recent_logcat.txt has9 unknown-gralloc-dataspace messages, but0 Invalid present fence,0 PostBlend,0 Fatal matches in this limited capture. Do not transplant counts from the older121508 file. The active floating layer has resolved sRGB metadata, so the generic warning alone is not a root cause.

Some sysfs reads were denied (display nodes and gpuclk); gmem_size path was absent. Consequently live node permissions, hardware registers and GPU memory-layout capabilities are not fully established. Never infer they are absent/zero from collection failure.

## Camera and Wi-Fi observations

camera.txt:4-10: eight enumerated devices, three normal/API1-visible devices, no active client at capture. camera.txt:14-38 records repeated camera1 face sessions including12:39:22 connect and12:39:23 disconnect; torch on/off events at12:19:21/23. camera.txt:25345 reports Camera error traces (0). This supports successful prior service sessions, not full still-photo/video/physical-torch validation.

modules.txt has the battery module loaded; wlan_state.txt does not list wlan0, and the loaded-module snapshot lacks the WLAN/CNSS/HWID driver chain. This independently supports Wi-Fi being unavailable, but does not replace the earlier actual loader-error evidence. /proc/modules not listing camera is consistent with the old built-in-camera baseline; it does not prove camera is absent.

## Author suffix: prepared, not inserted into the running build

User-requested UTS format:
`{linux_base}-qgki-lisa-c{candidate}-r{package_sha7}-by-Tim0320`

Keep Tim0320@lisa-ci and real build time as well. Use ASCII in the UTS release; describe it to users as made by Tim0320. The displayed base version must reflect integrated code, not just a changed Makefile/banner.

See build_identity_policy.json and patches/c0057-tim0320-suffix.pending.patch. Against the actual0057 source-review artifact, syntax, git apply --check, temporary-copy application,43-byte release length, five invalid-SHA rejection cases and unchanged ASTs of all other functions passed. No kernel compilation with this suffix is claimed.

Do not cancel Run37177089277 solely for this label. Apply on the next required rebuild after refreshing sources; if an actual0057 blocker requires a new run, include the tested suffix there. If the candidate changes, update its identifier rather than reusingc0057. Keep module loader, MODVERSIONS and CFI checks unchanged, and verify final Image/boot/manifest consistency.

## 5.4.302: preliminary study only

The official upstream5.4.302 release is commit9e3157c56ec7917e6a80ea53a8bd752e0037f2cb, dated2025-12-03. The changelog explicitly marks it the last upstream5.4.y release and end-of-life. It is a valid requested compatibility milestone, not a currently maintained security endpoint.

Already confirmed: this project uses selected files from the pinned LineageOS5.4.302 donor46af56554ec50e3ff3752858bf38eaeeb852ca0d on a5.4.289 base. Selected donor overlays do not mean the entire kernel is already5.4.302. Do not replace all Xiaomi/Qualcomm vendor trees with a generic/AOSP donor.

Proposed isolated upgrade procedure, NOT yet executed:
1. Freeze a device-tested5.4.289 baseline, exact build recipe/toolchain/config, all loaded vendor module versions and boot bytes.
2. Compare all stable changes5.4.290..5.4.302 against the actual Android/Qualcomm tree, distinguishing already-backported changes from missing patches. No complete diff inventory or conflict-resolution count is claimed yet.
3. Integrate in a dedicated upgrade branch; retain functional vendor hooks, UFS registry, typed battery providers, procfs compatibility and module ownership. Audit fields/callbacks and calling conventions, not only exported symbol names/CRCs.
4. Re-evaluate existing source-hash pins and source-pattern patches consciously. Pin failures must not be bypassed. Keep the current compiler first to separate source-update regressions from toolchain changes.
5. Rebuild and verify real release provenance, all vendor-import ABI contracts, structures used by display/camera/WLAN, BPF, protected-memory/CFI settings, boot layout and module loading paths. Update the reported version only with real integration.
6. Device tests: repeated boot, charging telemetry, Wi-Fi scan/connect/reconnect, overlays60/90Hz, screenshot versus panel, camera/video, AOD/suspend/resume and thermal behavior. Build success alone is not a pass.

Graphics experiment priority after0057 device validation: compare the same floating overlay using verified DEVICE versus CLIENT composition; then separately test compressed versus uncompressed buffers only with an identified supported control. Capture actual composition/format at each step and restore settings. No remote toggle or permanent disable-UBWC/disable-HWC change was made here. No unrelated ABI/power changes should be bundled into this experiment.

## Primary references consulted

- Official stable5.4.302 changelog: https://cdn.kernel.org/pub/linux/kernel/v5.x/ChangeLog-5.4.302
- AOSP stable kernel release/update guidance: https://source.android.com/docs/core/architecture/kernel/releases
- AOSP ABI monitoring: https://source.android.com/docs/core/architecture/kernel/abi-monitor
- Kernel driver ABI limitations: https://docs.kernel.org/process/stable-api-nonsense.html
- AOSP HWC requirements (alpha, format, tiling, stride): https://source.android.com/docs/core/graphics/implement-hwc
- AOSP Android14 SurfaceFlinger capture implementation: https://android.googlesource.com/platform/frameworks/native/+/refs/heads/android14-release/services/surfaceflinger/SurfaceFlinger.cpp (blobdb205b8a9518e1170f7265231df5e5e0351a7a32; renderScreenImpl / ScreenCaptureOutput)

## Scheduler handoff

Keep the same hourly Lisa task and existing per-run2/2/5-minute observer. Re-read build/verify/upload state; failure means inspect and repair the first actual blocker, not bypass gates. Separate documentation commit IDs from actual boot build commits. Pending work: finish0057, activate author suffix on next necessary compilation, investigate the now-observed DEVICE/UBWC-alpha path, and continue only the preparatory302 comparison until the stable baseline is validated. Do not classify this archive as a0057 device test. Do not publish raw private logs or screenshots.
