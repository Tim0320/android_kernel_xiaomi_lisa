# Lisa stock QGKI ABI reconstruction history

Target stock kernel:

- Device: Xiaomi 11 Lite 5G NE (`lisa`)
- Stock vermagic: `5.4.289-qgki-g5987d69e25da`
- Stock core ABI oracle: QGKI `msm_drm.ko` from stock `vendor_boot.img`
- Core fingerprint: 38 exported-symbol CRCs
- UFS/module fingerprint: 7 CRCs
- Exact stock IKCONFIG blob: `3343d7b7b3874e065ce4805eac61c0160c40b0a3`

> Important: percentages from different probe sets are not directly comparable. The 38-symbol core probe, 7-symbol UFS/module probe, and 17-symbol selected vendor probe measure different parts of the ABI.

## High-level status

| Probe set | Current best | Hit rate | Meaning |
| --- | ---: | ---: | --- |
| Selected vendor ABI from full Build #53 | 10 / 17 | 58.8% | MI memory, CNSS, display and touch are substantially aligned |
| Core QGKI fingerprint | 0 / 38 | 0% | Core/device/platform/OF/IOMMU/DMA/module KABI still differs from stock |
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
