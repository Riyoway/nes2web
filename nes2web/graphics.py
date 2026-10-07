from __future__ import annotations
import json, struct, zlib
from pathlib import Path
from .rom import NESRom


def _png(width:int,height:int,rgba:bytes)->bytes:
    sig=b'\x89PNG\r\n\x1a\n'
    def chunk(t:bytes,d:bytes)->bytes:
        return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    stride=width*4
    scan=bytearray()
    for y in range(height):
        scan.append(0); scan.extend(rgba[y*stride:(y+1)*stride])
    return sig+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(bytes(scan),9))+chunk(b'IEND',b'')


def decode_tiles(chr_data:bytes,start_tile:int,tile_count:int,cols:int=16,scale:int=1)->tuple[int,int,bytes]:
    rows=max(1,(tile_count+cols-1)//cols)
    w,h=cols*8*scale,rows*8*scale
    pix=bytearray(w*h*4)
    shades=[16,96,176,255]
    for n in range(tile_count):
        base=(start_tile+n)*16
        if base+16>len(chr_data): break
        tx=(n%cols)*8*scale; ty=(n//cols)*8*scale
        for y in range(8):
            p0,p1=chr_data[base+y],chr_data[base+y+8]
            for x in range(8):
                bit=7-x; ci=((p0>>bit)&1)|(((p1>>bit)&1)<<1); s=shades[ci]
                for sy in range(scale):
                    for sx in range(scale):
                        off=((ty+y*scale+sy)*w+(tx+x*scale+sx))*4
                        pix[off:off+4]=bytes((s,s,s,255))
    return w,h,bytes(pix)


def export_chr(rom:NESRom,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    meta={'type':'CHR-RAM' if not rom.chr else 'CHR-ROM','files':[],'tile_count':len(rom.chr)//16,'banks_8k':rom.chr_banks_8k}
    if not rom.chr:
        (out/'CHR-RAM.txt').write_text(
            'This cartridge has no CHR-ROM. Graphics are uploaded to CHR-RAM at runtime, so a static ROM-only extractor cannot truthfully reconstruct all tiles.\n',
            encoding='utf-8')
        meta['files'].append('CHR-RAM.txt')
        (out/'tiles.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
        return meta
    total=len(rom.chr)//16
    w,h,p=decode_tiles(rom.chr,0,total,16,2)
    (out/'chr-all.png').write_bytes(_png(w,h,p)); meta['files'].append('chr-all.png')
    # 4 KiB pattern tables (256 tiles each)
    for table in range((len(rom.chr)+4095)//4096):
        start=table*256; count=min(256,total-start)
        if count<=0: break
        w,h,p=decode_tiles(rom.chr,start,count,16,2)
        name=f'pattern-table-{table:02d}.png'; (out/name).write_bytes(_png(w,h,p)); meta['files'].append(name)
    # 8 KiB CHR banks are useful for CNROM/MMC-family inspection.
    for bank in range((len(rom.chr)+8191)//8192):
        start=bank*512; count=min(512,total-start)
        if count<=0: break
        w,h,p=decode_tiles(rom.chr,start,count,16,1)
        name=f'chr-bank-{bank:02d}.png'; (out/name).write_bytes(_png(w,h,p)); meta['files'].append(name)
    tiles=[]
    for i in range(total):
        tiles.append({'id':i,'byte_offset':i*16,'pattern_table':i//256,'index_in_table':i%256})
    (out/'tiles.json').write_text(json.dumps({'meta':meta,'tiles':tiles},indent=2),encoding='utf-8')
    meta['files'].append('tiles.json')
    (out/'README.txt').write_text(
        'NES CHR stores 2-bit pixel indices, not final RGB colors. The PNG files use diagnostic grayscale. '
        'Actual colors depend on runtime palette RAM and attribute/sprite palette selection.\n',encoding='utf-8')
    meta['files'].append('README.txt')
    return meta
