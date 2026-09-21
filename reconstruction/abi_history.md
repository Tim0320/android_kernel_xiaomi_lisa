# Lisa stock QGKI ABI reconstruction history

Target stock kernel:

- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Stock vermagic: `5.4.289-qgki-g5987d69e25da`
- Stock core ABI oracle: QGKI `msm_drm.ko` from stock `vendor_boot.img`
- Core fingerprint: 38 exported-symbol CRCs
- UFS/module fingerprint: 7 CRCs
- Exact stock IKCONFIG blob: `3343d7b7b3874e065ce4805eac61c0160c40b0a3`

> Important: percentages from different probe sets are not directly comparable. The 38-symbol core probe, 7-symbol UFS/module probe, and 17-symbol selected vendor probe measure different parts of the ABI.

## Stock Image oracle validation

The exact OS2.0.16.0.UKOCNXM stock `boot.img` was uploaded and its raw ARM64 Image was verified as:

- kernel: `5.4.289-qgki-g5987d69e25da`
- stock Image exported symbols recovered: **13,360**
- tested module-oracle symbols present in stock Image: **38 / 38**
- direct `__kcrctab` CRC matches against stock `msm_drm.ko`: **38 / 38**
- relative-CRC interpretation: **0 / 38**
- `module_layout`: stock Image `0xba39cbb8` = stock module `0xba39cbb8`
- conclusion: **the 38-symbol stock module oracle is binary-validated and authoritative for subsequent source-family comparisons**

The stock ARM64 binary uses 24-byte absolute `struct kernel_symbol` entries in the observed export tables. Their pointers are populated through ARM64 dynamic relocations, so the Image must be relocated before parsing `__ksymtab`; CRC values themselves are direct 32-bit entries because the exact stock configuration has `CONFIG_MODVERSIONS=y` and does not enable `CONFIG_MODULE_REL_CRCS`.

This validation means the historical 0/38 results for tested public source families cannot be explained by an incorrect `msm_drm.ko` oracle.

## Full stock Image vs Build #53 vmlinux ABI

The exact stock Image was compared against the `vmlinux` rows of Build #53 `Module.symvers` only. External module exports were excluded from the core comparison.

- stock Image exports: **13,360**
- reconstructed vmlinux exports: **14,031**
- symbol-name overlap: **13,257**
- CRC matches: **4,099**
- CRC mismatches: **9,158**
- stock-only symbols: **103**
- reconstructed-vmlinux-only symbols: **774**
- overlap CRC match rate: **30.92%**
- Build #53 external-module exports, tracked separately: **300**

The stock-name coverage is **13,257 / 13,360 = 99.23%**, so the dominant problem is not missing exported functionality. The dominant gap is ABI/type-signature divergence among symbols that exist in both kernels.

## ABI mismatch subsystem classification

Build #53 vmlinux exports were mapped back to the reconstructed source locations of their `EXPORT_SYMBOL*` definitions. Of the 13,257 overlapping stock/current symbols, **13,024** were mapped to source locations; **160 matching** and **73 mismatching** symbols were not mapped by the simple export-site scanner.

Top-level results:

| Area | Total mapped | Match | Mismatch | Match rate |
| --- | ---: | ---: | ---: | ---: |
| drivers | 6,266 | 1,505 | 4,761 | 24.02% |
| net | 2,269 | 394 | 1,875 | 17.36% |
| kernel | 1,141 | 731 | 410 | 64.07% |
| fs | 979 | 129 | 850 | 13.18% |
| lib | 653 | 564 | 89 | 86.37% |
| sound | 375 | 47 | 328 | 12.53% |
| mm | 363 | 136 | 227 | 37.47% |
| crypto | 298 | 90 | 208 | 30.20% |
| block | 283 | 32 | 251 | 11.31% |
| techpack | 183 | 173 | 10 | 94.54% |
| arch | 107 | 91 | 16 | 85.05% |

Strong low-match clusters include:

- `drivers/base`: 37 / 475 = **7.79%**
- `drivers/of`: 3 / 121 = **2.48%**
- `drivers/regulator`: 3 / 104 = **2.88%**
- `drivers/mmc`: 1 / 181 = **0.55%**
- `sound/soc`: 4 / 167 = **2.40%**
- `fs/buffer.c`: 1 / 58 = **1.72%**
- `fs/inode.c`: 2 / 55 = **3.64%**
- `fs/jbd2`: 1 / 51 = **1.96%**
- `mm/filemap.c`: 0 / 50 = **0%**
- `block/blk-mq.c`: 0 / 42 = **0%**
- `block/bio.c`: 0 / 32 = **0%**

Strong high-match controls include:

- `kernel/rcu`: 45 / 45 = **100%**
- `lib/xarray.c`: 32 / 32 = **100%**
- `drivers/virt`: 53 / 54 = **98.15%**
- `techpack`: 173 / 183 = **94.54%**
- `kernel/time`: 110 / 124 = **88.71%**

Interpretation: the mismatch is not a uniform whole-tree offset and is not primarily missing functionality. The pattern is consistent with a small set of shared ABI/type-definition generations (for example device, OF, VFS, page/filemap, block/bio, networking and regulator-related type graphs) contaminating thousands of exported CRCs, while several relatively independent subsystems remain close to stock.

The next diagnostic therefore targets **genksyms type dependency roots**, not individual CRCs.

## Genksyms root-type dependency ranking

A diagnostic build with `KBUILD_SYMTYPES=1` produced **1,533** `.symtypes` files. Of the 13,257 overlapping stock/current exports, **12,432** were mapped to genksyms type roots. Only **1 mismatching symbol** lacked a root mapping.

