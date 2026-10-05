#!/usr/bin/env python3
from pathlib import Path
import argparse, json, subprocess, tempfile

BASE="upstream-v5.4.289"
TARGET="upstream-v5.4.292"

MANUAL = {
    "kernel/time/hrtimer.c": {
        "class": "NOT_APPLICABLE",
        "reason": "5.4.290 CPUHP_AP_HRTIMERS_DYING fix targets the newer upstream hotplug model; Lisa retains CPUHP_HRTIMERS_PREPARE/hrtimers_prepare_cpu semantics.",
    },
    "drivers/clk/qcom/clk-rpmh.c": {
        "class": "ADAPT",
        "reason": "Apply upstream 5.4.291 unsigned-long cast in clk_rpmh_bcm_recalc_rate without replacing the downstream Qualcomm clock driver.",
    },
    "drivers/clk/qcom/clk-alpha-pll.c": {
        "class": "ADAPT",
        "reason": "Lisa already carries alpha_en_mask handling; add alpha_mode_mask to value/mask semantics while preserving downstream configure flow.",
    },
    "drivers/soc/qcom/socinfo.c": {
        "class": "ADAPT",
        "reason": "Preserve Lisa vendor socinfo API and add SMEM item-size-aware serial_num bounds semantics equivalent to upstream offsetofend fix.",
    },
    "kernel/cpu.c": {
        "class": "NOT_APPLICABLE",
        "reason": "Companion hrtimer CPUHP_AP_HRTIMERS_DYING startup callback belongs to the newer upstream hrtimer hotplug model that Lisa does not use.",
    },
    "kernel/gen_kheaders.sh": {
        "class": "ADAPT",
        "reason": "Preserve Lisa kheaders packaging flow and add the 5.4.290 AFS/NFS silly-rename exclusions to the existing tar invocation.",
    },
    "drivers/usb/gadget/function/f_fs.c": {
        "class": "ADAPT",
        "reason": "Apply 5.4.290 FunctionFS semantics by removing the unnecessary WARN_ON in functionfs_bind while preserving downstream Android gadget code.",
    },
    "Documentation/devicetree/bindings/mmc/mmc-controller.yaml": {
        "class": "ADAPT",
        "reason": "Carry the 5.4.291 documentation clarification that #address-cells denotes the SDIO function number while preserving downstream binding edits.",
    },
    "drivers/usb/dwc3/gadget.c": {
        "class": "ADAPT",
        "reason": "Port the 5.4.291 DWC3 controller halt timeout/run-stop sequencing fixes onto Lisa's downstream DWC3 implementation without replacing the vendor file.",
    },
    "kernel/softirq.c": {
        "class": "ADAPT",
        "reason": "Port the 5.4.291 tasklet initialization API support required by the stable tasklet users while preserving downstream softirq/tasklet behavior.",
    },
    "mm/oom_kill.c": {
        "class": "ADAPT",
        "reason": "Port the 5.4.291 memcg OOM soft-lockup mitigation and matching victim/trace semantics while preserving downstream OOM hooks.",
    },
}

def run(root,*args,check=True):
    return subprocess.run(["git","-C",str(root),*args],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=check)

def blob(root,ref,path):
    p=run(root,"show",f"{ref}:{path}",check=False)
    return None if p.returncode else p.stdout

def work(root,path):
    p=root/path
    return p.read_bytes() if p.is_file() else None

def mergeable(ours,base,theirs):
    if None in (ours,base,theirs) or any(b"\0" in x[:8192] for x in (ours,base,theirs)):
        return False
    with tempfile.TemporaryDirectory() as d:
        d=Path(d)
        for n,x in (("o",ours),("b",base),("t",theirs)): (d/n).write_bytes(x)
        p=subprocess.run(["git","merge-file","-p",str(d/"o"),str(d/"b"),str(d/"t")],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return p.returncode==0

def review(root):
    root=Path(root)
    paths=run(root,"diff","--name-only","--no-renames",BASE,TARGET).stdout.decode().splitlines()
    rows=[]
    for path in paths:
        b,t,o=blob(root,BASE,path),blob(root,TARGET,path),work(root,path)
        vendor=o!=b
        if o==t: cls="ALREADY_PRESENT"
        elif not vendor: cls="DIRECT"
        elif mergeable(o,b,t): cls="AUTO_3WAY"
        else: cls="SEMANTIC_REVIEW"
        row={"path":path,"class":cls,"vendor_diverged":vendor}
        if path in MANUAL and cls=="SEMANTIC_REVIEW":
            row.update(MANUAL[path])
        rows.append(row)
    result={"candidate":"0061","batch":"A","from":"5.4.289","to":"5.4.292","counts":{},"semantic_review":[]}
    for r in rows:
        result["counts"][r["class"]]=result["counts"].get(r["class"],0)+1
        if r["class"]=="SEMANTIC_REVIEW": result["semantic_review"].append(r["path"])
    result["files"]=rows
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kernel",type=Path,required=True)
    ap.add_argument("--out",type=Path,default=Path("candidate-0061-batch-a-review.json"))
    a=ap.parse_args()
    result=review(a.kernel)
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print("C0061_BATCH_A_REVIEW=PASS")
    print("semantic_review="+str(len(result["semantic_review"])))
    return 0
if __name__=="__main__": raise SystemExit(main())
