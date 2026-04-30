Terrain Map Assets – Anchoring Contract
======================================

AUTHORITATIVE DEFINITION
-----------------------

The authoritative definition for hex grid geometry, terrain anchoring,
and alpha handling is located at:

docs/rendering/hex_map_rendering.rst

This document is **binding**.
Do not rely on visual alignment or manual adjustments.

------------------------------------------------------------

Map_S3.png
----------

- Pixel coordinate **(0, 0)** corresponds to the **top-left corner of the
  bounding box of hex A1 (col=0, row=0)** in world space.
- Anchoring is derived strictly from `hex_to_world(0, 0)`.
- No X or Y offsets are permitted.
- The image is not centered and must not be recentered.

------------------------------------------------------------

Map_S2.png
----------

- Pixel coordinate **(0, 0)** corresponds to the **top-left corner of the
  bounding box of hex A9 (col=0, row=8)** in world space.
- The X origin is identical to Map_S3.png.
- Only the Y origin differs.
- No additional corrections are permitted.

------------------------------------------------------------

Rules (Do Not Violate)
---------------------

- Do NOT recenter terrain images
- Do NOT trim or pad transparent borders
- Do NOT introduce visual offsets
- Do NOT infer geometry from PNG dimensions
- The hex grid defines the world

Any visual misalignment indicates a **broken asset contract**,
not a rendering bug.