Highest-impact structural roots:

| Type root | Total dependent exports | Match | Mismatch | Mismatch rate |
| --- | ---: | ---: | ---: | ---: |
| `struct device` | 938 | 12 | 926 | 98.72% |
| `struct sk_buff` | 537 | 18 | 519 | 96.65% |
| `struct sock` | 375 | 10 | 365 | 97.33% |
| `struct net_device` | 348 | 0 | 348 | 100% |
| `struct net` | 239 | 0 | 239 | 100% |
| `struct inode` | 238 | 0 | 238 | 100% |
| `struct device_node` | 236 | 0 | 236 | 100% |
| `struct file` | 220 | 0 | 220 | 100% |
| `struct pci_dev` | 190 | 0 | 190 | 100% |
| `struct page` | 164 | 0 | 164 | 100% |
| `struct drm_device` | 158 | 2 | 156 | 98.73% |
| `struct dentry` | 128 | 0 | 128 | 100% |
| `struct request_queue` | 112 | 0 | 112 | 100% |
| `struct module` | 68 | 2 | 66 | 97.06% |
| `struct ufs_hba` | 45 | 0 | 45 | 100% |

This confirms that the 9,158 CRC mismatches are highly correlated through a relatively small number of shared type graphs. `struct device` alone participates in 926 mismatching exports.

A new high-value lead is present in the exact stock configuration: **`CONFIG_IKHEADERS=y`**. Linux embeds the build-time header archive as `kernel_headers_data ... kernel_headers_data_end` in the kernel image. Recovering that archive from the exact stock Image may expose the actual Xiaomi/Qualcomm headers used to build HyperOS, allowing direct comparison of the dominant root types instead of inferring them from public forks.

## Exact stock IKHEADERS recovered

The exact stock `boot.img` has `CONFIG_IKHEADERS=y`, and the embedded header archive was successfully recovered directly from the stock ARM64 Image.

Recovered evidence:

- `kernel_headers_data` VA: `0xffffffc01150d3e1`
- `kernel_headers_data_end` VA: `0xffffffc01186a009`
- compressed archive size: **3,525,672 bytes**
- extracted header files: **7,804**
- archive format: valid `tar.xz`

The highest-impact root-type headers are all different from the current reconstruction. Exact SHA-256 comparison:

| Header | Stock vs reconstruction |
| --- | --- |
| `include/linux/device.h` | different |
| `include/linux/fs.h` | different |
| `include/linux/mm_types.h` | different |
| `include/linux/of.h` | different |
| `include/linux/module.h` | different |
| `include/linux/skbuff.h` | different |
| `include/linux/netdevice.h` | different |
| `include/linux/blkdev.h` | different |
| `include/linux/bio.h` | different |
| `include/net/sock.h` | different |
| `include/net/net_namespace.h` | different |
| `include/scsi/scsi_device.h` | different |
| `include/drm/drm_device.h` | different |

This directly corroborates the genksyms root-type analysis. The current dominant ABI mismatch is therefore supported by binary-extracted build-time stock headers, not merely inferred from CRC patterns.

Important limitation: IKHEADERS does not necessarily contain every private driver-local header. For example `include/ufs/ufshcd.h` is absent from the recovered stock archive, so UFS-local type recovery still needs another method.

The next step is a **header-lineage fingerprint**: compare all 7,804 recovered stock headers against the previously tested Qualcomm/Xiaomi/public candidate trees and rank them by exact file identity and by critical root-type-header similarity. This is safer than copying stock headers wholesale into a source tree whose implementations may not match them.

## Header-lineage fingerprint methodology correction

The first exact-SHA lineage pass against the recovered IKHEADERS archive completed successfully but its raw identity percentages are **not valid lineage scores**.

Reason: `kernel/gen_kheaders.sh` removes all C block comments except SPDX blocks before creating `kheaders_data.tar.xz`. The stock archive is therefore comment-stripped, while the candidate source trees used raw source headers. This systematically caused false differences, including 0/19 exact matches across the critical root-type header set and overall raw exact rates near 2.8%.

The first-pass raw numbers must not be used to rank candidate source families.

The lineage workflow was corrected to:

1. reproduce the same IKHEADERS comment-removal transform on every candidate header before hashing;
2. separate generated build headers (`include/generated`, `include/config`, and arch generated headers) from source-header coverage;
3. report normalized source-header exact rate and normalized critical-root-header exact rate.

Corrected workflow commit: `ceefc4e3`.

## Exact stock header overlay and effective-config divergence

A controlled direct-genksyms experiment compared the current reconstruction against a temporary overlay of the exact stock IKHEADERS source headers.

Results:

| Mode | Present | Stock CRC matches |
| --- | ---: | ---: |
| control | 37/38 | 0/38 |
| exact stock source-header overlay | 37/38 | 0/38 |

The source-header overlay changed essentially every tested CRC, proving that the recovered stock headers participate in the ABI graph, but **source headers alone are not sufficient** to reproduce the stock CRC family.

A second root cause is now explicit in Build #53 configuration evidence. Although the runtime stock IKCONFIG contains **5,600** config entries, the reconstructed donor tree resolves it through `olddefconfig` to **5,570** entries with **92 differences**.

Important stock settings lost because the donor source/Kconfig does not preserve them include:

