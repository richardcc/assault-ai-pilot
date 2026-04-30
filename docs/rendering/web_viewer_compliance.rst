Hex Grid Map Rendering – Web Viewer Compliance
==============================================

This document defines the **binding compliance requirements** for the
web-based hex map viewer.

The web viewer does not define geometry.
It must strictly comply with the authoritative rendering rules.

------------------------------------------------------------

Authoritative Reference
-----------------------

All hex grid geometry, terrain anchoring (S2 / S3), scaling rules, and
alpha-handling semantics are defined in the following authoritative
document:

:doc:`hex_map_rendering`

This reference is **normative**.
Any discrepancy is considered a regression.

------------------------------------------------------------

Terrain Layers (S2 / S3)
------------------------

The web viewer MUST:

- Anchor the S3 terrain layer to **hex A1**, exactly as defined in the
  authoritative rendering document
- Anchor the S2 terrain layer to **hex A9**, exactly as defined in the
  authoritative rendering document
- Use the same ``hex_to_world`` mathematics as the canonical renderer
- Apply **no positional offsets or corrections**
- Preserve alpha transparency semantics exactly

The web viewer MUST NOT:

- Recenter terrain images
- Apply screen-space anchoring
- Introduce parity-based or row-dependent corrections
- Infer geometry from PNG pixel dimensions
- Compensate visually for malformed assets

Any visual misalignment must be treated as an **asset or contract
violation**, not as a geometry problem.

------------------------------------------------------------

Rendering Responsibility
------------------------

The web viewer is responsible only for:

- World-to-screen coordinate transformation
- Camera translation
- Zoom scaling
- Correct compositing order

The web viewer is **not** responsible for redefining world geometry,
grid structure, or terrain anchoring rules.

------------------------------------------------------------

Status
------

✅ Geometry: defined elsewhere  
✅ Authority: external and binding  
✅ Compliance: mandatory