from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Iterable
from .opcodes import OPCODES, Opcode
from .rom import NESRom

PPU_REGS = {
    0x2000:'PPUCTRL',0x2001:'PPUMASK',0x2002:'PPUSTATUS',0x2003:'OAMADDR',
    0x2004:'OAMDATA',0x2005:'PPUSCROLL',0x2006:'PPUADDR',0x2007:'PPUDATA',
    0x4000:'SQ1_VOL',0x4001:'SQ1_SWEEP',0x4002:'SQ1_LO',0x4003:'SQ1_HI',
    0x4004:'SQ2_VOL',0x4005:'SQ2_SWEEP',0x4006:'SQ2_LO',0x4007:'SQ2_HI',
    0x4008:'TRI_LINEAR',0x400A:'TRI_LO',0x400B:'TRI_HI',0x400C:'NOISE_VOL',
    0x400E:'NOISE_LO',0x400F:'NOISE_HI',0x4010:'DMC_FREQ',0x4011:'DMC_RAW',
    0x4012:'DMC_START',0x4013:'DMC_LEN',0x4014:'OAMDMA',0x4015:'APUSTATUS',
    0x4016:'CONTROLLER1',0x4017:'CONTROLLER2_APUFRAME',
}
BRANCHES = {'BPL','BMI','BVC','BVS','BCC','BCS','BNE','BEQ'}
TERMINATORS = {'RTS','RTI','BRK','KIL'}
WRITE_MNEMONICS = {'STA','STX','STY','SAX','SHX','SHY','AHX','TAS'}

@dataclass
class Insn:
    addr: int
    opcode: int
    mnemonic: str
    mode: str
    size: int
    operand: int | None
    raw: list[int]
    official: bool

    @property
    def next_addr(self) -> int:
        return (self.addr + self.size) & 0xFFFF

    def text(self) -> str:
        if self.mode == 'imp': arg = ''
        elif self.mode == 'acc': arg = 'A'
        elif self.mode == 'imm': arg = f'#$%02X' % (self.operand or 0)
        elif self.mode == 'zp': arg = f'$%02X' % (self.operand or 0)
        elif self.mode == 'zpx': arg = f'$%02X,X' % (self.operand or 0)
        elif self.mode == 'zpy': arg = f'$%02X,Y' % (self.operand or 0)
        elif self.mode == 'abs': arg = f'$%04X' % (self.operand or 0)
        elif self.mode == 'absx': arg = f'$%04X,X' % (self.operand or 0)
        elif self.mode == 'absy': arg = f'$%04X,Y' % (self.operand or 0)
        elif self.mode == 'ind': arg = f'($%04X)' % (self.operand or 0)
        elif self.mode == 'indx': arg = f'($%02X,X)' % (self.operand or 0)
        elif self.mode == 'indy': arg = f'($%02X),Y' % (self.operand or 0)
        elif self.mode == 'rel': arg = f'$%04X' % (self.operand or 0)
        else: arg = ''
        star = '' if self.official else ' *'
        return f'{self.mnemonic} {arg}'.rstrip() + star

@dataclass
class BasicBlock:
    start: int
    end: int
    instructions: list[int]
    successors: list[int]
    calls: list[int]


def _read(rom: NESRom, addr: int) -> int | None:
    return rom.deterministic_cpu_read(addr)


def decode_insn(rom: NESRom, addr: int) -> Insn | None:
    op = _read(rom, addr)
    if op is None:
        return None
    spec: Opcode = OPCODES[op]
    raw: list[int] = []
    for i in range(spec.size):
        b = _read(rom, (addr + i) & 0xFFFF)
        if b is None:
            return None
        raw.append(b)
    operand = None
    if spec.size == 2:
        operand = raw[1]
        if spec.mode == 'rel':
            disp = operand if operand < 0x80 else operand - 0x100
            operand = (addr + 2 + disp) & 0xFFFF
    elif spec.size == 3:
        operand = raw[1] | (raw[2] << 8)
    return Insn(addr, op, spec.mnemonic, spec.mode, spec.size, operand, raw, spec.official)