- `CONFIG_UFSGKI=y`
- `CONFIG_UFS_WB=y`
- `CONFIG_MI_UFS_FFU=y`
- `CONFIG_OEM_KERNEL=y`
- `CONFIG_PASSTHROUGH_SYSTEM=y`
- `CONFIG_MIGT=y`
- `CONFIG_MILLET=y`
- `CONFIG_MIUI_ZRAM_MEMORY_TRACKING=y`
- `CONFIG_QCOM_MINIDUMP_ENCRYPT=y`
- `CONFIG_QTI_TZ_LOG=y`

The donor additionally enables options absent from the stock IKCONFIG, including `CONFIG_ARM64_USE_LSE_ATOMICS=y`, `CONFIG_COMPAT_VDSO=y`, `CONFIG_RELR=y`, and related generated settings.

Therefore the current build cannot be described as using an exact effective stock configuration, even though it starts from the exact stock IKCONFIG text. The source tree's Kconfig generation changes the effective preprocessor environment used by genksyms.

The next probe overlays **all** recovered stock IKHEADERS after `prepare`, including generated/config headers, to test whether the stock generated preprocessor environment materially restores the 38-symbol CRC fingerprint.

## Full stock IKHEADERS overlay reproduces the stock core ABI

A direct-genksyms experiment isolated the missing ingredient:

| Mode | Present | Stock CRC matches |
| --- | ---: | ---: |
| control | 38/38 | 0/38 |
| stock source headers only | 38/38 | 0/38 |
| stock source + generated/config headers | 38/38 | **38/38** |

After adding `drivers/clk/clkdev.symtypes`, the previously absent `clk_get` was generated and matched exactly:

- `clk_get = 0xf8127647` stock
- `clk_get = 0xf8127647` overlay probe

All 38 core oracle symbols now reproduce the exact stock CRCs under the full exact-stock IKHEADERS environment. This includes `module_layout`, device/platform, OF, clock, regulator, IOMMU, kthread, IRQ, sysfs/kobject, page allocator, DMA and dma-buf CRCs.

This is strong experimental proof that the dominant KABI divergence comes from the **effective generated preprocessor/config environment**. It does **not yet mean the normal reconstructed kernel build is ABI-correct**: the normal build still resolves the donor Kconfig and generated headers differently. The next isolation probe tests stock generated/config headers without replacing source headers, so the minimum required stock environment can be identified before changing the reconstruction pipeline.

## Source/generated isolation result

A four-way direct-genksyms isolation probe completed successfully:

| Mode | Present | Stock CRC matches |
| --- | ---: | ---: |
| control | 38/38 | 0/38 |
| exact stock source headers only | 38/38 | 0/38 |
| exact stock generated/config headers only | 38/38 | 0/38 |
| exact stock source + generated/config headers | 38/38 | **38/38** |

The generated-only probe overlaid **2,120** stock generated/config headers while leaving all **5,686** source headers untouched; it still scored 0/38. Conversely, source-only also scores 0/38.

Therefore the stock KABI reproduction is an interaction effect: stock source-header type definitions must be interpreted under the stock generated/Kconfig preprocessor environment. Neither half reproduces the ABI independently.

The next step is to derive the **minimal source-header closure** actually consumed by the 18 direct-genksyms targets from Kbuild dependency files, then test stock generated/config headers plus only that dependency-closed source subset. This avoids treating all 5,686 source headers as required when most are unrelated to the 38-symbol core oracle.

## Minimal stock header full-build incompatibility and genksyms-only routing

The proven minimal ABI environment consists of **774** stock source headers plus **2,120** stock generated/config headers and reproduces the 38-symbol core oracle at **38/38** under direct genksyms.

A full kernel build using those 774 headers as global replacements failed because the current reconstructed donor C implementation is not source-compatible with the exact stock header API generation. Concrete failures included:

- `kernel/irq/proc.c`: donor C uses `struct proc_ops`, while the stock header set leaves it incomplete in this source context.
- `fs/erofs/internal.h`: donor code calls `vm_map_ram(pages, count, -1)`, while the stock `include/linux/vmalloc.h` declares a four-argument form.
- `mm/compaction.c`: donor code calls `lru_add_drain_cpu_zone()`, while the stock `include/linux/swap.h` does not declare that donor-side API.

Therefore the 774-header closure is an **ABI/genksyms closure**, not a drop-in full source compilation header replacement.

The next diagnostic build keeps normal donor headers for C/assembly compilation and routes only the genksyms preprocessing stage through an isolated stock ABI include tree. This can test whether a complete Image/modules/DTB build can retain the already-proven 38/38 CRC environment without breaking donor source compilation.

Important limitation: matching CRCs alone does not prove runtime structure-layout compatibility. A genksyms-only stock header route is diagnostic evidence and must not be treated as the final safe reconstruction if the underlying donor implementation layout differs from the stock implementation.

## Full build succeeds with stock ABI headers isolated to genksyms

A complete `Image modules dtbs` build succeeded while leaving normal donor headers untouched for C/assembly compilation and routing only genksyms preprocessing through the proven stock ABI header environment:

- stock source headers staged for genksyms: **774**
- stock generated/config headers staged for genksyms: **2,120**
- normal source tree replaced for compilation: **no**
- kernel/modules/DTBs: **build success**
- 38-symbol core stock ABI oracle: **38/38**
- historical 17-symbol vendor/UFS oracle: **17/17**
- tested module vermagic: **5.4.289-qgki-g5987d69e25da**

The previously mismatching UFS exports now all reproduce the exact stock CRCs, including `get_ufs_data`, `get_ufs_hba_data`, `get_ufs_sdev_data`, `ufs_get_string_desc`, `ufs_read_desc_param`, and `ufshcd_read_desc`.

