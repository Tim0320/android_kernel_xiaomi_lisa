/* SPDX-License-Identifier: GPL-2.0-only
 * Opt-in ring-buffer test for the actual target kernel, never a host substitute.
 * Temporary BPF maps/programs only: no pinning, network settings or disk writes.
 * Supports PID1 in an isolated QEMU initramfs. Normal execution requires --run.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <linux/bpf.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#define RB_TYPE 27
#define RB_OUTPUT 130
#define RB_RESERVE 131
#define RB_SUBMIT 132
#define RB_DISCARD 133
#define RB_QUERY 134
#define RING_SIZE 16384U
#define SAMPLE UINT64_C(0x00585242)
static char vlog[65536];
static int fails, tests;
struct program { struct bpf_insn i[128]; unsigned n; };
static void emit(struct program *p, unsigned code, unsigned dst, unsigned src, int off, int imm)
{
    if (p->n >= 128) abort();
    p->i[p->n++] = (struct bpf_insn){.code=code,.dst_reg=dst,.src_reg=src,.off=off,.imm=imm};
}
static void movi(struct program *p,unsigned d,int n) { emit(p,BPF_ALU64|BPF_MOV|BPF_K,d,0,0,n); }
static void movr(struct program *p,unsigned d,unsigned s) { emit(p,BPF_ALU64|BPF_MOV|BPF_X,d,s,0,0); }
static void call(struct program *p,int n) { emit(p,BPF_JMP|BPF_CALL,0,0,0,n); }
static void exitp(struct program *p) { emit(p,BPF_JMP|BPF_EXIT,0,0,0,0); }
static void map(struct program *p,unsigned reg,int fd)
{ emit(p,BPF_LD|BPF_DW|BPF_IMM,reg,BPF_PSEUDO_MAP_FD,0,fd); emit(p,0,0,0,0,0); }
static int bpf_call(enum bpf_cmd cmd, union bpf_attr *a)
{ return syscall(__NR_bpf,cmd,a,sizeof(*a)); }
static int newmap(unsigned type,unsigned key,unsigned value,unsigned entries)
{
    union bpf_attr a={0};a.map_type=type;a.key_size=key;a.value_size=value;a.max_entries=entries;
    return bpf_call(BPF_MAP_CREATE,&a);
}
static int load(struct program *p)
{
    union bpf_attr a={0};static const char license[]="GPL";
    memset(vlog,0,sizeof(vlog));a.prog_type=BPF_PROG_TYPE_SOCKET_FILTER;
    a.insn_cnt=p->n;a.insns=(uintptr_t)p->i;a.license=(uintptr_t)license;
    a.log_buf=(uintptr_t)vlog;a.log_size=sizeof(vlog);a.log_level=1;
    return bpf_call(BPF_PROG_LOAD,&a);
}
static int run(int fd,unsigned *retval)
{
    unsigned char input[64]={0}, output[128]={0};union bpf_attr a={0};
    a.test.prog_fd=fd;a.test.data_in=(uintptr_t)input;a.test.data_out=(uintptr_t)output;
    a.test.data_size_in=sizeof(input);a.test.data_size_out=sizeof(output);a.test.repeat=1;
    int ret=bpf_call(BPF_PROG_TEST_RUN,&a);*retval=a.test.retval;return ret;
}
static void result(const char *name,int ok)
{ ++tests;if(!ok)++fails;printf("BPF58_TEST %s %s\n",ok?"PASS":"FAIL",name); }
enum variant { GOOD, LEAK, NO_NULL, OOB, OFFSET_RELEASE, DOUBLE_RELEASE, AFTER_RELEASE, TOO_BIG, DISCARD, SPILL };
static struct program reserve(int fd,enum variant v)
{
    struct program p={0};map(&p,1,fd);movi(&p,2,v==TOO_BIG?0x7fffffff:8);movi(&p,3,0);call(&p,RB_RESERVE);
    unsigned branch=p.n;emit(&p,BPF_JMP|BPF_JEQ|BPF_K,0,0,0,0);
    if(v==NO_NULL) movi(&p,9,0),p.i[branch]=(struct bpf_insn){.code=BPF_ALU64|BPF_MOV|BPF_K,.dst_reg=9};
    movr(&p,6,0);
    if(v==SPILL) {
        emit(&p,BPF_STX|BPF_MEM|BPF_DW,10,6,-8,0);
        emit(&p,BPF_LDX|BPF_MEM|BPF_DW,6,10,-8,0);
    }
    emit(&p,BPF_ST|BPF_MEM|BPF_DW,6,0,v==OOB?8:0,(int)SAMPLE);
    if(v!=LEAK) {
        movr(&p,1,6);if(v==OFFSET_RELEASE)emit(&p,BPF_ALU64|BPF_ADD|BPF_K,1,0,0,8);
        movi(&p,2,0);call(&p,v==DISCARD?RB_DISCARD:RB_SUBMIT);
        if(v==DOUBLE_RELEASE) {movr(&p,1,6);movi(&p,2,0);call(&p,RB_DISCARD);}
        if(v==AFTER_RELEASE)emit(&p,BPF_ST|BPF_MEM|BPF_DW,6,0,0,1);
    }
    if(v!=NO_NULL)p.i[branch].off=(int)p.n-(int)branch-1;
    movi(&p,0,0);exitp(&p);return p;
}
static void verifier_case(int mapfd,enum variant v,const char *name,int accepted)
{
    struct program p=reserve(mapfd,v);int fd=load(&p);
    result(name,accepted?(fd>=0):(fd<0 && vlog[0]));
    if(accepted && fd<0)printf("BPF58_VERIFIER errno=%d %.800s\n",errno,vlog);
    if(fd>=0)close(fd);
}
static struct program output_prog(int fd)
{
    struct program p={0};emit(&p,BPF_ST|BPF_MEM|BPF_DW,10,0,-8,(int)SAMPLE);
    map(&p,1,fd);movr(&p,2,10);emit(&p,BPF_ALU64|BPF_ADD|BPF_K,2,0,0,-8);
    movi(&p,3,8);movi(&p,4,2);call(&p,RB_OUTPUT);exitp(&p);return p;
}
static struct program pending_prog(int fd)
{
    struct program p={0};movi(&p,8,0);map(&p,1,fd);movi(&p,2,12288);movi(&p,3,0);call(&p,RB_RESERVE);
    unsigned first=p.n;emit(&p,BPF_JMP|BPF_JEQ|BPF_K,0,0,0,0);movr(&p,6,0);
    map(&p,1,fd);movi(&p,2,12288);movi(&p,3,0);call(&p,RB_RESERVE);
    unsigned second=p.n;emit(&p,BPF_JMP|BPF_JEQ|BPF_K,0,0,0,0);
    movr(&p,1,0);movi(&p,2,0);call(&p,RB_DISCARD);movi(&p,8,1);
    p.i[second].off=(int)p.n-(int)second-1;
    movr(&p,1,6);movi(&p,2,0);call(&p,RB_DISCARD);movr(&p,0,8);exitp(&p);
    p.i[first].off=(int)p.n-(int)first-1;movi(&p,0,2);exitp(&p);return p;
}
static int perform(void)
{
    struct rlimit lim={RLIM_INFINITY,RLIM_INFINITY};(void)setrlimit(RLIMIT_MEMLOCK,&lim);
    int fd=newmap(RB_TYPE,0,0,RING_SIZE);
    if(fd<0){printf("BPF58_FEATURE_UNAVAILABLE errno=%d (%s)\n",errno,strerror(errno));return 1;}
    result("ringbuf_map_create",1);
    int bad=newmap(RB_TYPE,4,0,RING_SIZE);result("reject_nonzero_key",bad<0);if(bad>=0)close(bad);
    bad=newmap(RB_TYPE,0,8,RING_SIZE);result("reject_nonzero_value",bad<0);if(bad>=0)close(bad);
    bad=newmap(RB_TYPE,0,0,12288);result("reject_non_power_two",bad<0);if(bad>=0)close(bad);
    verifier_case(fd,GOOD,"reserve_submit_verified",1);
    verifier_case(fd,DISCARD,"reserve_discard_verified",1);
    verifier_case(fd,SPILL,"reserve_spill_reload_verified",1);
    verifier_case(fd,LEAK,"reject_unreleased_reference",0);
    verifier_case(fd,NO_NULL,"reject_missing_null_check",0);
    verifier_case(fd,OOB,"reject_record_oob",0);
    verifier_case(fd,OFFSET_RELEASE,"reject_interior_release",0);
    verifier_case(fd,DOUBLE_RELEASE,"reject_double_release",0);
    verifier_case(fd,AFTER_RELEASE,"reject_use_after_release",0);
    verifier_case(fd,TOO_BIG,"reject_unbounded_allocation",0);
    int array=newmap(BPF_MAP_TYPE_ARRAY,4,8,1);
    result("existing_array_map_still_works",array>=0);
    if(array>=0){verifier_case(array,GOOD,"reject_ringbuf_helper_on_array",0);close(array);}
    long page=sysconf(_SC_PAGESIZE);
    uint64_t *consumer=mmap(NULL,page,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    unsigned char *producer=mmap(NULL,page+2*RING_SIZE,PROT_READ,MAP_SHARED,fd,page);
    result("consumer_rw_producer_ro_mmap",consumer!=MAP_FAILED && producer!=MAP_FAILED);
    if(consumer!=MAP_FAILED && producer!=MAP_FAILED) {
        result("reject_producer_mprotect_write",mprotect(producer,page,PROT_READ|PROT_WRITE)<0);
        void *wrong=mmap(NULL,page,PROT_READ|PROT_WRITE,MAP_SHARED,fd,page);
        result("reject_writable_producer_mapping",wrong==MAP_FAILED);if(wrong!=MAP_FAILED)munmap(wrong,page);
        struct program p=output_prog(fd);int prog=load(&p);unsigned retval=~0U;
        result("output_helper_load",prog>=0);
        if(prog>=0){result("output_helper_run",run(prog,&retval)==0 && retval==0);close(prog);}
        struct pollfd item={.fd=fd,.events=POLLIN};int ready=poll(&item,1,1000);
        uint32_t len;uint64_t sample;memcpy(&len,producer+page,4);memcpy(&sample,producer+page+8,8);
        result("poll_and_record_roundtrip",ready==1 && (item.revents&POLLIN) && len==8 && sample==SAMPLE);
        __atomic_store_n(consumer,16,__ATOMIC_RELEASE);
        p=(struct program){0};map(&p,1,fd);movi(&p,2,1);call(&p,RB_QUERY);exitp(&p);prog=load(&p);
        result("query_helper_load",prog>=0);if(prog>=0){result("query_ring_size",run(prog,&retval)==0 && retval==RING_SIZE);close(prog);}
        close(fd);fd=-1;result("mapping_lifetime_after_fd_close",__atomic_load_n(consumer,__ATOMIC_ACQUIRE)==16);
    }
    if(consumer!=MAP_FAILED)munmap(consumer,page);
    if(producer!=MAP_FAILED)munmap(producer,page+2*RING_SIZE);
    if(fd>=0)close(fd);
    fd=newmap(RB_TYPE,0,0,RING_SIZE);
    if(fd>=0){
        consumer=mmap(NULL,page,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
        if(consumer!=MAP_FAILED){
            __atomic_store_n(consumer,12288,__ATOMIC_RELEASE);
            struct program p=pending_prog(fd);int prog=load(&p);unsigned value=~0U;
            result("pending_reservation_program_load",prog>=0);
            if(prog>=0){result("reject_overlapping_pending_reservation",run(prog,&value)==0 && value==0);close(prog);}
            munmap(consumer,page);
        }else result("pending_test_mapping",0);
        close(fd);
    }else result("pending_test_map",0);
    printf("BPF58_RESULT tests=%d failures=%d\n",tests,fails);
    return fails?1:0;
}
int main(int argc,char **argv)
{
    int init=(getpid()==1);setvbuf(stdout,NULL,_IONBF,0);
    if(!init && (argc!=2 || strcmp(argv[1],"--run"))) {
        fprintf(stderr,"Usage: %s --run (root/CAP_SYS_ADMIN; temporary BPF objects only)\n",argv[0]);return 2;
    }
    if(init){(void)mount("proc","/proc","proc",0,NULL);(void)mount("sysfs","/sys","sysfs",0,NULL);}
    printf("LISA_BPF58_TARGET_PROBE_BEGIN\n");int ret=perform();
    printf("LISA_BPF58_TARGET_PROBE_%s\n",ret?"FAIL":"PASS");
    if(init){sync();reboot(RB_POWER_OFF);for(;;)pause();}
    return ret;
}
