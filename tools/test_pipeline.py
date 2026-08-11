"""
Pipeline regression test without Vivado.

Models the datapath cycle by cycle (replicating the RTL: BRAM latency,
forwarding, load-use stall, branch flush, sub-word accesses) and compares the
result against a reference sequential RV32I simulator, with both directed and
random programs.

Usage:  python test_pipeline.py
"""
M = 0xFFFFFFFF
def s32(v): return v-(1<<32) if v & 0x80000000 else v

# ---------------- reference: sequential simulator ----------------
def reference(prog, max_steps=2000, mem_words=1024):
    regs=[0]*32; mem=[0]*mem_words; pc=0; steps=0
    while steps<max_steps:
        steps+=1
        if pc>>2 >= len(prog): break
        ins=prog[pc>>2]
        if ins==0: break
        op=ins&0x7F; rd=(ins>>7)&0x1F; f3=(ins>>12)&7
        rs1=(ins>>15)&0x1F; rs2=(ins>>20)&0x1F; f7=(ins>>25)&0x7F
        a=regs[rs1]; b=regs[rs2]; nxt=pc+4
        def imm_i(): return s32(((ins>>20)&0xFFF) | (0xFFFFF000 if ins&0x80000000 else 0))
        def wr(v):
            if rd: regs[rd]=v&M
        if op==0x33:
            sh=b&0x1F
            v={(0,0):(a+b)&M,(0,0x20):(a-b)&M,(1,0):(a<<sh)&M,(2,0):1 if s32(a)<s32(b) else 0,
               (3,0):1 if a<b else 0,(4,0):a^b,(5,0):a>>sh,(5,0x20):(s32(a)>>sh)&M,
               (6,0):a|b,(7,0):a&b}[(f3,f7)]
            wr(v)
        elif op==0x13:
            i=imm_i(); sh=i&0x1F
            v={0:(a+i)&M,1:(a<<sh)&M,2:1 if s32(a)<i else 0,3:1 if a<(i&M) else 0,
               4:a^(i&M),5:(a>>sh) if not (ins>>30)&1 else (s32(a)>>sh)&M,
               6:a|(i&M),7:a&(i&M)}[f3]
            wr(v)
        elif op==0x03:
            addr=(a+imm_i())&M; w=mem[(addr>>2)%mem_words]; off=addr&3
            al=(w>>(8*off))&M
            v={0:s32((al&0xFF)|(0xFFFFFF00 if al&0x80 else 0))&M,
               1:s32((al&0xFFFF)|(0xFFFF0000 if al&0x8000 else 0))&M,
               2:w,4:al&0xFF,5:al&0xFFFF}[f3]
            wr(v)
        elif op==0x23:
            i=s32((((ins>>25)&0x7F)<<5|((ins>>7)&0x1F))|(0xFFFFF000 if ins&0x80000000 else 0))
            addr=(a+i)&M; idx=(addr>>2)%mem_words; off=addr&3
            mask={0:0xFF,1:0xFFFF,2:0xFFFFFFFF}[f3]
            sh=8*off
            mem[idx]=((mem[idx] & ~((mask<<sh)&M)) | ((b&mask)<<sh)) & M
        elif op==0x63:
            i=s32((((ins>>31)&1)<<12|((ins>>7)&1)<<11|((ins>>25)&0x3F)<<5|((ins>>8)&0xF)<<1)
                  |(0xFFFFE000 if ins&0x80000000 else 0))
            if (f3==0 and a==b) or (f3==1 and a!=b): nxt=(pc+i)&M
        elif op==0x37: wr((ins&0xFFFFF000)&M)
        elif op==0x6F:
            i=s32((((ins>>31)&1)<<20|((ins>>21)&0x3FF)<<1|((ins>>20)&1)<<11|((ins>>12)&0xFF)<<12)
                  |(0xFFE00000 if ins&0x80000000 else 0))
            wr(pc+4); nxt=(pc+i)&M
        elif op==0x67:
            t=(a+imm_i())&M; wr(pc+4); nxt=t & ~1
        else: break
        pc=nxt
    return regs, mem, pc

# ================= pipeline model (replicates the RTL) =================
def ctrl(op):
    # ALUOp[9:8] ALUSrc[7] Branch[6] MemRead[5] MemWrite[4] Jump[3] RegWrite[2] MemtoReg[1:0]
    return {0x33:0b10_0_0_0_0_0_1_00, 0x13:0b11_1_0_0_0_0_1_00,
            0x03:0b00_1_0_1_0_0_1_01, 0x23:0b00_1_0_0_1_0_0_00,
            0x63:0b01_0_1_0_0_0_0_00, 0x37:0b00_1_0_0_0_0_1_00,
            0x6F:0b00_0_0_0_0_1_1_10, 0x67:0b00_1_0_0_0_1_1_10}.get(op,0)