This result proves that the normal donor implementation can complete a full build while genksyms is supplied with the recovered stock ABI preprocessor/type environment. It does **not** by itself prove runtime type/layout compatibility: CRC agreement can be produced by the stock genksyms view even when donor implementation headers differ. The next checks therefore expand from the 55 known oracle symbols to the full 13,360-export stock oracle and then inspect critical structure layouts separately.

## Full 13,360-export oracle after genksyms-only stock header routing

The successful full build that routes only genksyms through the recovered stock ABI environment was compared against the exact stock Image's complete **13,360-export** CRC oracle.

Results:

- stock exports: **13,360**
- current vmlinux exports: **14,032**
- overlap: **13,257**
- exact CRC matches: **12,348**
- CRC mismatches: **909**
- overlap match rate: **93.1432%**
- stock-only exports: **103**
- current-only vmlinux exports: **775**

This improves the same overlap population from Build #53's **4,099 / 13,257 = 30.9195%** to **12,348 / 13,257 = 93.1432%**.

The remaining 909 mismatches are highly concentrated:

- `net`: 646
- `drivers`: 198
- `kernel`: 30
- `fs`: 21
- `lib`: 3
- `techpack`: 3
- unmapped: 8

Largest deep groups:

- `net/netfilter`: 190
- `drivers/mmc`: 173
- `net/core`: 158
- `net/ipv4`: 118
- `net/ipv6`: 78
- `net/socket.c`: 33
- `net/xfrm`: 27
- `kernel/sched`: 25
- `net/sched`: 25
- `fs/proc`: 19

Interpretation: the 774-header stock source closure was derived only from the 18 selected core ABI targets. It is sufficient for the 38-symbol core oracle and the 17-symbol vendor/UFS oracle, but headers outside that closure fall back to donor headers during genksyms preprocessing. The concentration in networking and MMC is consistent with this limited closure.

The next experiment therefore stages the **complete stock IKHEADERS source set** (5,686 source headers plus 2,120 generated/config headers) in an isolated genksyms-only include root. Normal C/assembly compilation continues to use donor headers, avoiding the source/API incompatibilities observed when stock headers were globally overlaid.

## Complete stock IKHEADERS genksyms root reaches 99.4795%

A full kernel build using the complete stock IKHEADERS archive **only for genksyms preprocessing**, while normal C/assembly compilation continues to use donor headers, completed successfully after two unsupported translation-unit families were explicitly routed back to donor genksyms headers:

- `lib/zstd/*`
- `drivers/android/vendor_hooks.c`

Those two families previously produced 19 unversioned exports and unresolved `__crc_*` relocations at final vmlinux link. With the narrow fallback, `GENKSYMS_VERSION_FAILURES=0`.

Full stock Image oracle comparison:

- stock exports: **13,360**
- vmlinux overlap: **13,257**
- exact CRC matches: **13,188**
- CRC mismatches: **69**
- match rate: **99.4795%**
- stock-only exports: **103**
- current-only vmlinux exports: **775**

Progression on the same 13,257-symbol overlap:

- Build #53: **4,099 / 13,257 = 30.9195%**
- 774-header genksyms closure: **12,348 / 13,257 = 93.1432%**
- complete stock IKHEADERS genksyms root: **13,188 / 13,257 = 99.4795%**

All 69 remaining mismatches are mapped to source paths. Their concentration is:

- `kernel/sched`: 25
- `fs/proc`: 19
- `drivers/usb`: 16
- `lib/lz4`: 3
- `techpack` / IPA: 2
- `drivers/gpu` / KGSL: 2
- `net/qrtr`: 1
- `drivers/thermal`: 1

This pattern matches the construction of stock IKHEADERS: the archive contains `include/` and `arch/arm64/include/` headers, but not subsystem-private headers such as `kernel/sched/sched.h`, `fs/proc/internal.h`, or driver-local headers under `drivers/`, `net/`, `lib/`, and `techpack/`.

Therefore the remaining 69 symbols should be treated as a **private implementation/header lineage problem**, not a global Kconfig/header problem. The next experiment compares public Xiaomi/Qualcomm/Lisa source lineages only for the 19 translation units that own those 69 exports while retaining the exact stock global IKHEADERS environment.

## Remaining 69 private ABI symbols: public lineage matrix

A targeted matrix replaced only the private implementation/header regions that own the final 69 CRC mismatches while retaining the exact stock global IKHEADERS environment.

Best per-family matches:

- **MiCode redwood-s**
  - `kernel/sched`: **25/25**
  - `fs/proc`: **19/19**
  - KGSL: **2/2**
  - QRTR: **1/1**
- **YZzZr hyper-14**
  - USB DWC3/xHCI: **16/16**
  - TSENS: **1/1**
  - QRTR: **1/1**
- CannedShroud lisa:
  - `fs/proc`: **19/19**
  - KGSL: **2/2**
- MiCode lisa-r / taoyao-s:
  - `kernel/sched`: **25/25**
  - `fs/proc`: **18/19**
  - KGSL: **2/2**
- Lineage lisa QGKI 5.4.289:
  - `fs/proc`: **19/19**
  - KGSL: **2/2**
  - QRTR: **1/1**
  - TSENS: **1/1**
  - USB: **5/16**

Combining redwood-s for sched/proc/KGSL/QRTR with YZzZr hyper-14 for USB/TSENS covers **64/69** remaining symbols exactly.

Five symbols remain unresolved:

- LZ4: **3**
  - `LZ4_compress_default`
  - `LZ4_loadDict`
  - `LZ4_saveDict`
- IPA: **2**
  - `ipa3_get_ctx`
  - `ipa3_get_dma_dev`

