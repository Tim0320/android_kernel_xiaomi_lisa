from pathlib import Path

MANUAL={
"kernel/time/hrtimer.c":"NOT_APPLICABLE",
"kernel/cpu.c":"NOT_APPLICABLE",
"drivers/clk/qcom/clk-rpmh.c":"ADAPT",
"drivers/clk/qcom/clk-alpha-pll.c":"ADAPT",
"drivers/soc/qcom/socinfo.c":"ADAPT",
"kernel/gen_kheaders.sh":"ADAPT",
"drivers/usb/gadget/function/f_fs.c":"ADAPT",
"Documentation/devicetree/bindings/mmc/mmc-controller.yaml":"ADAPT",
"drivers/usb/dwc3/gadget.c":"ADAPT",
"kernel/softirq.c":"ADAPT",
"mm/oom_kill.c":"ADAPT",
}

def once(s,old,new,label):
    n=s.count(old)
    if n!=1: raise RuntimeError(f"{label}: anchor count={n}")
    return s.replace(old,new,1)

def adapt(root:Path,path:str,target_ref:str,target_blob):
    if path=="Documentation/devicetree/bindings/mmc/mmc-controller.yaml":
        data=target_blob(path)
        if data is None: raise RuntimeError("missing upstream MMC binding")
        p=root/path; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data); return
    p=root/path; s=p.read_text()

    if path=="drivers/clk/qcom/clk-rpmh.c":
        s=once(s,"return c->aggr_state * c->unit;",
          "return (unsigned long)c->aggr_state * c->unit;","clk-rpmh")

    elif path=="drivers/clk/qcom/clk-alpha-pll.c":
        s=once(s,"config->vco_val ||\n\t\tconfig->alpha_en_mask) {",
          "config->vco_val ||\n\t\tconfig->alpha_en_mask ||\n\t\tconfig->alpha_mode_mask) {","alpha condition")
        s=once(s,"\t\tval |= config->alpha_en_mask;\n",
          "\t\tval |= config->alpha_en_mask;\n\t\tval |= config->alpha_mode_mask;\n","alpha val")
        s=once(s,"\t\tmask |= config->alpha_en_mask;\n",
          "\t\tmask |= config->alpha_en_mask;\n\t\tmask |= config->alpha_mode_mask;\n","alpha mask")

    elif path=="drivers/soc/qcom/socinfo.c":
        if "static size_t socinfo_item_size;" not in s:
            s=once(s,"static uint32_t socinfo_format;\n",
              "static uint32_t socinfo_format;\nstatic size_t socinfo_item_size;\n","socinfo storage")
        old="\treturn socinfo ?\n\t\t(socinfo_format >= SOCINFO_VERSION(0, 10) ?\n\t\t\tle32_to_cpu(socinfo->serial_num) : 0)\n\t\t: 0;"
        new="\treturn socinfo ?\n\t\t(socinfo_format >= SOCINFO_VERSION(0, 10) &&\n\t\t offsetof(struct socinfo, serial_num) + sizeof(__le32) <= socinfo_item_size ?\n\t\t\tle32_to_cpu(socinfo->serial_num) : 0)\n\t\t: 0;"
        s=once(s,old,new,"socinfo serial bounds")
        s=once(s,"\tsocinfo = info;\n","\tsocinfo = info;\n\tsocinfo_item_size = item_size;\n","socinfo size")

    elif path=="kernel/gen_kheaders.sh":
        old='tar "${KBUILD_BUILD_TIMESTAMP:+--mtime=$KBUILD_BUILD_TIMESTAMP}" \\\n'.replace("\\$","$")
        s=once(s,old,old+'    --exclude=".__afs*" --exclude=".nfs*" \\\n',"kheaders excludes")

    elif path=="drivers/usb/gadget/function/f_fs.c":
        old="\tif (WARN_ON(ffs->state != FFS_ACTIVE\n\t\t || test_and_set_bit(FFS_FL_BOUND, &ffs->flags)))\n\t\treturn -EBADFD;"
        new="\tif (ffs->state != FFS_ACTIVE\n\t\t || test_and_set_bit(FFS_FL_BOUND, &ffs->flags))\n\t\treturn -EBADFD;"
        s=once(s,old,new,"FunctionFS")

    elif path=="drivers/usb/dwc3/gadget.c":
        s=once(s,"\tu32\t\t\ttimeout = 1500;\n",
          "\tu32\t\t\ttimeout = 2000;\n\tu32\t\t\tsaved_config = 0;\n","dwc3 timeout")
        anchor='\tdbg_event(0xFF, "run_stop", is_on);\n'
        add=(
          "\treg = dwc3_readl(dwc->regs, DWC3_GUSB2PHYCFG(0));\n"
          "\tif (reg & DWC3_GUSB2PHYCFG_SUSPHY) {\n\t\tsaved_config |= DWC3_GUSB2PHYCFG_SUSPHY;\n\t\treg &= ~DWC3_GUSB2PHYCFG_SUSPHY;\n\t}\n"
          "\tif (reg & DWC3_GUSB2PHYCFG_ENBLSLPM) {\n\t\tsaved_config |= DWC3_GUSB2PHYCFG_ENBLSLPM;\n\t\treg &= ~DWC3_GUSB2PHYCFG_ENBLSLPM;\n\t}\n"
          "\tif (saved_config)\n\t\tdwc3_writel(dwc->regs, DWC3_GUSB2PHYCFG(0), reg);\n\n")
        s=once(s,anchor,anchor+add,"dwc3 phy")
        old="\tdo {\n\t\treg = dwc3_readl(dwc->regs, DWC3_DSTS);\n\t\treg &= DWC3_DSTS_DEVCTRLHLT;\n\t} while (--timeout && !(!is_on ^ !reg));\n\n\tif (!timeout) {"
        new="\tdo {\n\t\tusleep_range(1000, 2000);\n\t\treg = dwc3_readl(dwc->regs, DWC3_DSTS);\n\t\treg &= DWC3_DSTS_DEVCTRLHLT;\n\t} while (--timeout && !(!is_on ^ !reg));\n\n\tif (saved_config) {\n\t\treg = dwc3_readl(dwc->regs, DWC3_GUSB2PHYCFG(0));\n\t\treg |= saved_config;\n\t\tdwc3_writel(dwc->regs, DWC3_GUSB2PHYCFG(0), reg);\n\t}\n\n\tif (!timeout) {"
        s=once(s,old,new,"dwc3 poll")

    elif path=="kernel/softirq.c":
        s=once(s,"\t\t\t\tt->func(t->data);\n",
          "\t\t\t\tif (t->use_callback)\n\t\t\t\t\tt->callback(t);\n\t\t\t\telse\n\t\t\t\t\tt->func(t->data);\n","tasklet dispatch")
        marker="void tasklet_init(struct tasklet_struct *t,\n"
        setup="void tasklet_setup(struct tasklet_struct *t,\n\t\t   void (*callback)(struct tasklet_struct *))\n{\n\tt->next = NULL;\n\tt->state = 0;\n\tatomic_set(&t->count, 0);\n\tt->callback = callback;\n\tt->use_callback = true;\n\tt->data = 0;\n}\nEXPORT_SYMBOL(tasklet_setup);\n\n"
        s=once(s,marker,setup+marker,"tasklet setup")
        s=once(s,"\tt->func = func;\n\tt->data = data;\n",
          "\tt->func = func;\n\tt->use_callback = false;\n\tt->data = data;\n","tasklet init")

    elif path=="mm/oom_kill.c":
        if "#include <linux/cred.h>" not in s:
            s=once(s,"#include <linux/mmu_notifier.h>\n",
              "#include <linux/mmu_notifier.h>\n#include <linux/cred.h>\n#include <linux/nmi.h>\n","oom includes")
        old="\telse {\n\t\tstruct task_struct *p;\n\n\t\trcu_read_lock();\n\t\tfor_each_process(p)\n\t\t\tdump_task(p, oc);\n\t\trcu_read_unlock();\n\t}"
        new="\telse {\n\t\tstruct task_struct *p;\n\t\tint i = 0;\n\n\t\trcu_read_lock();\n\t\tfor_each_process(p) {\n\t\t\tif ((++i & 1023) == 0)\n\t\t\t\ttouch_softlockup_watchdog();\n\t\t\tdump_task(p, oc);\n\t\t}\n\t\trcu_read_unlock();\n\t}"
        s=once(s,old,new,"oom dump")
        upstream_anchor="static void mark_oom_victim(struct task_struct *tsk)\n{\n\tstruct mm_struct *mm = tsk->mm;"
        lisa_anchor="static void mark_oom_victim(struct task_struct *tsk)\n{\n\tWARN_ON(oom_killer_disabled);"
        if upstream_anchor in s:
            s=once(s,upstream_anchor,
              "static void mark_oom_victim(struct task_struct *tsk)\n{\n\tconst struct cred *cred;\n\tstruct mm_struct *mm = tsk->mm;","oom cred upstream")
        elif lisa_anchor in s:
            s=once(s,lisa_anchor,
              "static void mark_oom_victim(struct task_struct *tsk)\n{\n\tconst struct cred *cred;\n\n\tWARN_ON(oom_killer_disabled);","oom cred lisa")
        else:
            raise RuntimeError("oom cred: no supported mark_oom_victim layout")
        s=once(s,"\ttrace_mark_victim(tsk->pid);\n",
          "\tcred = get_task_cred(tsk);\n\ttrace_mark_victim(tsk, cred->uid.val);\n\tput_cred(cred);\n","oom trace")

    else:
        raise RuntimeError("unknown manual path: "+path)
    p.write_text(s)
