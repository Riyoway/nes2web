# Architecture

```text
.nes
 ├─ header parser (iNES / NES 2.0)
 ├─ mapper-aware deterministic address view
 ├─ 256-opcode decoder
 │   └─ recursive disassembly
 │       ├─ functions
 │       ├─ basic blocks / CFG
 │       ├─ constant state
 │       ├─ pseudocode
 │       └─ JSON IR
 ├─ CHR decoder
 │   ├─ pattern tables
 │   ├─ 8 KiB bank atlases
 │   └─ tile metadata
 ├─ experimental static backend
 │   ├─ reference.js
 │   └─ module.wat
 └─ web generator
     ├─ JSNES compatibility runtime
     └─ integrated analysis viewer
```

The key rule is **never resolve a bank-dependent CPU address by assumption**. A static mapping function returns `None` when mapper runtime state is required; callers preserve that as an unresolved edge.