def recursive_disassemble(rom: NESRom, entries: Iterable[int]) -> tuple[dict[int,Insn], set[int], list[dict]]:
    decoded: dict[int,Insn] = {}
    labels: set[int] = set()
    unresolved: list[dict] = []
    work = [e for e in entries if e is not None and 0x8000 <= e <= 0xFFFF]
    labels.update(work)
    starts: set[int] = set()
    while work:
        pc = work.pop()
        if pc in starts:
            continue
        starts.add(pc)
        while 0x8000 <= pc <= 0xFFFF:
            if pc in decoded:
                break
            ins = decode_insn(rom, pc)
            if ins is None:
                unresolved.append({'from':pc,'kind':'unmapped-or-banked'})
                break
            decoded[pc] = ins
            nxt = ins.next_addr
            if ins.mnemonic == 'KIL':
                break
            if ins.mnemonic == 'JSR' and ins.operand is not None:
                labels.add(ins.operand)
                if _read(rom, ins.operand) is not None:
                    work.append(ins.operand)
                else:
                    unresolved.append({'from':pc,'target':ins.operand,'kind':'bank-dependent-call'})
                pc = nxt
                continue
            if ins.mnemonic == 'JMP':
                if ins.mode == 'abs' and ins.operand is not None:
                    labels.add(ins.operand)
                    if _read(rom, ins.operand) is not None:
                        work.append(ins.operand)
                    else:
                        unresolved.append({'from':pc,'target':ins.operand,'kind':'bank-dependent-jump'})
                else:
                    unresolved.append({'from':pc,'target':ins.operand,'kind':'indirect-jump'})
                break
            if ins.mnemonic in BRANCHES and ins.operand is not None:
                labels.add(ins.operand)
                if _read(rom, ins.operand) is not None:
                    work.append(ins.operand)
                else:
                    unresolved.append({'from':pc,'target':ins.operand,'kind':'bank-dependent-branch'})
                pc = nxt
                continue
            if ins.mnemonic in TERMINATORS:
                break
            pc = nxt
    return decoded, labels, unresolved


def build_cfg(decoded: dict[int,Insn], entries: Iterable[int]) -> dict[int,BasicBlock]:
    if not decoded:
        return {}
    leaders = {x for x in entries if x in decoded}
    for ins in decoded.values():
        if ins.mnemonic in BRANCHES and ins.operand in decoded:
            leaders.add(ins.operand)
            if ins.next_addr in decoded: leaders.add(ins.next_addr)
        elif ins.mnemonic == 'JMP' and ins.mode == 'abs' and ins.operand in decoded:
            leaders.add(ins.operand)
        elif ins.mnemonic in TERMINATORS:
            if ins.next_addr in decoded: leaders.add(ins.next_addr)
        elif ins.mnemonic == 'JSR':
            if ins.operand in decoded: leaders.add(ins.operand)
    leaders = {x for x in leaders if x in decoded}
    sorted_addrs = sorted(decoded)
    leader_set = set(leaders)
    blocks: dict[int,BasicBlock] = {}
    i = 0
    while i < len(sorted_addrs):
        start = sorted_addrs[i]
        if start not in leader_set:
            i += 1; continue
        insts = []
        j = i
        while j < len(sorted_addrs):
            addr = sorted_addrs[j]
            if j > i and addr in leader_set:
                break
            ins = decoded[addr]
            insts.append(addr)
            if ins.mnemonic in BRANCHES or ins.mnemonic == 'JMP' or ins.mnemonic in TERMINATORS:
                j += 1
                break
            if j + 1 < len(sorted_addrs) and sorted_addrs[j+1] != ins.next_addr:
                j += 1
                break
            j += 1
        last = decoded[insts[-1]]
        succ: list[int] = []
        calls: list[int] = []
        for a in insts:
            ins = decoded[a]
            if ins.mnemonic == 'JSR' and ins.operand in decoded:
                calls.append(ins.operand)
        if last.mnemonic in BRANCHES:
            if last.operand in decoded: succ.append(last.operand)
            if last.next_addr in decoded: succ.append(last.next_addr)
        elif last.mnemonic == 'JMP' and last.mode == 'abs':
            if last.operand in decoded: succ.append(last.operand)
        elif last.mnemonic not in TERMINATORS and last.next_addr in decoded:
            succ.append(last.next_addr)
        blocks[start] = BasicBlock(start, insts[-1], insts, sorted(set(succ)), sorted(set(calls)))
        i = max(j, i+1)
    return blocks


