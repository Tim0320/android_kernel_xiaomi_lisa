# Candidate0061 repaired IPA/PAS ABI provenance

Date: 2026-10-07
Integrated run: `37571737761`
Build commit: `803b05f1932d3109f7ec1f4f301c20f911de167d`

## Reconstruction gate

The repaired Candidate0059 source reconstruction emitted:

- `C0061_C0059_IPA_PAS_INHERITANCE=PASS`
- `C0059_INHERITED_SOURCE_STACK_RECREATED=PASS`

The repair replays only the pinned Candidate0046 prerequisites plus the Candidate0053 IPA/PAS endpoints needed by the real Candidate0059 lineage. It does not revive Batch C/D builds and does not wholesale copy a donor kernel.

Classification: `MIXED_CONFLICT` because Lisa/Yupik runtime semantics are preserved while the official 5.4.289 -> 5.4.302 stable delta remains the base materialization.

## Direct-302 gate

- semantic review: 34 / 34
- unresolved: 0
- source identity: 5.4.302
- Candidate0059 removed ABI symbols: 0

## ABI/KMI result

Exact result from `candidate-0061-integrated-abi.json`:

- changed CRC: 5
- removed symbols: 0
- added symbols: 11

### Changed symbols

All five changed CRCs are the already-reviewed official stable xHCI delta:

- `xhci_dbg_trace`
- `xhci_ext_cap_init`
- `xhci_gen_setup`
- `xhci_resume`
- `xhci_suspend`

Provenance: official Linux stable Segment A / previously reviewed stable ABI delta.

### Added symbols

Segment A stable provenance:
- `flow_rule_match_ports_range`
- `page_get_link_raw`
- `tasklet_setup`

Segment B stable provenance:
- `snd_pcm_runtime_buffer_set_silence`

Segment C stable provenance:
- `scsi_scan_host_selected`
- `tcf_action_update_stats`

Segment D stable provenance:
- `__irq_apply_affinity_hint`
- `irq_force_affinity`
- `irq_set_affinity`
- `l2cap_chan_hold`

Reviewed Candidate0059 compatibility provenance:
- `qcom_scm_get_download_mode`

`lisa_mtdoops_checkpoint` is no longer target-only added in this repaired run because the corrected Candidate0059 control reconstruction now contains the inherited mtdoops/IPA checkpoint layer. This is expected and is evidence that the C0059 source contract is more faithful than the retired run 37513703360.

## Packaging result

- kernel release: `5.4.302-qgki-lisa-c0061-r803b05f-by-Tim0320`
- Image SHA256: `5b3bd0f7e12ee729da7c83b78909c90696cfc22ef5a9b543224c7b8ceec84e3f`
- boot.img SHA256: `ffcad0916bd53d17d6c8bd8f336dab878a2862404846e390fc00c7bb48bb38e7`
- boot artifact: `11462052521`
- boot artifact name: `lisa-c0061-5.4.302-static-verified-pending-device-a1`

This repaired artifact replaces retired artifact `11437434497` for Phase 10 device validation.
