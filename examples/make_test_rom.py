from pathlib import Path
h=bytearray(16); h[:4]=b'NES\x1a'; h[4]=1; h[5]=1
prg=bytearray([0xEA]*0x4000)
# Tiny synthetic NROM: initialize PPUCTRL and return.
prg[:6]=bytes([0xA9,0x80,0x8D,0x00,0x20,0x60])
prg[-6:]=bytes([0x00,0xC0,0x00,0xC0,0x00,0xC0])
chr_data=bytearray(0x2000)
for tile in range(512):
    base=tile*16
    for y in range(8):
        chr_data[base+y]=0xAA if (tile+y)&1 else 0x55
        chr_data[base+y+8]=0x00
out=Path(__file__).with_name('synthetic-nrom.nes')
out.write_bytes(bytes(h)+bytes(prg)+bytes(chr_data))
print(out)