def imm_gen(ins):
    op=ins&0x7F; sign=0xFFFFF000 if ins&0x80000000 else 0
    if op in (0x03,0x13,0x67): return (((ins>>20)&0xFFF)|sign)&M
    if op==0x23: return ((((ins>>25)&0x7F)<<5|((ins>>7)&0x1F))|sign)&M
    if op==0x63: return ((((ins>>31)&1)<<12|((ins>>7)&1)<<11|((ins>>25)&0x3F)<<5|
                          ((ins>>8)&0xF)<<1)|(0xFFFFE000 if ins&0x80000000 else 0))&M
    if op==0x37: return ins&0xFFFFF000
    if op==0x6F: return ((((ins>>31)&1)<<20|((ins>>12)&0xFF)<<12|((ins>>20)&1)<<11|
                          ((ins>>21)&0x3FF)<<1)|(0xFFE00000 if ins&0x80000000 else 0))&M
    return 0

def alu_ctrl(op2,f3,b30):
    if op2==0: return 2
    if op2==1: return 6
    if op2==2: return {0:6 if b30 else 2,1:4,2:7,3:9,4:3,5:8 if b30 else 5,6:1,7:0}[f3]
    return {0:2,1:4,2:7,3:9,4:3,5:8 if b30 else 5,6:1,7:0}[f3]

def alu(a,b,c):
    sh=b&0x1F
    return {0:a&b,1:a|b,2:(a+b)&M,3:a^b,4:(a<<sh)&M,5:a>>sh,6:(a-b)&M,
            7:1 if s32(a)<s32(b) else 0,8:(s32(a)>>sh)&M,9:1 if a<b else 0}[c]

