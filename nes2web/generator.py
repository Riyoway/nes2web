from __future__ import annotations
import html, json, shutil, subprocess
from pathlib import Path
from .rom import NESRom
from .analysis import analyze_rom, make_listing, make_pseudo, make_ir
from .graphics import export_chr
from .recompiler import emit_reference_js, emit_wat


def _clean_analysis(a:dict)->dict:
    return {k:v for k,v in a.items() if not k.startswith('_')}


def _cfg_dot(blocks)->str:
    lines=['digraph CFG {','  rankdir=TB;','  node [shape=box,fontname="monospace"];']
    for start,b in sorted(blocks.items()):
        lines.append(f'  n{start:04X} [label="${start:04X}-${b.end:04X}\\n{len(b.instructions)} insn"];')
    for start,b in sorted(blocks.items()):
        for s in b.successors:
            if s in blocks: lines.append(f'  n{start:04X} -> n{s:04X};')
        for c in b.calls:
            if c in blocks: lines.append(f'  n{start:04X} -> n{c:04X} [style=dashed,label="call"];')
    lines.append('}')
    return '\n'.join(lines)+'\n'

WEB_CSS = r'''
:root{font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#090909;color:#eee}*{box-sizing:border-box}body{margin:0}.bar{height:56px;border-bottom:1px solid #262626;display:flex;align-items:center;justify-content:space-between;padding:0 18px;position:sticky;top:0;background:#090909;z-index:2}.brand{font-weight:700;letter-spacing:-.03em}.muted{color:#888}.layout{display:grid;grid-template-columns:minmax(500px,1fr) 420px;min-height:calc(100vh - 56px)}main{padding:22px;display:flex;flex-direction:column;align-items:center;gap:12px}.screen{width:min(820px,100%);aspect-ratio:256/240;background:#000;border:1px solid #292929;border-radius:10px;overflow:hidden;display:flex;align-items:center;justify-content:center}.screen canvas{width:100%!important;height:100%!important;image-rendering:pixelated}.buttons{display:flex;gap:8px}button{border:1px solid #333;background:#ededed;color:#111;border-radius:7px;padding:8px 12px;font-weight:650;cursor:pointer}button.secondary{background:#111;color:#ddd}button:disabled{opacity:.4}.status{font:12px ui-monospace,monospace;color:#aaa}aside{border-left:1px solid #262626;padding:16px;overflow:auto;max-height:calc(100vh - 56px);position:sticky;top:56px}.tabs{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:12px}.tabs button{font-size:11px;padding:6px 9px}.panel{display:none}.panel.active{display:block}pre{font:11px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;background:#101010;border:1px solid #252525;border-radius:8px;padding:11px;white-space:pre-wrap;overflow:auto}.chr{display:grid;grid-template-columns:1fr 1fr;gap:7px}.chr img{width:100%;background:#fff;border:1px solid #333;border-radius:5px;image-rendering:pixelated}h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#999}a{color:#ddd}@media(max-width:950px){.layout{grid-template-columns:1fr}aside{position:static;max-height:none;border-left:0;border-top:1px solid #262626}.screen{width:100%}}
'''

WEB_APP = r'''
const $=q=>document.querySelector(q);let browser=null;
async function bootMeta(){const a=await (await fetch('./analysis.json')).json();$('#overview').textContent=JSON.stringify(a,null,2);$('#disasm').textContent=await (await fetch('./disassembly.asm')).text();$('#pseudo').textContent=await (await fetch('./pseudo.js')).text();$('#ir').textContent=JSON.stringify(await (await fetch('./ir.json')).json(),null,2);for(const n of (a.graphics?.files||[]).filter(x=>x.endsWith('.png'))){const im=document.createElement('img');im.src='./assets/'+n;im.title=n;$('#chr').appendChild(im)}}
$('#start').onclick=async()=>{try{$('#start').disabled=true;$('#status').textContent='loading…';if(!window.jsnes?.Browser)throw new Error('JSNES is missing. Run prepare.bat or prepare.ps1.');const rom=new Uint8Array(await (await fetch('./game.nes')).arrayBuffer());browser?.destroy();browser=new jsnes.Browser({container:$('#nes'),onError:e=>{$('#status').textContent=String(e)}});browser.loadROM(rom);$('#reset').disabled=false;$('#status').textContent='running · arrows · Z/Y=B · X=A · Enter=Start · Right Ctrl=Select'}catch(e){console.error(e);$('#status').textContent='error: '+e;$('#start').disabled=false}};
$('#reset').onclick=()=>browser?.nes?.reset();
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));document.querySelectorAll('[data-tab]').forEach(x=>x.classList.add('secondary'));$('#'+b.dataset.tab).classList.add('active');b.classList.remove('secondary')});bootMeta().catch(e=>$('#status').textContent=String(e));
'''

