Hex Grid Map Rendering – Design Notes
====================================

This document records the **authoritative rules and decisions** governing the
rendering of the hex map and terrain layers (S2 / S3).

It exists to **prevent regressions** and to make explicit which parts of the
system are allowed to change — and which are not.

------------------------------------------------------------

1. Core Design Rule (Non‑Negotiable)
-----------------------------------

**The hex grid defines the world.**

All other systems (map layers, overlays, units, effects) must adapt to the
hex grid geometry.

This implies:

- The grid geometry is the single source of truth.
- World coordinates are defined by hex math, not by image dimensions.
- No screen‑space or ad‑hoc offsets are allowed.

If this rule is violated, rendering bugs will appear.

------------------------------------------------------------

2. Map Layers Overview
---------------------

Two terrain map layers are used:

- **S3**: Upper (top half) terrain layer
- **S2**: Lower (bottom half) terrain layer

Both layers:

- Are PNG files
- Contain transparency (alpha)
- Use hex‑shaped cutouts encoded in the alpha channel

**Important:**  
S2 and S3 are *not* logical rectangles.  
The hex geometry is already encoded in the image transparency.

------------------------------------------------------------

3. Transparency Rules (Critical)
--------------------------------

This was the root cause of the main visual bug.

Correct Loading
^^^^^^^^^^^^^^^

All PNG maps containing transparency **must** be loaded using
``convert_alpha()``:

::

    s2 = pygame.image.load("Map_S2.png").convert_alpha()
    s3 = pygame.image.load("Map_S3.png").convert_alpha()

Incorrect Loading (Bug Source)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

::

    pygame.image.load("Map_S2.png").convert()

Using ``convert()`` on a PNG with transparency:

- Drops the alpha channel
- Leaves garbage color data under transparent pixels
- Produces rectangular artifacts after ``smoothscale``

This issue looks geometric but is **purely an alpha error**.

------------------------------------------------------------

4. Hex Grid Geometry Reference
------------------------------

The grid uses pointy‑top hexes with row‑based horizontal offset.

Constants
^^^^^^^^^

::

    HEX_R = 52
    HEX_W = sqrt(3) * HEX_R
    HEX_ROW_STEP = 1.5 * HEX_R

Hex to World Coordinates
^^^^^^^^^^^^^^^^^^^^^^^

::

    def hex_to_world(col, row):
        x = col * HEX_W + (row % 2) * (HEX_W / 2)
        y = row * HEX_ROW_STEP
        return x, y

The function returns the **center** of the hex in world coordinates.

------------------------------------------------------------

5. Map Anchoring Rules
---------------------

Map placement is defined **only** in terms of hex coordinates.

S3 (Upper Map)
^^^^^^^^^^^^^^

- Anchored to **hex A1**
- Uses the **top‑left corner** of the A1 hex bounding box

::

    a1_x, a1_y = hex_to_world(0, 0)
    origin_x = a1_x - HEX_W / 2
    origin_y = a1_y - HEX_R

S2 (Lower Map)
^^^^^^^^^^^^^^

- Anchored to **hex A9** (row index 8)
- Uses the **top‑left corner** of the A9 hex bounding box

::

    a9_x, a9_y = hex_to_world(0, 8)
    origin_x = a9_x - HEX_W / 2
    origin_y = a9_y - HEX_R

Only the **Y origin** differs between S3 and S2.

No X correction is ever applied.

------------------------------------------------------------

6. Scaling Rules
----------------

- Map scaling must follow grid scaling.
- The PNG pixel size must never be treated as world geometry.

Scaling occurs *after* anchoring:

::

    screen_x = (world_x - camera_x) * zoom
    screen_y = (world_y - camera_y) * zoom

------------------------------------------------------------

7. Forbidden Fixes (Regression Traps)
------------------------------------

The following changes are **explicitly forbidden**:

- Manual X‑offset adjustments
- Parity‑based special‑case offsets
- Screen‑space anchoring
- Replacing hex math with pixel math
- Mixing ``convert()`` and ``convert_alpha()``

Any of these indicates a violation of core design rules.

------------------------------------------------------------

8. Debugging Checklist
---------------------

If map rendering looks wrong:

1. Confirm **both maps use ``convert_alpha()``**
2. Verify S3 is anchored at A1
3. Verify S2 is anchored at A9
4. Check that no extra offsets were added
5. Inspect PNG files for dirty or premultiplied alpha

If all checks pass, the issue is **not in the rendering math**.

------------------------------------------------------------

9. Final Note
-------------

This bug appeared to be geometric, but the true cause was:

- Incorrect alpha handling
- Incorrect anchoring assumptions

Always consult this document **before modifying rendering code**.

✅ **Status**: Stable and correct