class Pipe:
    def __init__(self, prog, mem_words=1024):
        self.imem=list(prog)+[0]*(1024-len(prog)); self.dmem=[0]*mem_words
        self.regs=[0]*32
        self.pc=0; self.pc_fetched=0; self.doutb=0        # IF + BRAM instr
        self.skid=0; self.skid_v=0
        self.ifid={'pc':0,'pc4':0,'ins':0,'valid':0}
        self.idex={'pc':0,'pc4':0,'ctrl':0,'d1':0,'d2':0,'imm':0,'f3':0,'b30':0,
                   'rd':0,'rs1':0,'rs2':0}
        self.exmem={'pc4':0,'ctrl':0,'res':0,'d2':0,'f3':0,'rd':0}
        self.memwb={'ctrl':0,'f3':0,'res':0,'pc4':0,'rd':0}
        self.douta=0
        self.flush_d1=0
        self.halted=False

    def step(self):
        # ---- WB (uses douta of the BRAM, which is the MEM/WB latch of the data) ----
        w=self.memwb; off=w['res']&3; al=(self.douta>>(8*off))&M
        ld={0:((al&0xFF)|(0xFFFFFF00 if al&0x80 else 0))&M,
            1:((al&0xFFFF)|(0xFFFF0000 if al&0x8000 else 0))&M,
            2:self.douta,4:al&0xFF,5:al&0xFFFF}.get(w['f3'],self.douta)
        m2r=w['ctrl']&3
        wb_data={0:w['res'],1:ld,2:w['pc4']}.get(m2r,0)
        wb_we=(w['ctrl']>>2)&1
        # regfile writes on negedge -> visible to ID in the same cycle
        if wb_we and w['rd']: self.regs[w['rd']]=wb_data&M

        # ---- ID ----
        ins=self.ifid['ins']; op=ins&0x7F
        c=ctrl(op); f3=(ins>>12)&7; b30=(ins>>30)&1; rd=(ins>>7)&0x1F
        uses_rs1 = op not in (0x37,0x6F)
        uses_rs2 = op in (0x33,0x23,0x63)
        rs1=(ins>>15)&0x1F if uses_rs1 else 0
        rs2=(ins>>20)&0x1F if uses_rs2 else 0
        d1=0 if rs1==0 else self.regs[rs1]; d2=0 if rs2==0 else self.regs[rs2]
        imm=imm_gen(ins)

        # ---- hazard detection (load-use) ----
        e=self.idex
        mem_read_ex=(e['ctrl']>>5)&1
        stall = bool(mem_read_ex and e['rd']!=0 and (e['rd']==rs1 or e['rd']==rs2))
        pc_write = not stall; if_id_write = not stall; control_mux = stall

        # ---- forwarding ----
        xm=self.exmem; mw=self.memwb
        rw_m=(xm['ctrl']>>2)&1; rw_w=(mw['ctrl']>>2)&1
        def fwd(rs):
            if rw_m and xm['rd']!=0 and xm['rd']==rs: return 2
            if rw_w and mw['rd']!=0 and mw['rd']==rs: return 1
            return 0
        fa,fb=fwd(e['rs1']),fwd(e['rs2'])
        ex_mem_fwd = xm['pc4'] if (xm['ctrl']>>3)&1 else xm['res']
        a_in={2:ex_mem_fwd,1:wb_data,0:e['d1']}[fa]
        b_in={2:ex_mem_fwd,1:wb_data,0:e['d2']}[fb]

        # ---- EX ----
        alu_src=(e['ctrl']>>7)&1
        data2 = e['imm'] if alu_src else b_in
        actrl=alu_ctrl((e['ctrl']>>8)&3, e['f3'], e['b30'])
        res=alu(a_in,data2,actrl); zero = (res==0)
        pc_branch=(e['pc']+e['imm'])&M
        branch_ex=(e['ctrl']>>6)&1; jump_ex=(e['ctrl']>>3)&1
        cond = zero if e['f3']==0 else (not zero if e['f3']==1 else zero)
        taken = bool((branch_ex and cond) or jump_ex)
        jalr = jump_ex and alu_src
        target = res if jalr else pc_branch
        flush = taken
        flush_if = flush or bool(self.flush_d1)

        # ---- MEM (data BRAM, latency 1, WRITE_FIRST) ----
        mem_w=(xm['ctrl']>>4)&1; mem_r=(xm['ctrl']>>5)&1
        widx=(xm['res']>>2)&0x3FF; boff=xm['res']&3
        size={0:0xF&0b0001,1:0b0011,2:0b1111}.get(xm['f3'],0b1111)
        bwe=(size<<boff)&0xF if mem_w else 0
        wdata=(xm['d2']<<(8*boff))&M
        new_douta=self.douta
        if mem_w or mem_r:
            word=self.dmem[widx]
            if bwe:
                mask=0
                for i in range(4):
                    if bwe>>i & 1: mask|=0xFF<<(8*i)
                word=((word & ~mask)|(wdata & mask))&M
                self.dmem[widx]=word
            new_douta=word           # WRITE_FIRST / lectura

        # ---- halt ----
        if self.ifid['ins']==0 and self.ifid['valid'] and self.pc_fetched>0x10:
            self.halted=True

        # ================= state update =================
        new_memwb={'ctrl':xm['ctrl']&7,'f3':xm['f3'],'res':xm['res'],
                   'pc4':xm['pc4'],'rd':xm['rd']}
        new_exmem={'pc4':e['pc4'],'ctrl':e['ctrl']&0x7F,'res':res,'d2':b_in,
                   'f3':e['f3'],'rd':e['rd']}
        new_idex={'pc':self.ifid['pc'],'pc4':self.ifid['pc4'],
                  'ctrl':0 if (control_mux or flush_if) else c,
                  'd1':d1,'d2':d2,'imm':imm,'f3':f3,'b30':b30,'rd':rd,
                  'rs1':rs1,'rs2':rs2}
        instr_eff = self.skid if self.skid_v else self.doutb
        if flush_if:
            new_ifid={'pc':0,'pc4':0,'ins':0,'valid':0}
        elif if_id_write:
            new_ifid={'pc':self.pc_fetched,'pc4':(self.pc_fetched+4)&M,
                      'ins':instr_eff,'valid':1}
        else:
            new_ifid=dict(self.ifid)
        if flush_if: new_skid_v=0
        elif stall:
            if not self.skid_v: self.skid=self.doutb; new_skid_v=1
            else: new_skid_v=1
        else: new_skid_v=0
        pc_en = pc_write or taken
        if pc_en:
            new_pc = target if taken else (self.pc+4)&M
            new_pcf = self.pc
        else:
            new_pc, new_pcf = self.pc, self.pc_fetched
        new_doutb=self.imem[(self.pc>>2)&0x3FF]

        self.memwb,self.exmem,self.idex,self.ifid=new_memwb,new_exmem,new_idex,new_ifid
        self.flush_d1=1 if flush else 0
        self.skid_v=new_skid_v; self.pc,self.pc_fetched=new_pc,new_pcf
        self.doutb=new_doutb; self.douta=new_douta

    def run(self, max_cycles=4000):
        for _ in range(max_cycles):
            if self.halted: break
            self.step()
        return self.regs, self.dmem, self.pc_fetched