def symbol_for_addr(addr: int) -> str:
    base = addr
    if 0x2000 <= addr <= 0x3FFF:
        base = 0x2000 + ((addr - 0x2000) & 7)
    return PPU_REGS.get(base, f'mem[0x{addr:04X}]')


def operand_expr(ins: Insn) -> str:
    o = ins.operand or 0
    return {
        'imm':f'0x{o:02X}','zp':f'mem[0x{o:02X}]','zpx':f'mem[(0x{o:02X}+X)&0xFF]',
        'zpy':f'mem[(0x{o:02X}+Y)&0xFF]','abs':symbol_for_addr(o),
        'absx':f'mem[(0x{o:04X}+X)&0xFFFF]','absy':f'mem[(0x{o:04X}+Y)&0xFFFF]',
        'indx':f'mem[indirectX(0x{o:02X},X)]','indy':f'mem[(indirectZp(0x{o:02X})+Y)&0xFFFF]',
    }.get(ins.mode, f'0x{o:04X}')


def pseudo_line(ins: Insn, constants: dict[str,int|None] | None = None) -> str:
    m, e = ins.mnemonic, operand_expr(ins)
    target = f'L_{(ins.operand or 0):04X}'
    const = constants or {}
    regval = lambda r: const.get(r)
    if m in ('LDA','LDX','LDY'):
        r = m[-1]
        return f'{r} = {e}; setNZ({r});'
    if m in ('STA','STX','STY'):
        r=m[-1]; v=regval(r)
        return f'{e} = {f"0x{v:02X}" if v is not None else r};'
    if m == 'SAX': return f'{e} = A & X;'
    if m in ('INC','DEC'):
        s='+' if m=='INC' else '-'; return f'{e} = ({e} {s} 1) & 0xFF; setNZ({e});'
    if m in ('ADC','SBC'): return f'A = {m.lower()}8(A, {e}, C);'
    if m in ('AND','ORA','EOR'):
        op={'AND':'&','ORA':'|','EOR':'^'}[m]; return f'A = (A {op} {e}) & 0xFF; setNZ(A);'
    if m in ('CMP','CPX','CPY'):
        r={'CMP':'A','CPX':'X','CPY':'Y'}[m]; return f'compare8({r}, {e});'
    if m == 'BIT': return f'bitTest(A, {e});'
    if m == 'JSR': return f'call {target}();'
    if m == 'JMP': return f'goto {target};' if ins.mode=='abs' else f'goto indirect(0x{(ins.operand or 0):04X});'
    if m in BRANCHES:
        cond={'BPL':'!N','BMI':'N','BVC':'!V','BVS':'V','BCC':'!C','BCS':'C','BNE':'!Z','BEQ':'Z'}[m]
        return f'if ({cond}) goto {target};'
    simple={
        'CLC':'C=0;','SEC':'C=1;','CLI':'I=0;','SEI':'I=1;','CLV':'V=0;','CLD':'D=0;','SED':'D=1;',
        'TAX':'X=A; setNZ(X);','TXA':'A=X; setNZ(A);','TAY':'Y=A; setNZ(Y);','TYA':'A=Y; setNZ(A);',
        'TSX':'X=SP; setNZ(X);','TXS':'SP=X;','INX':'X=(X+1)&0xFF; setNZ(X);','INY':'Y=(Y+1)&0xFF; setNZ(Y);',
        'DEX':'X=(X-1)&0xFF; setNZ(X);','DEY':'Y=(Y-1)&0xFF; setNZ(Y);','PHA':'push(A);','PLA':'A=pop(); setNZ(A);',
        'PHP':'push(P|0x30);','PLP':'P=pop();','RTS':'return;','RTI':'return_from_interrupt();','BRK':'software_interrupt();',
        'NOP':';','KIL':'halt_cpu();',
    }
    if m in simple: return simple[m]
    if m in ('ASL','LSR','ROL','ROR'):
        if ins.mode=='acc': return f'A={m.lower()}8(A);'
        return f'{e}={m.lower()}8({e});'
    if not ins.official:
        return f'unofficial_{m.lower()}({e});'
    return f'/* {ins.text()} */'


