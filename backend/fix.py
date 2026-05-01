
txt = open('apps/pipeline/tasks.py').read()

txt = txt.replace('        generate_content_item_embeddings,\n    )\n\n    # Resume from', '        generate_content_item_embeddings,\n    )\n    from apps.pipeline.services.passage_relevance import regenerate_passage_embeddings_for\n\n    # Resume from')

txt = txt.replace('        if len(batch) >= _BACKFILL_BATCH_SIZE:\n            generate_content_item_embeddings(\n                content_item_ids=batch,\n                force_reembed=True,\n            )\n            processed += len(batch)', '        if len(batch) >= _BACKFILL_BATCH_SIZE:\n            generate_content_item_embeddings(\n                content_item_ids=batch,\n                force_reembed=True,\n            )\n            for item in ContentItem.objects.filter(pk__in=batch):\n                regenerate_passage_embeddings_for(item)\n            processed += len(batch)')

txt = txt.replace('    # Tail flush.\n    if batch:\n        generate_content_item_embeddings(\n            content_item_ids=batch,\n            force_reembed=True,\n        )\n        processed += len(batch)', '    # Tail flush.\n    if batch:\n        generate_content_item_embeddings(\n            content_item_ids=batch,\n            force_reembed=True,\n        )\n        for item in ContentItem.objects.filter(pk__in=batch):\n            regenerate_passage_embeddings_for(item)\n        processed += len(batch)')

append_str = """
@shared_task(
    bind=True,
    name="passage_relevance.train_opq_codebook",
    time_limit=3600,
    soft_time_limit=3540,
)
def train_opq_codebook(self, sample_size=100000) -> dict:
    \"\"\"Train OPQ codebooks periodically to adapt to corpus drift.\"\"\"
    try:
        from apps.pipeline.services.opq_trainer import train_codebook
        train_codebook(sample_size=sample_size)
        return {"status": "completed"}
    except Exception as exc:
        logger.exception("OPQ codebook training failed")
        raise
"""

txt += append_str

with open('apps/pipeline/tasks.py', 'w') as f:
    f.write(txt)
