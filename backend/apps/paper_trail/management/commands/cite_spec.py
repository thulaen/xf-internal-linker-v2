"""manage.py cite_spec — register a spec citation."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.paper_trail.services import lesson_index as svc


_VALID_KINDS = {"patent", "doi", "rfc", "url"}
_KIND_SHORT = {"patent": "p", "doi": "d", "rfc": "r", "url": "u"}


class Command(BaseCommand):
    help = "Register a citation in the CitationCache and emit [SPEC CITED] marker."

    def add_arguments(self, parser):
        parser.add_argument("--key", required=True,
                            help="Canonical key, e.g. doi:10.1109/ICDE.2013.6544812")
        parser.add_argument("--kind", required=True, choices=sorted(_VALID_KINDS))
        parser.add_argument("--id", dest="ref_id", required=True,
                            help="Bare reference id without the kind prefix.")
        parser.add_argument("--title", required=True)
        parser.add_argument("--authors", default="")
        parser.add_argument("--year", type=int, default=0)
        parser.add_argument("--url", default="")
        parser.add_argument("--accessible", type=int, default=1,
                            choices=[0, 1, 2, 3],
                            help="0=unverified 1=ok 2=paywall 3=dead")
        parser.add_argument("--feature-id", required=True,
                            help="Feature/spec id this citation supports.")

    def handle(self, *args, **opts):
        kind = opts["kind"]
        ok = svc.cite_put(
            opts["key"],
            kind=_KIND_SHORT[kind],
            id_=opts["ref_id"],
            title=opts["title"],
            authors=opts["authors"],
            year=opts["year"],
            url=opts["url"],
            accessible=opts["accessible"],
            last_checked_unix=int(timezone.now().timestamp()),
        )
        if not ok:
            raise CommandError(
                "FAIL cite_spec: CitationCache rejected the put (likely full). "
                "Increase the cap in services/lesson_index.py or evict stale "
                "entries via `manage.py prune_test_artefacts`."
            )
        self.stdout.write(
            f"[SPEC CITED: feature={opts['feature_id']} kind={kind} "
            f"id={opts['ref_id']} verified_at={timezone.now().isoformat()}]"
        )
