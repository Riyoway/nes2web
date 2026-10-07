# Limits

A general NES ROM cannot be losslessly converted back into its original C/assembly source. Symbol names, comments, source structure and many data/code boundaries were not stored in the ROM.

Static recovery is additionally constrained by mapper bank state, indirect jumps, runtime-generated CHR-RAM, self-selected function tables, IRQ timing and PPU/APU side effects.

NES2Web therefore uses a conservative policy: recover what is provable, expose uncertainty, and keep a compatible emulator path for playable output.
