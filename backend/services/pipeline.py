"""
Pipeline service stub.

The real pipeline now lives in `backend/apps/pipeline/services/pipeline.py`.
This placeholder stays only so old imports fail clearly if they are still used.
"""


def run_pipeline(host_thread_id: int) -> list[dict]:
    """
    Run the full suggestion pipeline for a host thread.

    The live implementation uses semantic, keyword, March 2026 PageRank,
    velocity, and quality signals in the Django app pipeline service.

    Raises:
        NotImplementedError: This legacy stub should not be used.
    """
    raise NotImplementedError("Pipeline service migrated to apps.pipeline.services.pipeline")
