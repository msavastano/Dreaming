# Lorekeeper — Voiceover (VO) Script & Scene Timestamps

- **Project**: Lorekeeper (`msavastano/Dreaming`) — Thornwick Campaign Action Trailer
- **Format**: `1920x1080`, `60 fps`, `45.00 seconds` (`2,700 frames`)
- **Audio & Voiceover**: 100% generated in code (`video/audio.py` via `ffmpeg` `libflite` `rms` voice + NumPy procedural SFX & 16-bit synth score)
- **Visual Rhythm**: In every scene, the **pixel art remains completely STILL** while the Voiceover reads the campaign text aloud and the text types onto the console. The moment the VO finishes reading, the scene transitions into **60fps PIXEL ART ACTION**.

---

## Master Timeline & Phase Overview

| Scene | Act / Location | Turn ID | Still + VO Phase | Pixel Action Phase | Contact Sheet Check |
| :---: | :--- | :---: | :---: | :---: | :---: |
| **1** | ACT I // DUSK AT THORNWICK GATE (Thornwick — The Crooked Lantern) | `s001-t0005` | `00.00s – 05.80s` | `05.80s – 11.50s` | **8.0s** |
| **2** | ACT II // THE SMITHY & THE SEALED LETTER (Thornwick — Garra's Smithy) | `s001-t0009` | `11.50s – 17.50s` | `17.50s – 25.00s` | **22.0s** |
| **3** | ACT III // MOONRISE IN THE GREYWOOD (The Greywood — Old Millstream) | `s001-t0038` | `25.00s – 31.00s` | `31.00s – 39.50s` | **38.0s** |
| **4** | ACT IV // OFFLINE DREAMING & CANON REBUILT (Thornwick Ridge — Dawn Overlook) | `dream-pass-01` | `39.50s – 42.75s` | `42.75s – 45.00s` | **—** |

---

## Timestamped Voiceover (VO) Script & Action Cues

### Scene 1: ACT I // DUSK AT THORNWICK GATE
- **Scene Window**: `00.00s – 11.50s` (Frames `0000 – 0689`)
- **Campaign Turn ID**: `s001-t0005`
- **On-Screen Player Move**: `You > I arrive at Thornwick gate at dusk and ask Hobb at the Crooked Lantern for a room.`
- **Phase 1 — PIXEL STILL + VOICEOVER (`00.00s – 05.80s`)**:
  - **VO Timestamp**: `00.30s – 05.30s`
  - **Spoken VO Line**: *"Dusk falls on Thornwick. At the Crooked Lantern, Hobb lends Wren three silver."*
  - **Visual State**: Pixel-art characters hold a frozen tableau while the narration text types out on the console in sync with the voiceover and typewriter ticks.
- **Phase 2 — PIXEL ACTION UNLEASHED (`05.80s – 11.50s`)**:
  - **Action Trigger Cue (`05.80s`)**: Power fifth stinger + viewport flash transitions badge from `⏸ PIXEL STILL` to `▶ PIXEL ACTION: LIVE 60 FPS`.
  - **Pixel Action Choreography**: Wren & Pebble stride to the inn; Hobb waves his lantern & tosses 3 silver coins.
  - **Lorekeeper Memory Update**: `remembered: owes Hobb 3 silver by full moon [s001-t0005]`

### Scene 2: ACT II // THE SMITHY & THE SEALED LETTER
- **Scene Window**: `11.50s – 25.00s` (Frames `0690 – 1499`)
- **Campaign Turn ID**: `s001-t0009`
- **On-Screen Player Move**: `You > I give Elder Maren the sealed letter, and promise Garra a wolf pelt from the Greywood.`
- **Phase 1 — PIXEL STILL + VOICEOVER (`11.50s – 17.50s`)**:
  - **VO Timestamp**: `11.80s – 17.04s`
  - **Spoken VO Line**: *"Elder Maren traces the sealed letter. At the forge, Garra sharpens your blade."*
  - **Visual State**: Pixel-art characters hold a frozen tableau while the narration text types out on the console in sync with the voiceover and typewriter ticks.
- **Phase 2 — PIXEL ACTION UNLEASHED (`17.50s – 25.00s`)**:
  - **Action Trigger Cue (`17.50s`)**: Power fifth stinger + viewport flash transitions badge from `⏸ PIXEL STILL` to `▶ PIXEL ACTION: LIVE 60 FPS`.
  - **Pixel Action Choreography**: Garra hammers the glowing anvil in showers of sparks; Wren catches & slashes the honed blade.
  - **Lorekeeper Memory Update**: `remembered: promised Garra a Greywood wolf pelt [s001-t0007]`

### Scene 3: ACT III // MOONRISE IN THE GREYWOOD
- **Scene Window**: `25.00s – 39.50s` (Frames `1500 – 2369`)
- **Campaign Turn ID**: `s001-t0038`
- **On-Screen Player Move**: `You > At moonrise I follow tracks past the old mill into the Greywood and draw my short sword.`
- **Phase 1 — PIXEL STILL + VOICEOVER (`25.00s – 31.00s`)**:
  - **VO Timestamp**: `25.30s – 30.16s`
  - **Spoken VO Line**: *"Past the old mill, the Greywood wakes. A shadow wolf lunges under the moon."*
  - **Visual State**: Pixel-art characters hold a frozen tableau while the narration text types out on the console in sync with the voiceover and typewriter ticks.
- **Phase 2 — PIXEL ACTION UNLEASHED (`31.00s – 39.50s`)**:
  - **Action Trigger Cue (`31.00s`)**: Power fifth stinger + viewport flash transitions badge from `⏸ PIXEL STILL` to `▶ PIXEL ACTION: LIVE 60 FPS`.
  - **Pixel Action Choreography**: Dread-Wolf lunges; Wren parries with the blue bead, dashes in, and cleaves the beast under the moon.
  - **Lorekeeper Memory Update**: `recalled: s001-t0007 (wolf pelt for Garra) -> QUEST COMPLETE`

### Scene 4: ACT IV // OFFLINE DREAMING & CANON REBUILT
- **Scene Window**: `39.50s – 45.00s` (Frames `2370 – 2699`)
- **Campaign Turn ID**: `dream-pass-01`
- **On-Screen Player Move**: `You > /dream — Fold campaign turns into wiki pages, verify notes, and rebuild canon.md.`
- **Phase 1 — PIXEL STILL + VOICEOVER (`39.50s – 42.75s`)**:
  - **VO Timestamp**: `39.75s – 42.55s`
  - **Spoken VO Line**: *"Dreaming complete. Every promise remembered."*
  - **Visual State**: Pixel-art characters hold a frozen tableau while the narration text types out on the console in sync with the voiceover and typewriter ticks.
- **Phase 2 — PIXEL ACTION UNLEASHED (`42.75s – 45.00s`)**:
  - **Action Trigger Cue (`42.75s`)**: Power fifth stinger + viewport flash transitions badge from `⏸ PIXEL STILL` to `▶ PIXEL ACTION: LIVE 60 FPS`.
  - **Pixel Action Choreography**: Wren raises the blade at dawn as golden memory constellations rise into the Lorekeeper emblem.
  - **Lorekeeper Memory Update**: `canon.md rebuilt: 3 notes confirmed, wiki/wren.md & wiki/garra.md updated`
