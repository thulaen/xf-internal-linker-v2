"""FR-242 v2 — Train a LoRA domain adapter on top of frozen BGE-M3.

Operator-runnable Django management command. Default behaviour is
``--dry-run``: validates the corpus size and prints what training
*would* do without touching any weights. Pass ``--commit`` to actually
run the training loop and write the adapter to
``EMBEDDING_DOMAIN_ADAPTER_PATH``.

Sources of truth:
    * Wang, K., Reimers, N. & Gurevych, I. (2022). *GPL: Generative
      Pseudo Labeling for Unsupervised Domain Adaptation of Dense
      Retrieval.* NAACL. arXiv:2112.07577 §4 — 10K-doc minimum-data
      threshold.
    * Hu, E. J. et al. (2021). *LoRA: Low-Rank Adaptation of Large
      Language Models.* arXiv:2106.09685 §4.1 — rank=8, alpha=16.
    * Reimers, N. & Gurevych, I. (2019). *Sentence-BERT: Sentence
      Embeddings using Siamese BERT-Networks.* EMNLP-IJCNLP.
      arXiv:1908.10084 — MultipleNegativesRankingLoss is the
      sentence-pair training loss we use here as a simpler proxy
      for the full GPL margin-MSE pipeline.

Usage::

    docker compose exec backend python manage.py train_domain_adapter
    docker compose exec backend python manage.py train_domain_adapter --commit \\
        --epochs 1 --batch-size 32

The dry-run path runs in seconds and is safe to call any time. The
``--commit`` path requires peft installed and writes a ~2MB adapter
folder; a future ``embeddings`` reload picks it up automatically via
``apps.pipeline.services.domain_adapter.load_adapted_model``.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Train a LoRA domain adapter on top of frozen BGE-M3 (FR-242)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            help=(
                "Actually run training. Default is --dry-run — validates "
                "the corpus and prints what would happen."
            ),
        )
        parser.add_argument(
            "--epochs", type=int, default=1,
            help="Number of training epochs (default 1).",
        )
        parser.add_argument(
            "--batch-size", type=int, default=32,
            help="Training batch size (default 32).",
        )
        parser.add_argument(
            "--max-pairs", type=int, default=20_000,
            help=(
                "Cap on positive sentence-pair count (default 20000). "
                "Larger corpora are sampled."
            ),
        )

    def handle(self, *args, **options):
        from apps.content.models import ContentItem
        from apps.pipeline.services.domain_adapter import (
            GPL_MIN_CORPUS_SIZE,
            LORA_ALPHA_DEFAULT,
            LORA_RANK_DEFAULT,
            get_adapter_weights_path,
            should_train_adapter,
        )

        corpus_size = ContentItem.objects.filter(is_deleted=False).count()
        if not should_train_adapter(corpus_size):
            raise CommandError(
                f"Corpus has only {corpus_size:,} content items; need "
                f"≥{GPL_MIN_CORPUS_SIZE:,} per Wang et al. 2022 GPL §4. "
                f"Aborting — vanilla BGE-M3 stays in use."
            )

        path = get_adapter_weights_path()
        self.stdout.write(
            f"Corpus size: {corpus_size:,} content items. "
            f"Training target: {path}.\n"
            f"LoRA rank={LORA_RANK_DEFAULT}, alpha={LORA_ALPHA_DEFAULT} "
            f"(Hu et al. 2021 §4.1).\n"
        )

        if not options["commit"]:
            self.stdout.write(
                "Dry-run — pass --commit to actually train. "
                "(Vanilla BGE-M3 remains the active model.)"
            )
            return

        ok = self._run_training(
            epochs=options["epochs"],
            batch_size=options["batch_size"],
            max_pairs=options["max_pairs"],
            adapter_path=path,
        )
        if ok:
            self.stdout.write(
                self.style.SUCCESS(
                    f"FR-242 — adapter saved to {path}. "
                    "Restart backend + celery to load it."
                )
            )
        else:
            raise CommandError("Training did not produce an adapter; see logs.")

    def _run_training(
        self,
        *,
        epochs: int,
        batch_size: int,
        max_pairs: int,
        adapter_path: str,
    ) -> bool:
        """Execute the training loop. Returns True on success."""
        try:
            import torch
            from sentence_transformers import (
                SentenceTransformer,
                InputExample,
                losses,
            )
            from torch.utils.data import DataLoader
        except Exception as exc:
            raise CommandError(
                f"Required ML libraries unavailable: {exc}. "
                "Ensure sentence-transformers + torch are installed."
            )

        try:
            from peft import LoraConfig, get_peft_model, TaskType
        except ImportError:
            raise CommandError(
                "peft is not installed. Add `peft>=0.13` to "
                "backend/requirements.txt and rebuild the image."
            )

        examples = self._build_training_examples(max_pairs=max_pairs)
        if len(examples) < 100:
            raise CommandError(
                f"Only {len(examples)} positive pairs assembled — too few "
                "to train. Need broader corpus coverage."
            )

        from apps.pipeline.services.domain_adapter import (
            DEFAULT_MODEL_NAME,
            LORA_ALPHA_DEFAULT,
            LORA_RANK_DEFAULT,
        )
        from apps.pipeline.services.embeddings import (
            DEFAULT_MODEL_NAME as EMBED_DEFAULT,
        )
        model_name = os.environ.get(
            "EMBEDDING_DOMAIN_ADAPTER_BASE_MODEL", EMBED_DEFAULT,
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"

        self.stdout.write(
            f"Loading {model_name} on {device}; assembled {len(examples)} pairs."
        )
        model = SentenceTransformer(model_name, device=device)
        base = model._modules["0"]
        # Wrap the underlying transformer with a LoRA adapter. Hu 2021
        # §4.1 — query and value projection layers are the standard
        # injection points for transformer LoRA adaptation.
        config = LoraConfig(
            task_type=TaskType.FEATURE_EXTRACTION,
            r=LORA_RANK_DEFAULT,
            lora_alpha=LORA_ALPHA_DEFAULT,
            target_modules=["query", "value"],
        )
        try:
            adapted = get_peft_model(base.auto_model, config)
            base.auto_model = adapted
        except Exception as exc:
            raise CommandError(
                f"peft.get_peft_model failed for this base model: {exc}. "
                "BGE-M3 normally exposes `query`/`value` projections; "
                "if you swapped to a different model, adjust target_modules."
            )

        loader = DataLoader(examples, shuffle=True, batch_size=batch_size)
        loss_fn = losses.MultipleNegativesRankingLoss(model)
        warmup = max(1, int(0.1 * len(loader)))

        self.stdout.write(
            f"Training {epochs} epoch(s), batch_size={batch_size}, "
            f"warmup_steps={warmup}…"
        )
        model.fit(
            train_objectives=[(loader, loss_fn)],
            epochs=epochs,
            warmup_steps=warmup,
            show_progress_bar=False,
        )

        os.makedirs(adapter_path, exist_ok=True)
        adapted.save_pretrained(adapter_path)
        return os.path.isfile(os.path.join(adapter_path, "adapter_config.json"))

    def _build_training_examples(self, *, max_pairs: int) -> list:
        """Assemble (anchor, positive) pairs from sibling-sentence adjacency.

        Reimers & Gurevych 2019 §3.1 — sentences from the same scope
        (thread / page) are treated as positives; the
        ``MultipleNegativesRankingLoss`` then samples in-batch
        negatives. This is the simplest training signal that reliably
        produces useful domain adaptation; the full GPL pipeline
        (synthetic queries + hard negatives) is the v2 upgrade.
        """
        from sentence_transformers import InputExample
        from apps.content.models import Sentence
        from collections import defaultdict

        # Pull recent sentences in scope-aligned chunks.
        rows = list(
            Sentence.objects.filter(
                content_item__is_deleted=False,
                text__isnull=False,
            ).values("content_item_id", "text").order_by("-id")[:max_pairs * 4]
        )
        by_content: dict[int, list[str]] = defaultdict(list)
        for row in rows:
            text = (row["text"] or "").strip()
            if 20 <= len(text) <= 512:
                by_content[row["content_item_id"]].append(text)
        examples: list = []
        for sentences in by_content.values():
            for i in range(len(sentences) - 1):
                examples.append(
                    InputExample(texts=[sentences[i], sentences[i + 1]])
                )
                if len(examples) >= max_pairs:
                    return examples
        return examples
