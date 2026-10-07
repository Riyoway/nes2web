from __future__ import annotations
import argparse, json, sys, webbrowser
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from .rom import NESRom
from .generator import generate
from .graphics import export_chr


def _rom(path:str)->NESRom:
    return NESRom.load(Path(path).expanduser().resolve())


def cmd_info(args):
    r=_rom(args.rom)
    d=r.header_info(); d['notes']=r.static_analysis_notes(); d['vectors']={k:(f'0x{v:04X}' if v is not None else None) for k,v in r.vectors().items()}
    if r.mapper==1: d['mmc1_vector_candidates']=r.mmc1_vector_candidates()
    print(json.dumps(d,indent=2))


def cmd_extract(args):
    r=_rom(args.rom); out=Path(args.out); print(json.dumps(export_chr(r,out),indent=2)); print(f'written: {out.resolve()}')


def cmd_port(args):
    r=_rom(args.rom); out=Path(args.out)
    result=generate(r,out)
    print(f'generated: {out.resolve()}')
    print(f'mapper: {result["header"]["mapper"]} ({result["header"]["mapper_name"]})')
    print(f'static reachable instructions: {result["static"]["reachable_instructions"]}')
    print(f'web: {(out/"web").resolve()}')
    print(f'report: {(out/"report.html").resolve()}')


def cmd_serve(args):
    root=Path(args.directory).resolve()
    if not root.exists(): raise ValueError(f'not found: {root}')
    handler=partial(SimpleHTTPRequestHandler,directory=str(root))
    url=f'http://127.0.0.1:{args.port}/'
    print(url)
    if not args.no_browser: webbrowser.open(url)
    ThreadingHTTPServer(('127.0.0.1',args.port),handler).serve_forever()


def build_parser():
    p=argparse.ArgumentParser(prog='nes2web',description='NES ROM -> web-port + reverse-engineering workspace')
    p.add_argument('--version',action='version',version='nes2web 0.2.0')
    s=p.add_subparsers(dest='command',required=True)
    x=s.add_parser('info',help='parse the ROM header and mapper'); x.add_argument('rom'); x.set_defaults(fn=cmd_info)
    x=s.add_parser('extract',help='extract CHR graphics'); x.add_argument('rom'); x.add_argument('-o','--out',default='nes2web-assets'); x.set_defaults(fn=cmd_extract)
    x=s.add_parser('port',help='generate analysis, IR, static-recompiler artifacts and a playable web project'); x.add_argument('rom'); x.add_argument('-o','--out',default='nes2web-output'); x.set_defaults(fn=cmd_port)
    x=s.add_parser('serve',help='serve an already generated web directory'); x.add_argument('directory',nargs='?',default='nes2web-output/web'); x.add_argument('--port',type=int,default=8080); x.add_argument('--no-browser',action='store_true'); x.set_defaults(fn=cmd_serve)
    return p


def main(argv=None)->int:
    try:
        a=build_parser().parse_args(argv); a.fn(a); return 0
    except KeyboardInterrupt: return 130
    except (OSError,ValueError,IndexError) as e:
        print(f'error: {e}',file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