import sys


import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from riscv_debug.riscv_assembler import assemble
fails=[]
def run(name, src, check_regs=None):
    prog=assemble(src).words
    exp_r,exp_m,_=reference(prog)
    p=Pipe(prog); got_r,got_m,_=p.run()
    bad=[i for i in range(32) if got_r[i]!=exp_r[i]]
    badm=[i for i in range(64) if got_m[i]!=exp_m[i]]
    ok = not bad and not badm
    print(("  PASS  " if ok else "  FAIL  ")+name)
    if not ok:
        for i in bad[:6]:
            print(f"        x{i}: pipeline=0x{got_r[i]:08X}  referencia=0x{exp_r[i]:08X}")
        for i in badm[:4]:
            print(f"        mem[{i}]: pipeline=0x{got_m[i]:08X}  referencia=0x{exp_m[i]:08X}")
        fails.append(name)

NOPS="\n".join(["nop"]*8)

print("=== Riesgos de datos (lo que ya andaba) ===")
run("forwarding + load-use", (pathlib.Path(__file__).resolve().parent.parent / "examples" / "hazards.s").read_text().replace("FIN:    beq  zero, zero, FIN","")+NOPS)

print("\n=== Fix 1: operaciones nuevas de la ALU ===")
run("sll/srl/sra", f"""
    addi t0, zero, -8
    addi t1, zero, 2
    sll  a0, t0, t1
    srl  a1, t0, t1
    sra  a2, t0, t1
    {NOPS}""")
run("slt/sltu/xor", f"""
    addi t0, zero, -1
    addi t1, zero, 1
    slt  a0, t0, t1
    sltu a1, t0, t1
    xor  a2, t0, t1
    {NOPS}""")
run("inmediatos: slli/srli/srai/xori/slti/sltiu/ori/andi", f"""
    addi t0, zero, -16
    slli a0, t0, 3
    srli a1, t0, 4
    srai a2, t0, 4
    xori a3, t0, 255
    slti a4, t0, 0
    sltiu a5, t0, 0
    ori  a6, t0, 15
    andi a7, t0, 255
    {NOPS}""")
run("addi negativo NO es resta", f"addi t0, zero, 100\naddi t1, t0, -1\n{NOPS}")

print("\n=== Fix 2: lui ===")
run("lui solo", f"lui a0, 0x12345\n{NOPS}")
run("lui despues de escribir el registro que ocupa esos bits", f"""
    addi x18, zero, 999
    lui  a0, 0x12345
    {NOPS}""")
run("lui + addi (patron li)", f"lui a0, 0x12345\naddi a0, a0, 0x678\n{NOPS}")

print("\n=== Fix 3: saltos ===")
run("beq tomado", f"""
    addi t0, zero, 5
    addi t1, zero, 5
    beq  t0, t1, DEST
    addi a0, zero, 99
    addi a1, zero, 88
DEST: addi a2, zero, 7
    {NOPS}""")
run("beq NO tomado", f"""
    addi t0, zero, 5
    addi t1, zero, 6
    beq  t0, t1, DEST
    addi a0, zero, 99
DEST: addi a2, zero, 7
    {NOPS}""")
run("bne tomado", f"""
    addi t0, zero, 5
    addi t1, zero, 6
    bne  t0, t1, DEST
    addi a0, zero, 99
    addi a1, zero, 88
DEST: addi a2, zero, 7
    {NOPS}""")
run("bne NO tomado", f"""
    addi t0, zero, 5
    addi t1, zero, 5
    bne  t0, t1, DEST
    addi a0, zero, 33
DEST: addi a2, zero, 7
    {NOPS}""")
run("salto hacia atras (loop)", f"""
    addi t0, zero, 3
    addi t1, zero, 0
LOOP: addi t1, t1, 10
    addi t0, t0, -1
    bne  t0, zero, LOOP
    add  a0, t1, zero
    {NOPS}""")
run("jal guarda pc+4 y salta", f"""
    jal  ra, DEST
    addi a0, zero, 99
    addi a1, zero, 88
DEST: addi a2, zero, 7
    {NOPS}""")
