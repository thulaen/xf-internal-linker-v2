"""Structural prior scoring based on click distance and URL depth (FR-012).

This service calculates how 'shallow' or 'deep' a content item is in the 
site's structural tree. Shallower items (closer to roots) receive a 
small ranking bonus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from django.db import transaction
from django.db.models import F

from apps.suggestions.recommended_weights import recommended_float

if TYPE_CHECKING:
    from apps.content.models import ContentItem, ScopeItem


@dataclass(frozen=True, slots=True)
class ClickDistanceSettings:
    """Settings for FR-012 Click-Distance Structural Prior."""
    ranking_weight: float = recommended_float("click_distance.ranking_weight")
    k_cd: float = recommended_float("click_distance.k_cd")        # Saturation constant
    b_cd: float = recommended_float("click_distance.b_cd")        # Structural depth weight
    b_ud: float = recommended_float("click_distance.b_ud")        # URL depth weight

    def is_valid(self) -> bool:
        """Weight sum must be positive to avoid division by zero."""
        return (self.b_cd + self.b_ud) > 0


class ClickDistanceService:
    """Service to calculate structural depth and click-distance scores."""

    def __init__(self, settings: Optional[ClickDistanceSettings] = None):
        self.settings = settings

    def _ensure_settings(self):
        if self.settings is None:
            from apps.core.views import get_click_distance_settings
            config = get_click_distance_settings()
            self.settings = ClickDistanceSettings(**config)

    def calculate_url_depth(self, url: str) -> int:
        """Return the number of path segments in the URL."""
        if not url:
            return 0
        try:
            path = urlparse(url).path
            # Split by / and filter out empty strings
            segments = [s for s in path.split('/') if s]
            return len(segments)
        except Exception:
            return 0

    def build_scope_depth_map(self) -> Dict[int, int]:
        """
        Build a map of scope_id -> depth (parent hops to root).
        Uses a simple iterative parent traversal for each scope.
        """
        from apps.content.models import ScopeItem
        
        scopes = ScopeItem.objects.all().only('id', 'parent_id')
        scope_by_pk = {s.id: s for s in scopes}
        depth_map: Dict[int, int] = {}

        for scope in scopes:
            depth = 0
            current = scope
            visited = {current.id}
            
            while current.parent_id is not None:
                parent = scope_by_pk.get(current.parent_id)
                if parent is None or parent.id in visited:
                    # Broken or circular path
                    break
                current = parent
                visited.add(current.id)
                depth += 1
                
            depth_map[scope.id] = depth
            
        return depth_map

    def calculate_score(
        self,
        scope_depth: int,
        url_depth: int
    ) -> Tuple[float, str, Dict]:
        """
        Calculate the normalized click distance score (0-1).
        1.0 = shallowest/most prominent.
        0.5 = neutral (fallback).
        """
        self._ensure_settings()
        assert self.settings is not None
        
        if not self.settings.is_valid():
            return 0.5, "neutral_invalid_settings", {}

        # structural_click_distance = scope_depth + 1 (root is 1 click away)
        # This prevents the root from acting as a 0-distance singularity.
        struct_dist = float(scope_depth) + 1.0
        u_depth = float(url_depth)

        # blended_depth = weighted average of structural and URL depth
        blended_depth = (
            (self.settings.b_cd * struct_dist) + (self.settings.b_ud * u_depth)
        ) / (self.settings.b_cd + self.settings.b_ud)

        # Score formula: k / (k + depth)
        # Example k=4:
        #   depth 1 (root) -> 4 / (4+1) = 0.8
        #   depth 5 (deep) -> 4 / (4+5) = 0.44
        raw_score = self.settings.k_cd / (self.settings.k_cd + blended_depth)
        
        # Clamp to 0..1
        score = max(0.0, min(1.0, raw_score))
        
        diagnostics = {
            "scope_depth": scope_depth,
            "url_depth": url_depth,
            "structural_click_distance": struct_dist,
            "blended_depth": round(blended_depth, 3),
            "k_cd": self.settings.k_cd,
            "b_cd": self.settings.b_cd,
            "b_ud": self.settings.b_ud,
        }

        return score, "computed", diagnostics

    def recalculate_all(self) -> Dict[str, int]:
        """
        Bulk recalculate click_distance_score for all ContentItems.
        Returns counts of computed vs neutral items.
        """
        from apps.content.models import ContentItem
        
        self._ensure_settings()
        depth_map = self.build_scope_depth_map()
        items = ContentItem.objects.all().select_related('scope').only('id', 'url', 'scope_id')
        
        counts = {"computed": 0, "neutral": 0, "total": 0}
        updates: List[ContentItem] = []

        for item in items:
            counts["total"] += 1
            
            scope_depth = depth_map.get(item.scope_id if item.scope_id else -1)
            
            if scope_depth is None:
                item.click_distance_score = 0.5
                counts["neutral"] += 1
            else:
                url_depth = self.calculate_url_depth(item.url)
                score, state, _ = self.calculate_score(scope_depth, url_depth)
                item.click_distance_score = score
                if state == "computed":
                    counts["computed"] += 1
                else:
                    counts["neutral"] += 1
            
            updates.append(item)
            
            # Batch updates for performance
            if len(updates) >= 500:
                with transaction.atomic():
                    ContentItem.objects.bulk_update(updates, ['click_distance_score'])
                updates = []

        if updates:
            with transaction.atomic():
                ContentItem.objects.bulk_update(updates, ['click_distance_score'])

        return counts
