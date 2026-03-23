"""
Distiller service — destination content distillation.

Condenses a thread's body text into a clean, meaningful summary
used as the "destination" in semantic matching.
Migrated from V1 with minimal changes in Phase 2.
V1 source: ../xf-internal-linker/services/distiller.py
"""

# TODO Phase 2: migrate from V1 distiller.py


def distill(title: str, body_html: str) -> str:
    """
    Distill a XenForo thread into a clean text representation.

    Combines title with the most meaningful sentences from the body.
    Strips BBCode/HTML tags. Used as the destination embedding input.

    Args:
        title: The thread title.
        body_html: Raw thread body (may contain BBCode or HTML).

    Returns:
        Clean distilled text string ready for embedding.

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Distiller service migrated in Phase 2")
