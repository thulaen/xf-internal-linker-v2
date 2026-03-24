"""
ML pipeline services — migrated from V1 and adapted for Django ORM + pgvector.

Pure-Python utilities (no DB dependency):
    spacy_loader      — shared spaCy model singleton
    text_cleaner      — BBCode stripping and content hashing
    link_parser       — XenForo internal-link extraction from BBCode
    sentence_splitter — spaCy / regex sentence splitting
    distiller         — destination body distillation (top-K sentences)
    anchor_extractor  — anchor phrase extraction from host sentences
    ranker            — composite scoring dataclasses and functions

Django-ORM-dependent services:
    pagerank          — PageRank over ExistingLink graph
    velocity          — velocity score calculator using ContentMetricSnapshot
    embeddings        — embedding generation and storage via pgvector VectorField
    pipeline          — main 3-stage suggestion pipeline
"""