The IPA score of 0/2 in the first matrix was a probe bug rather than ABI evidence: `ipa.c` is aggregated into `ipam-y` by the parent Makefile, so `ipa_v3/ipa.symtypes` had no direct Kbuild rule.

All tested Xiaomi/Lahaina candidates produced the same three incorrect LZ4 CRCs. The reconstructed tree uses a newer standalone `lib/lz4/lz4.c` implementation, while Linux/Android 5.4-era trees commonly use `lz4_compress.c + lz4defs.h`. The next probe therefore separates the final five symbols into a corrected IPA direct-genksyms test and an upstream/AOSP historical LZ4 implementation matrix.

## Final five ABI symbols resolved

The final-five matrix completed with one non-essential Lahaina IPA candidate job failing, but the target symbols themselves were fully resolved.

### IPA

Exact stock CRCs:

- `ipa3_get_ctx = 0xc7ed42a2`
- `ipa3_get_dma_dev = 0xb76b3f37`

Matches:

- MiCode `redwood-s-oss`: **2/2**
- MiCode `taoyao-s-oss`: **2/2**
- MiCode `lisa-r-oss`: **1/2**
- current reconstruction: **0/2**
- YZzZr hyper-14: **0/2**
- JiuGe new-rebase: **0/2**

### LZ4

Exact stock CRCs:

- `LZ4_compress_default = 0x4f4d78c5`
- `LZ4_loadDict = 0x749849d8`
- `LZ4_saveDict = 0x635ff76d`

Linux v5.4 reproduces all three exactly: **3/3**. AOSP android11-5.4 and android12-5.4 also reproduce **3/3**, as do the tested historical upstream Linux versions. This confirms that the stock ABI uses the older Linux-style LZ4 interface rather than the reconstructed tree's newer standalone 2023 LZ4 implementation.

Combined with the previous private-lineage matrix, every one of the final 69 mismatches now has an exact public-source donor:

- redwood-s: sched/proc/KGSL/QRTR/IPA
- YZzZr hyper-14: USB/TSENS
- Linux 5.4-style LZ4: LZ4

The next validation is a real full kernel build with these source families overlaid, followed by the complete 13,360-export stock Image CRC comparison.

## Exact vendor_boot cohort audit reduces boot-critical ABI gap to six symbols

The exact stock `vendor_boot.img` was unpacked and all **46** kernel modules were parsed from their ELF `__versions` sections.

Two distinct module ABI cohorts are present:

- **45 modules** under `lib/modules/5.4-gki/`
  - vermagic: `5.4.289-g5987d69e25da SMP preempt mod_unload modversions aarch64`
  - `module_layout = 0x1e5b7ab7`
- **1 module**, `lib/modules/msm_drm.ko`
  - vermagic: `5.4.289-qgki-g5987d69e25da SMP preempt mod_unload modversions aarch64`
  - `module_layout = 0xba39cbb8`

The root `lib/modules/modules.load` explicitly lists `msm_drm.ko`, confirming that this is the stock QGKI module relevant to the reconstructed QGKI kernel rather than the alternate 5.4-gki module cohort.

Against the exact stock Image export oracle:

- `msm_drm.ko` kernel imports: **736**
- stock Image matches: **736/736**
- current 99.4795% build matches: **730/736**
- current missing exports: **0**
- current CRC mismatches: **6**

The only QGKI boot-critical ABI mismatches are:

- `proc_create_data`
- `proc_mkdir`
- `proc_remove`
- `remove_proc_entry`
- `sched_setscheduler`
- `wake_up_process`

Exact stock vs current CRCs:

- `proc_create_data`: stock `0xa187c33a`, current `0x2f8cd0e1`
- `proc_mkdir`: stock `0xd8fd7935`, current `0xb1ea2572`
- `proc_remove`: stock `0x0420ade2`, current `0x5c1ed45a`
- `remove_proc_entry`: stock `0x05ba4e75`, current `0x9a087f14`
- `sched_setscheduler`: stock `0xe09be37d`, current `0xe92eb5f9`
- `wake_up_process`: stock `0xfa54581b`, current `0x1fc82c75`

MiCode redwood-s reproduces all six CRCs under the exact stock global IKHEADERS environment.

The four procfs mismatches correspond to a real API-generation difference: the exact stock `include/linux/proc_fs.h` uses `struct file_operations *`, while the current reconstructed common core uses the later `struct proc_ops *` API. CRC spoofing is therefore not a safe fix because the pointed-to operation structures are not runtime-layout compatible.

The next diagnostic separates redwood source files from redwood private headers for `fs/proc/generic.c` and `kernel/sched/core.c`, and inventories the current tree's proc_ops migration scope before any source-generation rollback is attempted.

## High-level status

| Probe set | Current best | Hit rate | Meaning |
| --- | ---: | ---: | --- |
| Selected vendor ABI from full Build #53 | 10 / 17 | 58.8% | MI memory, CNSS, display and touch are substantially aligned |
| Core QGKI fingerprint, normal reconstructed build | 0 / 38 | 0% | Normal donor-generated preprocessor/Kconfig environment still differs from stock |
| Core QGKI fingerprint, exact full IKHEADERS diagnostic overlay | 38 / 38 | 100% | Exact stock source + generated/config header environment reproduces all tested core CRCs |
| UFS + module fingerprint | 0 / 7 | 0% | UFS type graph and `module_layout` still differ from stock |

Known Build #53 stock matches:

