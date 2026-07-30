# Third-party model and redistribution notes

- `models/provided/MCP6001.txt` contains Microchip's model licence. Its use is restricted by the terms embedded in that file.
- `models/provided/MMBT3904.spice.txt` is a Diodes Incorporated model, while the current netlist metadata identifies a different manufacturer. It is retained for comparison and is not silently treated as an exact-vendor match.
- `models/provided/1n4148_spice.lib` is an inspectable model whose manufacturer does not clearly match the current ordered-part metadata. The hybrid deck uses its documented portable model card rather than claiming an exact match.
- `models/provided/lm2901.lib` is legacy comparison material and is not used for the current TLV7044 circuit.
- TI packages downloaded by `Spice.py fetch-models` are placed outside the provided-model directory. Their redistribution must be reviewed before committing or sharing them.

The generated reports record selected model paths and SHA-256 checksums so a future model replacement is reviewable.