def constant_states(decoded: dict[int,Insn], blocks: dict[int,BasicBlock]) -> dict[int,dict[str,int|None]]:
    out: dict[int,dict[str,int|None]] = {}
    for block in blocks.values():
        regs: dict[str,int|None] = {'A':None,'X':None,'Y':None}
        for addr in block.instructions:
            ins = decoded[addr]
            out[addr] = dict(regs)
            m = ins.mnemonic
            if m in ('LDA','LDX','LDY'):
                r=m[-1]; regs[r] = ins.operand if ins.mode=='imm' else None
            elif m == 'TAX': regs['X']=regs['A']
            elif m == 'TXA': regs['A']=regs['X']
            elif m == 'TAY': regs['Y']=regs['A']
            elif m == 'TYA': regs['A']=regs['Y']
            elif m in ('INX','DEX') and regs['X'] is not None:
                regs['X']=(regs['X'] + (1 if m=='INX' else -1)) & 0xFF
            elif m in ('INY','DEY') and regs['Y'] is not None:
                regs['Y']=(regs['Y'] + (1 if m=='INY' else -1)) & 0xFF
            elif m in ('AND','ORA','EOR'):
                if ins.mode=='imm' and regs['A'] is not None:
                    x=ins.operand or 0
                    regs['A']={'AND':regs['A']&x,'ORA':regs['A']|x,'EOR':regs['A']^x}[m] & 0xFF
                else: regs['A']=None
            elif m in ('ADC','SBC','ASL','LSR','ROL','ROR','PLA'):
                if m in ('ASL','LSR','ROL','ROR') and ins.mode != 'acc':
                    pass
                else: regs['A']=None
            elif m in ('LAX',):
                if ins.mode=='imm': regs['A']=regs['X']=ins.operand
                else: regs['A']=regs['X']=None
            elif m in ('JSR','RTI','BRK'):
                regs={'A':None,'X':None,'Y':None}
    return out


def collect_refs(decoded: dict[int,Insn]) -> tuple[dict[str,int], list[dict], dict[str,int]]:
    regs: dict[str,int] = {}
    mapper_writes: list[dict] = []
    unofficial: dict[str,int] = {}
    for ins in decoded.values():
        if not ins.official:
            unofficial[ins.mnemonic] = unofficial.get(ins.mnemonic,0)+1
        if ins.operand is None:
            continue
        if ins.mode in ('abs','absx','absy'):
            a=ins.operand
            base=0x2000+((a-0x2000)&7) if 0x2000<=a<=0x3FFF else a
            name=PPU_REGS.get(base)
            if name: regs[name]=regs.get(name,0)+1
            if ins.mnemonic in WRITE_MNEMONICS and a>=0x8000:
                mapper_writes.append({'address':ins.addr,'target':a,'mnemonic':ins.mnemonic})
    return dict(sorted(regs.items())), mapper_writes, dict(sorted(unofficial.items()))


