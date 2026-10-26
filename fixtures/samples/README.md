# Sample record (per-frame contract between the sampler and the state machine)

One row per processed frame. Python (`server/whcore/oracle/sampler.py`, `Sampler.sample`) and Swift
(`ios/WHCapture`, S2.T3) must produce the same columns; the state machine (S1.T2 / S2.T2) reads
only these. Files here are gzip CSV with a header row; missing values are the literal `nan`.

Coordinates come from the calibration (`fixtures/calibration/iphone-1206x2622.json`), scaled by
buffer size when the frame is not 1206×2622 (the phone's ReplayKit buffers are 884×1920).

| column | type | meaning |
| --- | --- | --- |
| `frame` | int | index in the sampled stream (0-based) |
| `t_ms` | int | time since the start of the stream |
| `t{i}_r`, `t{i}_g`, `t{i}_b` (i = 0–15) | float | mean RGB of tile *i*'s sample patch (`sample_rects[i]`: a 40×16 strip at the top of the tile, clear of the glyph), row-major tiles |
| `{roi}_r/g/b`, `{roi}_std` for roi ∈ `banner`, `banner_words`, `banner_score`, `timer`, `end_banner`, `end_list` | float | mean RGB of the calibrated rect, and the std of per-pixel gray (mean of r,g,b) over it |
| `p0` … `p63` | float | 64-bin row-intensity profile of the whole frame (gray, every 4th column) |
| `words` | float | live banner WORDS count read with the digit templates (`fixtures/templates/digits.npz`), only on frames classified `board`; else `nan` |
| `list_shift` | float | VIEW ALL WORDS scroll shift vs the previous frame in px (positive = content moved up), from the full-resolution list-band profile (rows 612–2600, x 330–940) with a pull towards the previous shift; only on `all_words` frames after the first; else `nan` |

Rounding: all floats to 1 decimal.

## Colour domains
Values are in the colour domain of the source and are **not** interchangeable:
screen recordings (BT.709, resting tile ≈ (247, 209, 151)) vs the phone's ReplayKit buffers
(resting ≈ (251, 217, 163)). Thresholds that depend on colour live with the domain they were
measured in (calibration `resting_rgb_video` and, from S2, the phone values).

## Screen classes derived from a row (see `whcore/oracle/screens.py`)
- `board`: banner mean > 185, banner std > 70, timer mean < 112
- `end`: banner mean < 115, banner std < 25, end_banner std > 60, end_list mean < 110
- `all_words`: banner mean 105–135, banner std 38–62, timer mean > 140, timer std > 60
- otherwise `other`
