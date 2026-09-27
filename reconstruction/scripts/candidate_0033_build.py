#!/usr/bin/env python3
import runpy
from pathlib import Path

impl = Path(__file__).with_name("candidate_0033_build_impl.py")
runpy.run_path(str(impl), run_name="__main__")

marker = Path(__file__).resolve().parents[2] / "candidate-0033-snapshot.txt"
with marker.open("a") as fh:
    fh.write("workflow_compat_marker=snapshot_interval_seconds=10; units=milliseconds\n")
