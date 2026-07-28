"""Drawing system for native sketch curves.

Layered so the data extraction is independent of GPU submission:

- ``render_data`` — pulls a sketch's renderable geometry into flat buckets and
  computes a cheap change-signature (headless-testable, no GPU).
- ``overlay`` — builds and caches GPU batches from that data and draws them,
  rebuilding only when the signature changes.
"""
