import json, tempfile, unittest
from pathlib import Path
from nes2web.opcodes import OPCODES, OFFICIAL
from nes2web.rom import NESRom
from nes2web.analysis import analyze_rom, make_pseudo
from nes2web.generator import generate


def make_nrom(path:Path):
    h=bytearray(16); h[:4]=b'NES\x1a'; h[4]=1; h[5]=1
    prg=bytearray([0xEA]*0x4000)
    # $C000: LDA #$80; STA $2000; JSR $C010; RTS
    prg[0:9]=bytes([0xA9,0x80,0x8D,0x00,0x20,0x20,0x10,0xC0,0x60])
    prg[0x10:0x13]=bytes([0xA2,0x03,0x60])
    prg[-6:]=bytes([0x00,0xC0,0x00,0xC0,0x00,0xC0])
    path.write_bytes(bytes(h)+bytes(prg)+bytes([0])*0x2000)


def make_uxrom(path:Path):
    h=bytearray(16); h[:4]=b'NES\x1a'; h[4]=4; h[5]=0; h[6]=0x20
    prg=bytearray([0xEA]*(4*0x4000))
    base=3*0x4000
    prg[base:base+2]=bytes([0x60,0xEA])
    prg[base+0x3FFA:base+0x4000]=bytes([0x00,0xC0,0x00,0xC0,0x00,0xC0])
    path.write_bytes(bytes(h)+bytes(prg))

class CoreTests(unittest.TestCase):
    def test_opcode_matrix(self):
        self.assertEqual(len(OPCODES),256); self.assertEqual(len(OFFICIAL),151)
        self.assertEqual((OPCODES[0x80].mnemonic,OPCODES[0x80].size,OPCODES[0x80].official),('NOP',2,False))
        self.assertEqual(OPCODES[0x02].mnemonic,'KIL')

    def test_nrom_pipeline(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); rp=root/'test.nes'; make_nrom(rp)
            rom=NESRom.load(rp); self.assertEqual(rom.mapper,0); self.assertEqual(rom.vectors()['reset'],0xC000)
            a=analyze_rom(rom); self.assertGreaterEqual(a['static']['reachable_instructions'],6)
            self.assertIn('PPUCTRL',a['static']['register_refs'])
            out=root/'out'; clean=generate(rom,out)
            self.assertTrue((out/'assets'/'chr-all.png').read_bytes().startswith(b'\x89PNG'))
            self.assertTrue((out/'web'/'index.html').exists()); self.assertTrue((out/'recompiler'/'module.wat').exists())
            pseudo=(out/'pseudo.js').read_text(); self.assertIn('PPUCTRL = 0x80',pseudo)
            ir=json.loads((out/'ir.json').read_text()); self.assertTrue(ir['blocks'])
            self.assertEqual(clean['header']['mapper_name'],'NROM')

    def test_uxrom_fixed_bank_vectors(self):
        with tempfile.TemporaryDirectory() as td:
            rp=Path(td)/'u.nes'; make_uxrom(rp); rom=NESRom.load(rp)
            self.assertEqual(rom.mapper,2); self.assertEqual(rom.vectors()['reset'],0xC000)
            self.assertIsNone(rom.deterministic_cpu_read(0x8000)); self.assertIsNotNone(rom.deterministic_cpu_read(0xC000))

    def test_nes2_exponent_size(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'e.nes'; h=bytearray(16); h[:4]=b'NES\x1a'; h[4]=(14<<2); h[5]=0; h[7]=0x08; h[9]=0x0F
            p.write_bytes(bytes(h)+bytes([0])*16384)
            r=NESRom.load(p); self.assertEqual(r.format,'NES 2.0'); self.assertEqual(len(r.prg),16384)

if __name__=='__main__': unittest.main()
