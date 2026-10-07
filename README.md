# NES2Web

`nes2web` turns an NES/Famicom ROM into a **playable static web project plus a reverse-engineering workspace**.

It is local-first: the ROM is analyzed on your machine. The generated web player fetches the pinned JSNES 2.1.0 browser runtime only when you run `prepare.bat` / `prepare.ps1` for the first time.

## What it generates

```text
output/<rom-name>/
├─ analysis.json        ROM/header/mapper/static-analysis summary
├─ disassembly.asm      reachable 6502 disassembly
├─ pseudo.js            simplified analysis-oriented pseudocode
├─ ir.json              instruction IR + basic blocks + CFG edges
├─ cfg.dot              Graphviz control-flow graph
├─ report.html          standalone reverse-engineering report
├─ assets/
│  ├─ chr-all.png
│  ├─ pattern-table-*.png
│  ├─ chr-bank-*.png
│  └─ tiles.json
├─ recompiler/
│  ├─ reference.js      block-level static translation
│  └─ module.wat        experimental WebAssembly-text backend
└─ web/
   ├─ game.nes
   ├─ index.html
   ├─ app.js
   ├─ style.css
   ├─ analysis.json / disassembly.asm / pseudo.js / ir.json
   ├─ assets/
   ├─ prepare.bat / prepare.ps1
   └─ start.bat
```

## Quick start on Windows

Drag your `.nes` file onto `start.bat`.

Or:

```powershell
python -m nes2web port game.nes -o output\game
output\game\web\start.bat
```

You can also install the CLI:

```powershell
python -m pip install -e .
nes2web port game.nes -o output\game
```

## Commands

```text
nes2web info game.nes
nes2web extract game.nes -o assets
nes2web port game.nes -o output/game
nes2web serve output/game/web
```

## Static analysis

The analyzer understands all 256 NMOS 6502 opcode byte lengths, including unofficial opcodes. Official instructions are distinguished from unofficial ones instead of treating unknown bytes as one-byte data and losing synchronization.

For code it can safely map, it builds:

- recursive reachable-code disassembly from interrupt vectors
- function candidates from vectors and `JSR`
- basic blocks
- CFG flow/call edges
- PPU/APU/controller register references
- cartridge mapper-write sites
- local A/X/Y constant propagation
- simplified pseudocode
- instruction-level JSON IR

`KIL/STP` terminates a path. Indirect jumps and runtime-dependent bank targets are reported as unresolved rather than guessed.

## Mapper handling

The tool recognizes every mapper number in the header, and has explicit static-mapping knowledge for the common first five:

| Mapper | Board | Static analysis behavior |
|---:|---|---|
| 0 | NROM | Fixed 16/32 KiB PRG; full deterministic mapping |
| 1 | MMC1/SxROM | Reports per-bank vector candidates; does not guess power-on bank state |
| 2 | UxROM | Safely follows fixed `$C000-$FFFF`; banked `$8000-$BFFF` is marked dynamic |
| 3 | CNROM | PRG is fixed; CHR banks are extracted separately |
| 4 | MMC3/TxROM | Safely follows fixed last 8 KiB at `$E000-$FFFF`; dynamic PRG windows stay unresolved |

The **playable web output is a separate compatibility path** and uses JSNES, which supports substantially more mapper/hardware behavior than the static analyzer.

## CHR / “texture” extraction

NES graphics are not conventional textures. CHR tiles are 8×8 pixels at 2 bits per pixel, 16 bytes per tile. NES2Web exports diagnostic grayscale atlases because the final RGB colors come from runtime palette RAM and palette selection.

For CHR-RAM cartridges there is no complete tile set stored as CHR-ROM, so NES2Web explicitly reports that runtime PPU-write tracing is required instead of fabricating images.

## About the static recompiler

`recompiler/reference.js` is a readable block-level translation of deterministic reachable code.

`recompiler/module.wat` is an **experimental** static backend: decoded opcodes and operands are hardcoded into WebAssembly blocks, while exact 2A03/bus semantics are imported. It is intentionally not the default playable backend yet. NES timing couples CPU, PPU, APU, DMA, interrupts and mapper state; replacing only the CPU with an approximate backend would make compatibility worse.

The current architecture therefore gives you both:

1. a web port that actually runs via a mature emulator backend; and
2. progressively higher-level extracted code/IR suitable for replacing emulator components later.

## Legal note

Use this with homebrew, your own ROMs, or ROM images you are authorized to use. The tool does not grant rights to redistribute copyrighted game ROMs or extracted assets.

## References

See [`SOURCES.md`](SOURCES.md). The implementation intentionally follows primary/reference documentation for NES header, CPU and mapper behavior instead of guessing hardware details.
