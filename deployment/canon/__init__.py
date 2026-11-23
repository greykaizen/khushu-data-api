"""Build-time canonicalization for dua content.

See `~/.opencode/plan/dua-content-canonicalization.md` (repo mirror at
`.opencode/plan/dua-content-canonicalization.md`) for the design.
"""

from .blocks import canonical_blocks, plain_projection
from .dua import canonicalize_record, semantic_key, verify_semantic_keys

__all__ = [
    "canonical_blocks",
    "plain_projection",
    "canonicalize_record",
    "semantic_key",
    "verify_semantic_keys",
]
