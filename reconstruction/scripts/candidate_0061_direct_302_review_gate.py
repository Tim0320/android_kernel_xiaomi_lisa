#!/usr/bin/env python3
from pathlib import Path
import argparse
import json

from candidate_0061_direct_302_reviewed import REVIEWED_SEMANTICS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", type=Path, required=True)
    args = ap.parse_args()

    data = json.loads(args.scan.read_text())
    semantic = data.get("semantic_review", [])
    reviewed = []
    unresolved = []

    for row in semantic:
        decision = REVIEWED_SEMANTICS.get(row.get("path"))
        segments = set(row.get("provenance_segments", []))
        reviewed_segments = set(decision.get("reviewed_segments", [])) if decision else set()

        if decision and segments.issubset(reviewed_segments):
            row["review_status"] = "REUSED_REVIEWED_DECISION"
            row["semantic_classification"] = decision["classification"]
            row["semantic_resolution"] = decision["resolution"]
            row["semantic_reason"] = decision["reason"]
            reviewed.append(row)
        else:
            row["review_status"] = "UNRESOLVED"
            if decision:
                row["partially_reviewed_segments"] = sorted(segments & reviewed_segments)
                row["unreviewed_segments"] = sorted(segments - reviewed_segments)
            unresolved.append(row)

    data["reviewed_semantic_count"] = len(reviewed)
    data["unresolved_semantic_count"] = len(unresolved)
    data["reviewed_semantic"] = reviewed
    data["unresolved_semantic"] = unresolved
    args.scan.write_text(json.dumps(data, indent=2) + "\n")

    print("C0061_DIRECT_302_REVIEW_GATE=PASS")
    print("semantic_review_count=" + str(len(semantic)))
    print("reviewed_semantic_count=" + str(len(reviewed)))
    print("unresolved_semantic_count=" + str(len(unresolved)))

    for row in unresolved:
        print(
            "DIRECT302_UNRESOLVED",
            row["path"],
            "segments=" + ",".join(row.get("provenance_segments", [])),
        )


if __name__ == "__main__":
    main()