- `memblock_mem_size_in_gb`
- `cnss_statistic_wow_wakeup`
- `wow_suspend_type`
- `dsi_bridge_interface_enable`
- `mi_disp_register_client`
- `mi_disp_unregister_client`
- `mi_disp_set_fod_queue_work`
- `last_touch_events_collect`
- `update_palm_sensor_value`
- `xiaomitouch_register_modedata`

Known Build #53 mismatches are concentrated in:

- `get_ufs_data`
- `get_ufs_hba_data`
- `get_ufs_sdev_data`
- `ufs_get_string_desc`
- `ufs_read_desc_param`
- `ufshcd_read_desc`
- `module_layout`

## 38-symbol core ABI history

Every row marked **valid** completed the core genksyms probe against the same stock QGKI 38-symbol oracle.

| Family | Candidate / version | Result | Rate | Status / conclusion |
| --- | --- | ---: | ---: | --- |
| Current | reconstructed `reconstruction/5.4.289-qgki` | 0/38 | 0% | valid |
| Stable | pure Android-common 5.4.289 donor `4c8fb327...` | 0/38 | 0% | valid; stable source alone is not stock |
| Xiaomi QGKI | Alioth QGKI 5.4.233 | 0/38 | 0% | valid |
| Xiaomi QGKI | Kona QGKI 5.4.233 | 0/38 | 0% | valid; same fingerprint as Alioth |
| Xiaomi QGKI + stable | Alioth QGKI merged to 5.4.289 | 0/38 | 0% | valid; core CRC family stayed effectively unchanged |
| Xiaomi QGKI + stable | Kona QGKI merged to 5.4.289 | 0/38 | 0% | valid; same conclusion as Alioth |
| Lineage | Xiaomi SM8350 lineage-22.2 | 0/38 | 0% | valid |
| Lineage | pre-5.4.289 commit `eeafe414...` | 0/38 | 0% | valid |
| Lineage | 5.4.289 merge commit `f2c008f...` | 0/38 | 0% | valid |
| Lineage | integrated 5.4.289 `bb60c832...` | 0/38 | 0% | valid |
| Qualcomm mirror | LA.UM.9.14 r1-25000.02 LAHAINA.QSSI14 | 0/38 | 0% | valid; same broad core family as Lineage/Nothing in this probe |
| Nothing | SM7325 S | 0/38 | 0% | valid |
| Nothing | SM7325 U | 0/38 | 0% | valid |
| Nothing | SM7325 V | 0/38 | 0% | valid |
| Xiaomi | SM6375 main | 0/38 | 0% | valid; distinct fingerprint |
| ACK | android11-5.4 at 5.4.289 `a85d92d...` | 0/38 | 0% | valid |
| ACK | android11-5.4-lts at 5.4.289 `a85d92d...` | 0/38 | 0% | valid; identical to android11-5.4 |
| ACK | android12-5.4 at 5.4.289 `4ca8db0...` | 0/38 | 0% | valid |
| ACK | android12-5.4-lts at 5.4.289 `4ca8db0...` | 0/38 | 0% | valid; identical to android12-5.4 |
| OEM | ASUS SM8350 Android 11 | 0/38 | 0% | valid |
| OEM | OnePlus SM8350 r06 | 0/38 | 0% | valid after neutralizing codegen-only flags |
| OEM | OnePlus SM8350 r12 | 0/38 | 0% | valid after neutralizing codegen-only flags |
| OEM | OnePlus SM8350 r14 | 0/38 | 0% | valid |
| OEM | Sony PDX214 SM8350 | 0/38 | 0% | valid after neutralizing codegen-only Polly flags |
| MiCode | `lisa-r-oss`, LA.UM.9.14 r1-16700 | 0/38 | 0% | valid |
| MiCode | `odin-r-oss`, LA.UM.9.14 r1-16700 | 0/38 | 0% | valid |
| MiCode | `vili-r-oss`, LA.UM.9.14 r1-16700 | 0/38 | 0% | valid |
| MiCode QSSI12 | `redwood-s-oss`, r1-18200 | 0/38 | 0% | valid |
| MiCode QSSI12 | `taoyao-s-oss`, r1-18300.05 | 0/38 | 0% | valid |
| MiCode QSSI12 | `zijin-s-oss`, r1-18300.05 | 0/38 | 0% | valid |

### Invalid / incomplete core probes

| Candidate | Status | Reason |
| --- | --- | --- |
| EndCredits raw MIUI base, 38-symbol baseline | incomplete | build/preparation failed in that workflow; its UFS 7-symbol probe is valid separately |
| OnePlus SM8350 15.2 in the older broad matrix | incomplete | stock IKCONFIG/toolchain preparation failed |
| Xiaomi Raphael 5.4 QGKI | incomplete | candidate clone failed |
| CLO LAHAINA history run #1 | incomplete | workflow ref resolver hit SIGPIPE under `set -o pipefail`; workflow fixed in `e2420246` |

## Distinct core fingerprint families already eliminated

These candidates are useful to group because testing more forks with the same fingerprint is low value.

| Fingerprint family | Representative `module_layout` | Members observed |
| --- | --- | --- |
| Current / EndCredits-like | `0x0816e668` | current reconstruction; EndCredits/new-rebase in 7-symbol probe |
| Xiaomi QGKI 5.4.233 | `0x02c80512` | Alioth, Kona; remained unchanged after 5.4.289 stable merge |
| Generic modern Qualcomm/Lineage | `0x758f56fc` | Lineage SM8350, Nothing SM7325, QSSI14 mirror |
| ACK Android 11 5.4.289 | `0x6bcc11cb` | android11-5.4 and android11-5.4-lts |
| ACK Android 12 5.4.289 | `0xb7a6d333` | android12-5.4 and android12-5.4-lts |
| OnePlus SM8350 | `0x23ba0f93` | r06, r12, r14 |
| MiCode LAHAINA R | `0xa0b467f6` | lisa-r, odin-r, vili-r; zijin probe also landed in this family |
| MiCode QSSI12 S | `0x7433db90` | redwood-s, taoyao-s |
| ASUS SM8350 | `0x823424ab` | ASUS Android 11 |
| Sony SM8350 | `0x63d772be` | PDX214 |

