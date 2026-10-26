# Measurements (agents: write numbers here once; read them instead of re-measuring)

## Screenshots (2026-10-24)
- `IMG_0717.PNG` board at 00:01, all tiles resting; 1206×2622 px. Letters LCMEORSIETRATDIM.
- `IMG_0718.PNG` end screen: WORDS 65, SCORE 44700; shows the top 15 words then "(50 more)".
- Solver on that board: YAWL 335 words / 262,800 max pts; ENABLE 251 / 196,500.
  By length (YAWL): 10:1, 9:1, 8:6, 7:33, 6:57, 5:70, 4:107, 3:60.
  By length (ENABLE): 10:1, 8:4, 7:26, 6:44, 5:50, 4:79, 3:47.
- Accepted by GamePigeon but not in ENABLE: CLOTTER, CLOTTERS, LOTTER, LOTTERS (all in YAWL).

## Dictionaries
- yawl.txt 264,097 lines (260,269 of 3–16 letters); enable1.txt 172,823 (170,398). Lowercase a–z, no dupes.
- 82 ENABLE words are not in YAWL.

## Recording (session1)
- session1: 1.17 GB, 622 s, 1206×2622 HEVC (yuvj420p, BT.709 full range), ~60 fps VFR → sampled at 30 fps = 18,672 frames.
- allwords1: 1.22 GB, 647 s, same format → 19,420 frames. Both were .mp4 renamed to .mov (same container).
- Colour domain: video is darker than the P3 PNG (bg green PNG (106,138,98) vs video (85,127,83)).
  Resting tile in video (247.4, 209.3, 150.5) vs PNG (245, 218, 170) → `resting_rgb_video` in the calibration.
- Geometry: video tiles land within 0.5 px of the PNG calibration (no rescale).
- Tile colour clusters seen (video, /6 bins): resting 71%, white (252,252,252) 10%, green (126,252,126), yellow (246,246,114), red (252,138,138).
- "(N more)" on the end screen expands to the full list: yes / no

## Calibration
- (S0.T4, `fixtures/calibration/iphone-1206x2622.json`; rects are [x,y,w,h] px)
- tiles 188 px, pitch 218.67 px both axes; centre (0,0) = (274.4, 1283.1), (3,3) = (930.4, 1939.1).
- colour sample patch per tile: 40×16 px at centre dy −73 (top strip, clear of glyph). Resting RGB (245, 218, 170).
- board banner [131,220,944,279]; "WORDS: n" line [406,297,270,36]; "SCORE: s" line [408,347,649,66]; timer pill [851,500,199,73].
- end: player banner [54,867,500,140]; list panel [53,1040,499,975]; 15 rows, first row y 1043 (h 48), pitch 61.07; words x 53–336, points x 336–552.
- seed letter templates (48×48 ink masks) re-read IMG_0717 exactly; min best−second NCC margin 0.16.

## Colour states (RGB centroids)
- resting / valid_new / already_found / not_a_word:

## Accuracy
| metric | 30 fps | 15 fps |
| --- | --- | --- |
| board segmentation | | |
| accepted attempts == WORDS | | |
| letters (LOBO) | | |
| reconciliation (§3.3) | | |

## All-words list (allwords1)
- captures matched to the right board:
- per-length totals vs YAWL / ENABLE solver counts:
- max safe shift px/frame (30 / 15 fps) and equivalent flick speed:

## Device probe (30 min)
- mem peak MB / fps p50 / p5 / frames dropped:
- App Groups available on Personal Team: yes / no

## Go / no-go
-
