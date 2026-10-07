# Synthetic test ROM

Run:

```powershell
python make_test_rom.py
python -m nes2web port synthetic-nrom.nes -o ../output/synthetic
```

The generated ROM contains only synthetic code/CHR data and is intended for pipeline testing.