Stock target remains:

- `module_layout = 0xba39cbb8`

No tested family has matched it.

## 7-symbol UFS + module ABI history

Stock targets:

- `get_ufs_data = 0xfa507f92`
- `get_ufs_hba_data = 0xc40eabac`
- `get_ufs_sdev_data = 0xc5bbd8a8`
- `ufs_get_string_desc = 0x479d5ded`
- `ufs_read_desc_param = 0x16548413`
- `ufshcd_read_desc = 0xa93e3b58`
- `module_layout = 0xba39cbb8`

| Candidate | Result | Rate | Notes |
| --- | ---: | ---: | --- |
| current reconstruction baseline | 0/7 | 0% | valid |
| YZzZr HyperOS 14 SM8350 | 0/7 | 0% | valid |
| EndCredits ASB-2024-10-05 | 0/7 | 0% | valid |
| CannedShroud Lisa-derived | 0/7 | 0% | valid |
| JiuGeFaCai new-rebase | 0/7 | 0% | valid |
| MiCode lisa-r-oss | 0/7 | 0% | valid |
| config baseline | 0/7 | 0% | valid |
| restore-missing-stock config shape | 0/7 | 0% | valid |
| remove-generated-extra config shape | 0/7 | 0% | valid |
| strict-stock-shape config | 0/7 | 0% | valid |
| tanz `miui-t` | n/a | n/a | probe build failed |

Isolated EndCredits UFS source experiment also matched **0/6** UFS symbols.

## Android KABI structural experiments

Deterministic reserve-count scan used an unmodified control first.

Control values were reproduced exactly:

- `module_layout = 0x0816e668`
- `device_register = 0xc1e70e13`
- `device_unregister = 0xb88b5350`
- `dev_driver_string = 0x52e5afec`

Then the following were scanned:

- `struct module` reserve counts: 0, 2, 4, 6, 8
- `struct device` reserve counts: 0, 2, 4, 6, 8, 10, 12

Result: **0/4 stock matches for every valid variant**.

Conclusion: the stock difference is not explained by merely changing the number of `ANDROID_KABI_RESERVE` fields.

## Configuration experiments

Exact stock IKCONFIG is known and verified. Multiple forced/config-shape variants produced the same 7-symbol mismatches.

Conclusion:

- stock ABI mismatch is not a simple Kconfig switch;
- stock IKCONFIG contains no relevant Android KABI generation toggle that explains these CRCs;
- source/type lineage remains the primary missing factor.

## Exact Qualcomm Lahaina tag-tip results

The first native-QGKI object probe produced `MISSING` CRCs because the LTO build path did not leave the expected per-object `.symversions` files. Those apparent `0/38` values are invalid and must not be counted.

A later direct-genksyms workflow patched only the probe-side `scripts/Makefile.build` output redirection and used the kernel's own `cmd_gensymtypes_c` rule with the original candidate cflags/config. The current reconstruction control reproduced the known baseline exactly:

- `module_layout = 0x0816e668`
- `device_register = 0xc1e70e13`
- `device_unregister = 0xb88b5350`
- `dev_driver_string = 0x52e5afec`
- present symbols: **37/38** (`clk_get` is not emitted by this direct-object set)
- control marker: `DIRECT_GENKSYMS_CONTROL_OK=1`

Therefore the following Lahaina results are valid:

| Qualcomm Lahaina revision | Provenance | Result | Present | module_layout |
| --- | --- | ---: | ---: | --- |
| LA.UM.9.14.r1-18400.02-LAHAINA.QSSI12.0 | exact Qualcomm tag tip recovered as merge second parent `cc27e795...` | 0/38 | 37/38 | `0x9024fb67` |
| LA.UM.9.14.r1-18600.02-LAHAINA.QSSI12.0 | exact tag tip `846e80ab...` | 0/38 | 37/38 | `0x9024fb67` |
| LA.UM.9.14.r1-18900-LAHAINA.QSSI12.0 | exact tag tip `cda32b04...` | 0/38 | 37/38 | `0x9024fb67` |
| LA.UM.9.14.r1-19500-LAHAINA.QSSI12.0 | exact tag tip `bcf162c8...` | 0/38 | 37/38 | `0x9024fb67` |
| LA.UM.9.14.r1-19800.01-LAHAINA.QSSI12.0 | exact tag tip `5223d470...` | 0/38 | 37/38 | `0x9024fb67` |
| LA.UM.9.14.r1-20000.01-LAHAINA.QSSI12.0 | exact tag tip `72be295f...` | 0/38 | 37/38 | `0x9024fb67` |

All 37 observable CRCs were identical across 18400.02 through 20000.01. This rules out that entire QSSI12 interval as the stock Lisa core-KABI family.

Observed lower-layer generation boundaries:

- `include/linux/device.h`: unchanged from the observed 16700 snapshot through 20000.01.
- `include/scsi/scsi_device.h`: unchanged from 16700 through 20000.01.
- `include/linux/module.h`: changed between the 16700 snapshot and 18400.02, then stayed unchanged through 20000.01.
- `include/linux/android_kabi.h`: changed between 18400.02 and 18600.02.
- `lahaina_QGKI.config`: changed between 18400.02 and 18600.02.
- Despite the latter two file changes, the 37 observable core CRCs remained identical from 18400.02 to 20000.01.