run("jalr", f"""
    addi t0, zero, 20
    jalr ra, 0(t0)
    addi a0, zero, 99
    addi a1, zero, 88
    addi a2, zero, 7
    {NOPS}""")
run("branch con operandos adelantados", f"""
    addi t0, zero, 5
    addi t1, t0, 0
    beq  t0, t1, DEST
    addi a0, zero, 99
DEST: addi a1, zero, 1
    {NOPS}""")

print("\n=== Fix 4: accesos de byte y media palabra ===")
run("sw/lw", f"""
    addi t0, zero, 291
    sw   t0, 16(zero)
    lw   a0, 16(zero)
    {NOPS}""")
run("sb en los 4 offsets", f"""
    addi t0, zero, 0xAA
    sb   t0, 32(zero)
    sb   t0, 33(zero)
    sb   t0, 34(zero)
    sb   t0, 35(zero)
    lw   a0, 32(zero)
    {NOPS}""")
run("sh en offset 0 y 2", f"""
    addi t0, zero, 0x7BC
    sh   t0, 40(zero)
    sh   t0, 42(zero)
    lw   a0, 40(zero)
    {NOPS}""")
run("lb con signo", f"""
    addi t0, zero, 0xF0
    sb   t0, 48(zero)
    lb   a0, 48(zero)
    lbu  a1, 48(zero)
    {NOPS}""")
run("lh con signo", f"""
    lui  t0, 0xFFFF0
    sh   t0, 56(zero)
    lh   a0, 56(zero)
    lhu  a1, 56(zero)
    {NOPS}""")
run("lb en offset 3", f"""
    addi t0, zero, 0x7F
    sb   t0, 67(zero)
    lb   a0, 67(zero)
    lw   a1, 64(zero)
    {NOPS}""")
run("load-use con lb", f"""
    addi t0, zero, 0x25
    sb   t0, 72(zero)
    lb   a0, 72(zero)
    add  a1, a0, a0
    {NOPS}""")

print("\n=== Programas aleatorios contra la referencia ===")
import random
R  = ["add","sub","sll","srl","sra","and","or","xor","slt","sltu"]
I  = ["addi","andi","ori","xori","slti","sltiu"]
SH = ["slli","srli","srai"]
LD = ["lb","lh","lw","lbu","lhu"]
ST = ["sb","sh","sw"]
BR = ["beq","bne"]

def gen(rng, n):
    out=[]
    for i in range(n):
        k=rng.random(); rd=rng.randint(1,15); a=rng.randint(0,15); b=rng.randint(0,15)
        if k<0.30:   out.append(f"{rng.choice(R)} x{rd}, x{a}, x{b}")
        elif k<0.50: out.append(f"{rng.choice(I)} x{rd}, x{a}, {rng.randint(-64,64)}")
        elif k<0.58: out.append(f"{rng.choice(SH)} x{rd}, x{a}, {rng.randint(0,31)}")
        elif k<0.68:
            op=rng.choice(ST); off=rng.randrange(0,256,{"sb":1,"sh":2,"sw":4}[op])
            out.append(f"{op} x{b}, {off}(x0)")
        elif k<0.80:
            op=rng.choice(LD); off=rng.randrange(0,256,{"lb":1,"lbu":1,"lh":2,"lhu":2,"lw":4}[op])
            out.append(f"{op} x{rd}, {off}(x0)")
        elif k<0.86: out.append(f"lui x{rd}, {rng.randint(0,0xFFFFF)}")
        elif k<0.96:
            f=rng.randint(1,min(4,max(1,n-i-1))); out.append(f"{rng.choice(BR)} x{a}, x{b}, {4*f}")
        else:
            f=rng.randint(1,min(4,max(1,n-i-1))); out.append(f"jal x{rd}, {4*f}")
    return "\n".join(out)+"\n"+"\n".join(["nop"]*10)

rng=random.Random(20260811); bad=0; total=0
for t in range(400):
    prog=assemble(gen(rng, rng.randint(6,30))).words
    total+=1
    exp_r,exp_m,_=reference(prog); got_r,got_m,_=Pipe(prog).run()
    if [i for i in range(32) if got_r[i]!=exp_r[i]] or [i for i in range(64) if got_m[i]!=exp_m[i]]:
        bad+=1
print(f"  {'PASS' if bad==0 else 'FAIL'}  {total} programas aleatorios, {bad} diferencias")
if bad: fails.append("programas aleatorios")

print("\n"+"="*56)
print(f"FALLARON {len(fails)}: {fails}" if fails else "TODO OK")
sys.exit(1 if fails else 0)
