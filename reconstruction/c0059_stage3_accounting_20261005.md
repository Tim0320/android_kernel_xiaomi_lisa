# Candidate0059 Stage3 active package-runtime accounting

Stage3 advances the Android16 performance repair from storage/lifecycle plumbing into real package runtime accounting.

It is intentionally bounded. It activates the split-WALT `update_pkg_load()` path from Stage2 and maintains task/user cluster runtime counters in the KABI-safe external state introduced by Stage1.

## Included

- strong `pkg_enable()`, `update_pkg_load()`, and `package_runtime_monitor()`;
- capacity-ordered LITTLE/MID/BIG cluster map for Lisa's three-cluster CPU topology;
- task and owning-user FRONT/BACK plus per-cluster cumulative accounting;
- history-slot advancement;
- weak `migt_hook()` landing point so the later MIGT implementation can replace it without rewriting WALT again.

## Explicitly not included

Stage3 does not expose `/dev/migt` or `/dev/metis`, does not register MIGT ioctls, does not force CPU frequency, does not change thermal policy, does not add cpuset overrides, and does not create `/dev/iorap_dev`.

A Stage3 compile PASS means the real package accounting source builds against exact pinned Lisa with Stage1+Stage2. It does not prove Android16 jank is fixed.

Next after PASS: port the stock-lineage MIGT task monitor / scheduler layer against this pointer-backed state, then compile it before considering the device-facing MIGT driver.
