# Lorekeeper — 45s Pixel Art Action Video (`1920x1080 @ 60fps`)

A 45-second cinematic motion-graphics and 16-bit pixel art action trailer based on **Lorekeeper** (`msavastano/Dreaming`), the fantasy text adventure set in **Thornwick** on the edge of the **Greywood**.

## Core Visual & Narrative Rhythm

Every scene follows the signature two-phase structure:
1. **STILL PHASE (`⏸ PIXEL STILL: VOICEOVER READING TEXT`)**:
   - The 16-bit pixel-art world holds a frozen tableau while the player's move (`You > ...`) and the Game Master's narration type out onto the bottom console.
   - The code-synthesized **Voiceover** reads the campaign text aloud accompanied by mechanical typewriter ticks and a ducked 16-bit lute arpeggio.
2. **ACTION PHASE (`▶ PIXEL ACTION: LIVE 60 FPS`)**:
   - As soon as the Voiceover finishes reading the text, a power-fifth stinger and viewport flash unleash **60fps pixel-art action**: characters stride across cobblestones, silver coins arc through the dusk air, Garra's blacksmith hammer showers the anvil in sparks, and Wren leaps under the blood-silver moon to cleave the Greywood Dread-Wolf.

---

## Deliverables in `video/`

| Deliverable | File Path | Description |
| :--- | :--- | :--- |
| **1. Rendered MP4** | `video/lorekeeper_pixel_action.mp4` | `1920x1080`, `60 fps`, `45.0s` (`2,700 frames`), H.264 video + 44.1 kHz stereo AAC audio generated 100% in code. |
| **2. Source Project** | `video/config.py`, `video/sprites.py`, `video/scenes.py`, `video/audio.py`, `video/render.py` | Modular Python source project with editable scene timing constants at the top of `video/config.py`. |
| **3. VO Script with Timestamps** | `video/VO_SCRIPT.md` | Full voiceover script with exact start/end timestamps, turn IDs, player moves, and action cues. |
| **4. 3-Frame Contact Sheet** | `video/contact_sheet_8s_22s_38s.png` | Composition check sheet at `8.0s`, `22.0s`, and `38.0s` (full 16:9 frames + 1:1 4x pixel viewport crops). |

---

## Editable Scene Timing Constants (`video/config.py`)

All scene boundaries and phase transitions are defined as top-level constants in `video/config.py`:

```python
# Scene 1: Arrival at Thornwick Gate & The Crooked Lantern Inn
SCENE_1_START: float = 0.0
SCENE_1_VO_START: float = 0.30
SCENE_1_STILL_END: float = 5.80
SCENE_1_END: float = 11.50

# Scene 2: The Smithy Forge & Elder Maren's Sealed Letter
SCENE_2_START: float = 11.50
SCENE_2_VO_START: float = 11.80
SCENE_2_STILL_END: float = 17.50
SCENE_2_END: float = 25.00

# Scene 3: Moonrise in the Greywood — Battle at the Old Mill
SCENE_3_START: float = 25.00
SCENE_3_VO_START: float = 25.30
SCENE_3_STILL_END: float = 31.00
SCENE_3_END: float = 39.50

# Scene 4: Offline Dreaming — Canon Rebuilt at Dawn Ridge
SCENE_4_START: float = 39.50
SCENE_4_VO_START: float = 39.75
SCENE_4_STILL_END: float = 42.75
SCENE_4_END: float = 45.00
```

## Rebuilding the Contact Sheet or Full Render

```bash
# 1. Regenerate only the 3-frame contact sheet (8s, 22s, 38s) and VO_SCRIPT.md (~4 seconds)
python3 -m video.render --contact-sheet-only

# 2. Render the full 45-second 1920x1080 @ 60fps MP4, contact sheet, and VO_SCRIPT.md
python3 -m video.render
```
