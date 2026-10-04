# Candidate0059 Stage5 passive GLK/game-load layer

Stage5 restores the stock-lineage `kernel/sched/glk.c` landing point and exact `game_load_init` identity after the Stage4 MIGT scheduler/statistics layer.

The port is deliberately passive. It provides per-CPU runtime/history accounting and the `game_load_update`, `game_load_history_update`, and `game_load_reset` APIs required by the later MIGT control layer.

It does **not** port GLK frequency policy yet. In particular there is no `glk_freq_limit`, no cpufreq policy rewriting, no core_ctl boost, no thermal change, no cpuset override, no `/dev/migt`, no Metis alias, and no iorap shim.

This split prevents a dangerous false-positive state where a later MIGT driver links against no-op frequency APIs and appears functional even though the policy is missing.

A Stage5 compile PASS means the passive game-load source and exact `game_load_init` initcall compile against the exact Lisa source after Stages1-4. It is not Android16 runtime proof.

Next after PASS: Stage6 must review the actual legacy `/dev/migt` ioctl contract and only port the device-facing control pieces whose dependencies can be mapped safely to Lisa. Metis remains a separate ABI.