## Pre-18400 Lahaina direct-genksyms results

Workflow `2f0df04c` completed successfully with a valid direct-genksyms control.

| Candidate | Provenance | Result | Present | module_layout | Interpretation |
| --- | --- | ---: | ---: | --- | --- |
| 16700 snapshot | Skywalker cumulative snapshot `58f8584f...` | 0/38 | 37/38 | `0x9024fb67` | snapshot only; unexpectedly already in the later family |
| 16900 snapshot | Skywalker cumulative snapshot `39350d27...` | 0/38 | 37/38 | `0xc20359c8` | different family; not proven exact Qualcomm tag-tip |
| 17500 snapshot | Skywalker cumulative snapshot `64fb9dc6...` | 0/38 | 37/38 | `0xc20359c8` | same as 16900 snapshot; not proven exact Qualcomm tag-tip |
| 17700 exact tag-tip | Qualcomm tag second parent `21af954d...` | 0/38 | 37/38 | `0x9024fb67` | exact; same family as all later QSSI12 tags |
| 18300 exact tag-tip | Qualcomm tag second parent `c6b805f3...` | 0/38 | 37/38 | `0x9024fb67` | exact |
| 18400.02 control | exact tag-tip `cc27e795...` | 0/38 | 37/38 | `0x9024fb67` | control reproduced known Lahaina family |

Important correction: the Skywalker 16700/16900/17500 entries are **merge snapshots**, not guaranteed exact Qualcomm tag tips. Their non-monotonic fingerprint behavior proves that snapshot results must not be used to place the Qualcomm generation boundary by themselves.

A Qualcomm vendor manifest for `LA.UM.9.14.r1-16900-LAHAINA.0` gives the exact `kernel/msm-5.4` revision:

- `203d4a97455e95f81738823edbb34b17c55fec43`

That commit is preserved in many public Qualcomm-derived mirrors, so the next probe will resolve early tag revisions from vendor manifests and fetch the exact commit by SHA.

## Manifest-exact early Lahaina results

Workflow commit `6cee2104` used Qualcomm vendor-manifest exact `kernel/msm-5.4` revisions and direct genksyms. All jobs completed the CRC stage successfully.

| Release(s) | Exact kernel revision | Result | Present | module_layout |
| --- | --- | ---: | ---: | --- |
| 15400 | `4065f0ea2f5e...` | 0/38 | 37/38 | `0x9024fb67` |
| 15500 / 15600 QSSI12 | `5ad0937ee3cc...` | 0/38 | 37/38 | `0x9024fb67` |
| 15800 | `02c90c6a7bea...` | 0/38 | 37/38 | `0x9024fb67` |
| 16100 / 16100.01 QSSI12 | `7a4b43854304...` | 0/38 | 37/38 | `0x9024fb67` |
| 16300 | `178ecd92d985...` | 0/38 | 37/38 | `0x9024fb67` |
| 16700 | `bec53eadb657...` | 0/38 | 37/38 | `0x9024fb67` |
| 16900 | `203d4a97455e...` | 0/38 | 37/38 | `0x9024fb67` |
| 17700 control | `21af954d9156...` | 0/38 | 37/38 | `0x9024fb67` |

The 17700 control reproduced the expected direct-genksyms values and emitted `EARLY_LAHAINA_CONTROL_OK=1`.

This proves the mainstream Qualcomm Lahaina core-KABI generation is stable across at least 15400 through 20000.01 and does not match stock Lisa HyperOS QGKI.

The earlier `0xc20359c8` values from Skywalker 16900/17500 snapshots were fork-state artifacts, not Qualcomm tag-tip ABI generations.

## Current active direction

The next useful boundary is **pre-18400 Lahaina**, not later QSSI12/QSSI14 forks.

Candidates now prioritized:

| Lahaina revision | Provenance |
| --- | --- |
| 16700 | preserved merge snapshot in `Skywalker-I005/Skywalker-ZS673KS` |
| 16900 | preserved merge snapshot `39350d27...` |
| 17500 | preserved merge snapshot `64fb9dc6...` |
| 17700 | exact Qualcomm tag tip recovered as second parent `21af954d...` |
| 18300 | exact Qualcomm tag tip recovered as second parent `c6b805f3...` |
| 18400.02 | exact tag-tip control, known family `module_layout=0x9024fb67` |

The objective is to locate the generation transition before 18400 and determine whether any earlier Lahaina QGKI baseline matches or approaches the stock Lisa CRC family.

## Working conclusion

Evidence so far strongly rules out all of these as the direct stock core-KABI source:

1. pure Android common 5.4.289;
2. Xiaomi public Lisa R source by itself;
3. Xiaomi public QSSI12 S source;
4. public Xiaomi QGKI 5.4.233 plus Linux 5.4.289 stable;
5. standard ACK Android 11/12 KMI generations;
6. common Lineage/Nothing modern Qualcomm 5.4 trees;
7. ASUS/OnePlus/Sony same-generation OEM trees;
8. configuration-only or reserve-count-only explanations;
9. exact Qualcomm Lahaina QSSI12 tag tips from 18400.02 through 20000.01.

The remaining evidence points toward an earlier Qualcomm/Xiaomi QGKI core generation or a Xiaomi-private KABI/type delta carried forward to the stock HyperOS 5.4.289 kernel.
