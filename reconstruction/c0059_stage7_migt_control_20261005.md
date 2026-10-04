# Candidate0059 Stage7 bounded legacy MIGT control

Stage7 restores the legacy Xiaomi `migt` miscdevice only after Stage6 made its
QUEUE/DEQUEUE render state real.

The donor's userspace contract is unusual: the driver dispatches on
`_IOC_NR(cmd)` and has three command numbers:
- 1: QUEUE_BUFFER
- 2: DEQUEUE_BUFFER
- 3: SET_CEILING

The donor ignores the ioctl payload. Candidate0059 keeps the number-based
dispatch so existing legacy userspace can reach the same command identities,
but it does not preserve the donor's unsafe default-success behavior.

Implemented now:
- QUEUE_BUFFER updates real Q-render state and resets stale render identities
  when the traced UID changes.
- DEQUEUE_BUFFER updates real DQ-render state.
- the device identity is exactly `migt`.
- exact `migt_init` is registered with `late_initcall`.

Deliberately not claimed:
- SET_CEILING returns `-EOPNOTSUPP` until its real frequency ceiling policy is
  ported.
- unknown ioctl numbers return `-ENOTTY`.
- no cpufreq notifier, core_ctl boost, thermal change, Metis alias, or iorap
  shim is present.

A Stage7 compile PASS therefore means the legacy control surface exists with
truthful bounded behavior; it does not mean stock MIGT boost is complete or
Android16 jank is fixed.
