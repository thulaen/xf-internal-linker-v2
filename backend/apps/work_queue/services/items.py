from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist, ValidationError


@dataclass(frozen=True)
class WorkItemRef:
    kind: str
    id: int
    key: str


def parse_item_key(item_key: str) -> WorkItemRef:
    if "-" not in item_key:
        raise ValidationError("Use autoissue-<id> or papertrail-<id>.")
    prefix, raw_id = item_key.rsplit("-", 1)
    if prefix not in {"autoissue", "papertrail"} or not raw_id.isdigit():
        raise ValidationError("Use autoissue-<id> or papertrail-<id>.")
    return WorkItemRef(kind=prefix, id=int(raw_id), key=item_key)


def load_item(ref: WorkItemRef):
    if ref.kind == "autoissue":
        from apps.auto_issues.models import AutoIssue

        return AutoIssue.objects.get(pk=ref.id)
    if ref.kind == "papertrail":
        from apps.paper_trail.models import PaperTrailEntry

        return PaperTrailEntry.objects.get(pk=ref.id)
    raise ObjectDoesNotExist("Unknown work item kind.")


def affected_files_for(item) -> list[str]:
    files = getattr(item, "affected_files", None) or []
    return [str(path) for path in files if str(path).strip()]