WEB_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NES2Web Port</title><link rel="stylesheet" href="./style.css"></head><body><header class="bar"><div class="brand">NES2Web <span class="muted">generated port</span></div><div class="buttons"><button id="reset" class="secondary" disabled>Reset</button><button id="start">Start</button></div></header><div class="layout"><main><div id="nes" class="screen"></div><div id="status" class="status">ready</div></main><aside><div class="tabs"><button data-tab="overview">Overview</button><button data-tab="graphics" class="secondary">CHR</button><button data-tab="disassembly" class="secondary">ASM</button><button data-tab="pseudocode" class="secondary">Pseudo</button><button data-tab="irpanel" class="secondary">IR</button></div><section id="overview" class="panel active"><pre id="overview">loading…</pre></section><section id="graphics" class="panel"><div id="chr" class="chr"></div></section><section id="disassembly" class="panel"><pre id="disasm"></pre></section><section id="pseudocode" class="panel"><pre id="pseudo"></pre></section><section id="irpanel" class="panel"><pre id="ir"></pre></section></aside></div><script src="./vendor/jsnes.min.js"></script><script src="./app.js"></script></body></html>'''
WEB_HTML=WEB_HTML.replace('<section id="overview" class="panel active"><pre id="overview">','<section id="overviewPanel" class="panel active"><pre id="overview">').replace('data-tab="overview"','data-tab="overviewPanel"')


def _report_html(clean:dict, listing:str, pseudo:str, ir:dict, graphics:dict)->str:
    data=html.escape(json.dumps(clean,indent=2))
    asm=html.escape(listing); ps=html.escape(pseudo); irs=html.escape(json.dumps(ir,indent=2))
    imgs=''.join(f'<figure><img src="assets/{html.escape(n)}"><figcaption>{html.escape(n)}</figcaption></figure>' for n in graphics.get('files',[]) if n.endswith('.png'))
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>NES2Web Report</title><style>{WEB_CSS}.report{{max-width:1200px;margin:auto;padding:24px}}.report .chr{{grid-template-columns:repeat(3,1fr)}}figure{{margin:0}}figcaption{{font:11px monospace;color:#999}}</style></head><body><div class="report"><h1>NES2Web report</h1><h2>Analysis</h2><pre>{data}</pre><h2>CHR</h2><div class="chr">{imgs}</div><h2>Disassembly</h2><pre>{asm}</pre><h2>Pseudocode</h2><pre>{ps}</pre><h2>IR</h2><pre>{irs}</pre></div></body></html>'''


def generate(rom:NESRom,out:Path)->dict:
    out.mkdir(parents=True,exist_ok=True)
    a=analyze_rom(rom)
    graphics=export_chr(rom,out/'assets')
    a['graphics']=graphics
    decoded=a['_decoded']; labels=a['_labels']; blocks=a['_blocks']; states=a['_states']; vectors=a['_vectors_raw']
    listing=make_listing(decoded,labels,vectors)
    pseudo=make_pseudo(decoded,labels,vectors,states)
    ir=make_ir(decoded,blocks,states)
    clean=_clean_analysis(a)
    (out/'analysis.json').write_text(json.dumps(clean,indent=2),encoding='utf-8')
    (out/'disassembly.asm').write_text(listing,encoding='utf-8')
    (out/'pseudo.js').write_text(pseudo,encoding='utf-8')
    (out/'ir.json').write_text(json.dumps(ir,indent=2),encoding='utf-8')
    (out/'cfg.dot').write_text(_cfg_dot(blocks),encoding='utf-8')
    if shutil.which('dot'):
        try:
            subprocess.run(['dot','-Tsvg',str(out/'cfg.dot'),'-o',str(out/'cfg.svg')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError):
            pass
    recomp=out/'recompiler'; recomp.mkdir(exist_ok=True)
    (recomp/'reference.js').write_text(emit_reference_js(decoded,blocks,states),encoding='utf-8')
    (recomp/'module.wat').write_text(emit_wat(decoded,blocks),encoding='utf-8')
    (recomp/'README.md').write_text('''# Experimental static recompiler\n\n`reference.js` is a readable block-level translation. `module.wat` hardcodes decoded instructions and imports exact CPU/bus semantics as `nes.exec`. This backend is intentionally not used for the playable build yet: replacing the CPU without equally exact PPU/APU/mapper timing would reduce compatibility.\n''',encoding='utf-8')
    (out/'report.html').write_text(_report_html(clean,listing,pseudo,ir,graphics),encoding='utf-8')
    build_web(rom,out,clean)
    return clean


def build_web(rom:NESRom,out:Path,clean:dict)->None:
    web=out/'web'; (web/'assets').mkdir(parents=True,exist_ok=True); (web/'vendor').mkdir(parents=True,exist_ok=True)
    shutil.copy2(rom.path,web/'game.nes')
    for name in ('analysis.json','disassembly.asm','pseudo.js','ir.json'):
        shutil.copy2(out/name,web/name)
    for p in (out/'assets').iterdir():
        if p.is_file(): shutil.copy2(p,web/'assets'/p.name)
    (web/'index.html').write_text(WEB_HTML,encoding='utf-8')
    (web/'style.css').write_text(WEB_CSS,encoding='utf-8')
    (web/'app.js').write_text(WEB_APP,encoding='utf-8')
    (web/'prepare.bat').write_text('@echo off\r\ncd /d %~dp0\r\nif not exist vendor mkdir vendor\r\npowershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri \'https://unpkg.com/jsnes@2.1.0/dist/jsnes.min.js\' -OutFile \'vendor\\jsnes.min.js\'"\r\n',encoding='utf-8')
    (web/'prepare.ps1').write_text("$ErrorActionPreference='Stop'\nNew-Item -ItemType Directory -Force vendor | Out-Null\nInvoke-WebRequest -UseBasicParsing -Uri 'https://unpkg.com/jsnes@2.1.0/dist/jsnes.min.js' -OutFile 'vendor/jsnes.min.js'\n",encoding='utf-8')
    (web/'start.bat').write_text('@echo off\r\ncd /d %~dp0\r\nif not exist vendor\\jsnes.min.js call prepare.bat\r\nif not exist vendor\\jsnes.min.js exit /b 1\r\nstart "" http://127.0.0.1:8080/\r\npython -m http.server 8080 --bind 127.0.0.1\r\n',encoding='utf-8')
    (web/'THIRD_PARTY.md').write_text('# JSNES\n\nThe playable compatibility backend uses JSNES 2.1.0 (Apache-2.0), fetched by `prepare.bat` / `prepare.ps1`.\nSource: https://github.com/bfirsh/jsnes\n',encoding='utf-8')
