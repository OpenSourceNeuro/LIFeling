# LIFeling SPICE cold-start separation patch v9

Run `python -B .\apply_v9.py` from the `SPICE` directory.

This patch changes the full-board N06 cold-start simulation from the dynamic-SOC
CR2032 subcircuit to a fixed-SOC Thevenin equivalent:

- OCV at SOC 0.75: 2.92125 V
- series resistance: 35 ohm
- source ramp: 0 to 2.92125 V over 1 ms
- simulation horizon: remains 50 ms

The dynamic battery library model is retained. It should be validated in a
separate battery-only deck, rather than inside the complete 1 MHz switching
board, because the two models operate on radically different timescales.
