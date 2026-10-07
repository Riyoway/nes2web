from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

MAPPER_NAMES = {
    0: 'NROM', 1: 'MMC1 / SxROM', 2: 'UxROM', 3: 'CNROM', 4: 'MMC3 / TxROM'
}


def _nes2_size(lsb: int, msb_nibble: int, unit: int) -> int:
    if msb_nibble != 0xF:
        return (((msb_nibble << 8) | lsb) * unit)
    exponent = lsb >> 2
    multiplier = ((lsb & 0x03) * 2) + 1
    return (1 << exponent) * multiplier


def _shift_size(nibble: int) -> int:
    return 0 if nibble == 0 else 64 << nibble

@dataclass
class NESRom:
    path: Path
    raw: bytes
    header: bytes
    format: str
    mapper: int
    submapper: int
    prg: bytes
    chr: bytes
    trainer: bytes
    misc: bytes
    mirroring: str
    battery: bool
    four_screen: bool
    console_type: int
    timing: str
    prg_ram: int
    prg_nvram: int
    chr_ram: int
    chr_nvram: int

    @classmethod
    def load(cls, path: Path) -> 'NESRom':
        raw = path.read_bytes()
        if len(raw) < 16 or raw[:4] != b'NES\x1a':
            raise ValueError('Not an iNES/NES 2.0 ROM (missing NES\\x1A header)')
        h = raw[:16]
        flags6, flags7 = h[6], h[7]
        nes2 = (flags7 & 0x0C) == 0x08
        mapper = (flags6 >> 4) | (flags7 & 0xF0)
        submapper = 0
        console_type = flags7 & 0x03
        if nes2:
            mapper |= (h[8] & 0x0F) << 8
            submapper = h[8] >> 4
            prg_size = _nes2_size(h[4], h[9] & 0x0F, 16384)
            chr_size = _nes2_size(h[5], (h[9] >> 4) & 0x0F, 8192)
            prg_ram = _shift_size(h[10] & 0x0F)
            prg_nvram = _shift_size(h[10] >> 4)
            chr_ram = _shift_size(h[11] & 0x0F)
            chr_nvram = _shift_size(h[11] >> 4)
            timing = {0:'NTSC',1:'PAL',2:'multi-region',3:'Dendy'}.get(h[12] & 3, 'unknown')
            fmt = 'NES 2.0'
        else:
            prg_size = h[4] * 16384
            chr_size = h[5] * 8192
            prg_ram = (h[8] or 1) * 8192
            prg_nvram = 0
            chr_ram = 8192 if chr_size == 0 else 0
            chr_nvram = 0
            timing = 'PAL' if (h[9] & 1) else 'NTSC'
            fmt = 'iNES 1.0'

        off = 16
        trainer = b''
        if flags6 & 0x04:
            if len(raw) < off + 512:
                raise ValueError('ROM declares a trainer but is truncated')
            trainer = raw[off:off+512]
            off += 512
        end_prg = off + prg_size
        end_chr = end_prg + chr_size
        if end_chr > len(raw):
            raise ValueError('ROM is truncated according to header PRG/CHR sizes')
        prg = raw[off:end_prg]
        chr_data = raw[end_prg:end_chr]
        misc = raw[end_chr:]
        mirroring = 'four-screen' if flags6 & 0x08 else ('vertical' if flags6 & 1 else 'horizontal')
        return cls(
            path=path, raw=raw, header=h, format=fmt, mapper=mapper, submapper=submapper,
            prg=prg, chr=chr_data, trainer=trainer, misc=misc, mirroring=mirroring,
            battery=bool(flags6 & 2), four_screen=bool(flags6 & 8), console_type=console_type,
            timing=timing, prg_ram=prg_ram, prg_nvram=prg_nvram, chr_ram=chr_ram, chr_nvram=chr_nvram,
        )

    @property
    def mapper_name(self) -> str:
        return MAPPER_NAMES.get(self.mapper, f'Mapper {self.mapper}')

    @property
    def prg_banks_16k(self) -> int:
        return (len(self.prg) + 0x3FFF) // 0x4000

    @property
    def prg_banks_8k(self) -> int:
        return (len(self.prg) + 0x1FFF) // 0x2000

    @property
    def chr_banks_8k(self) -> int:
        return (len(self.chr) + 0x1FFF) // 0x2000 if self.chr else 0

    def header_info(self) -> dict:
        return {
            'source': self.path.name,
            'format': self.format,
            'mapper': self.mapper,
            'mapper_name': self.mapper_name,
            'submapper': self.submapper,
            'prg_bytes': len(self.prg),
            'chr_bytes': len(self.chr),
            'prg_ram_bytes': self.prg_ram,
            'prg_nvram_bytes': self.prg_nvram,
            'chr_ram_bytes': self.chr_ram,
            'chr_nvram_bytes': self.chr_nvram,
            'mirroring': self.mirroring,
            'battery': self.battery,
            'trainer': bool(self.trainer),
            'misc_bytes': len(self.misc),
            'timing': self.timing,
            'console_type': self.console_type,
        }

    def prg_read_physical(self, offset: int) -> int:
        if not 0 <= offset < len(self.prg):
            raise IndexError(offset)
        return self.prg[offset]

    def deterministic_cpu_read(self, addr: int) -> int | None:
        '''Read only when mapping is deterministic without knowing runtime mapper state.'''
        if not 0x8000 <= addr <= 0xFFFF or not self.prg:
            return None
        if self.mapper in (0, 3):
            if len(self.prg) == 0x4000:
                return self.prg[(addr - 0x8000) & 0x3FFF]
            if len(self.prg) >= 0x8000:
                return self.prg[(addr - 0x8000) % len(self.prg)]
        elif self.mapper == 2:
            if addr >= 0xC000 and len(self.prg) >= 0x4000:
                return self.prg[len(self.prg)-0x4000 + (addr-0xC000)]
        elif self.mapper == 4:
            if addr >= 0xE000 and len(self.prg) >= 0x2000:
                return self.prg[len(self.prg)-0x2000 + (addr-0xE000)]
        return None

    def deterministic_vector(self, vector_addr: int) -> int | None:
        lo = self.deterministic_cpu_read(vector_addr)
        hi = self.deterministic_cpu_read(vector_addr + 1)
        if lo is None or hi is None:
            return None
        return lo | (hi << 8)

    def vectors(self) -> dict[str, int | None]:
        return {
            'nmi': self.deterministic_vector(0xFFFA),
            'reset': self.deterministic_vector(0xFFFC),
            'irq': self.deterministic_vector(0xFFFE),
        }

    def mmc1_vector_candidates(self) -> dict[str, list[dict]]:
        '''MMC1 power-on mapping can vary by revision. Return candidates from every 16 KiB bank.'''
        out = {'nmi': [], 'reset': [], 'irq': []}
        if self.mapper != 1:
            return out
        vec_offsets = {'nmi':0x3FFA, 'reset':0x3FFC, 'irq':0x3FFE}
        for bank in range(self.prg_banks_16k):
            base = bank * 0x4000
            if base + 0x4000 > len(self.prg):
                continue
            for name, rel in vec_offsets.items():
                lo, hi = self.prg[base+rel], self.prg[base+rel+1]
                addr = lo | (hi << 8)
                if 0x8000 <= addr <= 0xFFFF:
                    out[name].append({'bank16k': bank, 'target': addr})
        return out

    def static_analysis_notes(self) -> list[str]:
        notes: list[str] = []
        if self.mapper == 0:
            notes.append('NROM has fixed PRG mapping; static CPU address mapping is deterministic.')
        elif self.mapper == 2:
            notes.append('UxROM fixes the last 16 KiB at $C000-$FFFF; $8000-$BFFF depends on the selected bank.')
        elif self.mapper == 3:
            notes.append('CNROM PRG mapping is fixed like NROM; CHR is bank-switched at runtime.')
        elif self.mapper == 4:
            notes.append('MMC3 fixes the last 8 KiB at $E000-$FFFF; other PRG windows depend on mapper registers.')
        elif self.mapper == 1:
            notes.append('MMC1 power-on PRG mode varies by revision; vector candidates are reported per 16 KiB bank instead of guessing one mapping.')
        else:
            notes.append('Mapper-specific static CPU mapping is not implemented; header/graphics/raw scans remain available.')
        return notes