def make_listing(decoded: dict[int,Insn], labels: set[int], entries: dict[str,int|None]) -> str:
    rev: dict[int,list[str]] = {}
    for name,addr in entries.items():
        if addr is not None: rev.setdefault(addr,[]).append(name.upper())
    lines=['; generated by nes2web','; * marks an unofficial NMOS 6502 opcode','']
    for addr in sorted(decoded):
        if addr in labels:
            lbl='_'.join(rev.get(addr,[])) or f'L_{addr:04X}'
            lines.append(lbl+':')
        ins=decoded[addr]
        raw=' '.join(f'{b:02X}' for b in ins.raw).ljust(9)
        lines.append(f'  {addr:04X}  {raw} {ins.text()}')
    return '\n'.join(lines)+'\n'


def make_pseudo(decoded: dict[int,Insn], labels: set[int], entries: dict[str,int|None], states: dict[int,dict]) -> str:
    rev: dict[int,list[str]]={}
    for name,addr in entries.items():
        if addr is not None: rev.setdefault(addr,[]).append(name.upper())
    lines=['// generated by nes2web','// analysis-oriented pseudocode; labels are preserved where structuring is unsafe','']
    for addr in sorted(decoded):
        if addr in labels:
            lines.append(('_'.join(rev.get(addr,[])) or f'L_{addr:04X}')+':')
        ins=decoded[addr]
        lines.append(f'  {pseudo_line(ins, states.get(addr))} // ${addr:04X}: {ins.text()}')
    return '\n'.join(lines)+'\n'


def make_ir(decoded: dict[int,Insn], blocks: dict[int,BasicBlock], states: dict[int,dict]) -> dict:
    items=[]
    for addr in sorted(decoded):
        ins=decoded[addr]
        items.append({
            'address':addr,'opcode':ins.opcode,'mnemonic':ins.mnemonic,'mode':ins.mode,
            'operand':ins.operand,'official':ins.official,'constants_in':states.get(addr,{}),
            'pseudo':pseudo_line(ins,states.get(addr)),
        })
    return {
        'instructions':items,
        'blocks':[asdict(blocks[k]) for k in sorted(blocks)],
        'edges':[{'from':b.start,'to':s,'kind':'flow'} for b in blocks.values() for s in b.successors]
             +[{'from':b.start,'to':c,'kind':'call'} for b in blocks.values() for c in b.calls],
    }


def analyze_rom(rom: NESRom) -> dict:
    vectors=rom.vectors()
    entries=[v for v in vectors.values() if v is not None]
    decoded,labels,unresolved=recursive_disassemble(rom,entries)
    blocks=build_cfg(decoded,entries)
    states=constant_states(decoded,blocks)
    refs,mapper_writes,unofficial=collect_refs(decoded)
    function_entries=sorted(set(entries)|{i.operand for i in decoded.values() if i.mnemonic=='JSR' and i.operand in decoded})
    call_edges=[]
    for b in blocks.values():
        for c in b.calls: call_edges.append({'from_block':b.start,'to':c})
    return {
        'header':rom.header_info(),
        'notes':rom.static_analysis_notes(),
        'vectors':{k:(f'0x{v:04X}' if v is not None else None) for k,v in vectors.items()},
        'mmc1_vector_candidates':rom.mmc1_vector_candidates() if rom.mapper==1 else None,
        'static':{
            'reachable_instructions':len(decoded),
            'basic_blocks':len(blocks),
            'function_entries':[f'0x{x:04X}' for x in function_entries],
            'unresolved':unresolved,
            'register_refs':refs,
            'mapper_writes':mapper_writes,
            'unofficial_opcodes':unofficial,
            'call_edges':call_edges,
        },
        '_decoded':decoded,'_labels':labels,'_blocks':blocks,'_states':states,'_vectors_raw':vectors,
    }
