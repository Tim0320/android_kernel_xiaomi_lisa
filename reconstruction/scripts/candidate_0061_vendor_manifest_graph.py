#!/usr/bin/env python3
"""Offline manifest dependency graph; never infer modprobe -l order or Android runtime success."""
import argparse
import collections
import json
from pathlib import Path

def parse_load(text):
    names=[x.strip() for x in text.splitlines() if x.strip() and not x.lstrip().startswith("#")]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate modules.load entry")
    return names

def parse_dep(text):
    graph={}
    for n,line in enumerate(text.splitlines(),1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"Malformed modules.dep line {n}")
        name,dependencies=line.split(":",1)
        name=Path(name).name
        if name in graph:
            raise ValueError("Duplicate modules.dep entry: "+name)
        graph[name]=[Path(dep).name for dep in dependencies.strip().split()]
    return graph

def analyze(load,graph):
    known=set(graph)
    broken=sorted({(module,dep) for module,deps in graph.items() for dep in deps if dep not in known})
    reverse=collections.defaultdict(set)
    for module,deps in graph.items():
        for dep in deps:
            reverse[dep].add(module)
    colors={}
    cycles=set()
    def check(name,stack):
        if colors.get(name)==1:
            cycles.add(tuple(stack[stack.index(name):]+[name]))
            return
        if colors.get(name)==2:
            return
        colors[name]=1
        for child in graph.get(name,[]):
            if child in known:
                check(child,stack+[child])
        colors[name]=2
    for module in graph:
        check(module,[module])
    def transitive_dependents(module):
        todo=list(reverse[module])
        seen=set()
        while todo:
            n=todo.pop()
            if n not in seen:
                seen.add(n)
                todo.extend(reverse[n])
        return len(seen)
    fanin=sorted([(len(parents),transitive_dependents(n),n) for n,parents in list(reverse.items())],reverse=True)
    return {
        "modules_load":len(load),"modules_dep":len(graph),
        "dependency_edges":sum(map(len,graph.values())),
        "load_without_dep_entry":sorted(set(load)-known),
        "dep_entry_not_in_load":sorted(known-set(load)),
        "unresolved_deps":[list(x) for x in broken],
        "dependency_cycles":len(cycles),
        "high_fanin":[{"module":n,"direct":direct,"transitive":transitive} for direct,transitive,n in fanin[:10]],
        "nfc_in_load":"nfc_i2c.ko" in load,
        "actual_modprobe_list_order":"UNKNOWN",
        "android_actual_modules_loaded":"UNKNOWN"
    }

def self_test():
    a=analyze(parse_load("a.ko\\nb.ko\\n".replace("\\n","\n")),parse_dep("a.ko: b.ko\nb.ko:"))
    assert a["modules_load"]==2 and a["dependency_edges"]==1
    assert a["dependency_cycles"]==0 and not a["unresolved_deps"]
    assert a["high_fanin"][0]["module"]=="b.ko"
    b=analyze(["a.ko"],parse_dep("a.ko: missing.ko"))
    assert b["unresolved_deps"]==[["a.ko","missing.ko"]]
    c=analyze(["a.ko","b.ko"],parse_dep("a.ko: b.ko\nb.ko: a.ko"))
    assert c["dependency_cycles"]==1
    assert a["actual_modprobe_list_order"]=="UNKNOWN"
    print("C0061_MANIFEST_GRAPH_SELF_TEST=PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    for name in ["qgki_load","qgki_dep","gki_load","gki_dep","json"]:
        p.add_argument("--"+name.replace("_","-"),type=Path)
    a=p.parse_args()
    if a.self_test:
        self_test()
        return
    for name in ["qgki_load","qgki_dep","gki_load","gki_dep","json"]:
        if getattr(a,name) is None:
            p.error("--"+name.replace("_","-")+" required")
    ql=parse_load(a.qgki_load.read_text())
    gl=parse_load(a.gki_load.read_text())
    result={
        "scope":"OFFLINE_VENDOR_MANIFEST_GRAPH_NOT_ABI_OR_RUNTIME_PROOF",
        "qgki":analyze(ql,parse_dep(a.qgki_dep.read_text())),
        "gki":analyze(gl,parse_dep(a.gki_dep.read_text())),
        "shared_names":len(set(ql)&set(gl)),
        "qgki_only":len(set(ql)-set(gl)),
        "gki_only":len(set(gl)-set(ql)),
        "blocklist_presence":"UNKNOWN_PULL_FAILED",
        "first_modprobe_probe":"UNKNOWN_REQUIRES_REAL_MODPROBE_LIST",
        "fallback_executed_on_device":"UNKNOWN"
    }
    a.json.write_text(json.dumps(result,indent=2)+"\n")
    print("C0061_MANIFEST_GRAPH=PASS")
    print("QGKI",len(ql),"GKI",len(gl),"SHARED",result["shared_names"])
    print("MODPROBE_FIRST_PROBE=UNKNOWN")

if __name__=="__main__":
    main()
