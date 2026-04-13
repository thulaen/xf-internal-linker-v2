import { Pipe, PipeTransform } from '@angular/core';

/**
 * Translates raw score components into plain-English explanations.
 *
 * Usage: {{ suggestion | suggestExplain }}
 * Returns an array of human-readable sentences explaining why the
 * suggestion scored the way it did.
 */

interface ScoreInput {
  score_semantic?: number;
  score_keyword?: number;
  score_node_affinity?: number;
  score_quality?: number;
  score_final?: number;
  anchor_confidence?: string;
  same_silo?: boolean;
  repeated_anchor?: boolean;
}

@Pipe({
  name: 'suggestExplain',
  standalone: true,
  pure: true,
})
export class SuggestionExplainerPipe implements PipeTransform {
  transform(s: ScoreInput | null): string[] {
    if (!s) return [];
    const lines: string[] = [];

    if (s.score_semantic != null && s.score_semantic > 0.7) {
      lines.push('Strong topic match — the source and destination cover closely related subjects.');
    } else if (s.score_semantic != null && s.score_semantic > 0.4) {
      lines.push('Moderate topic overlap — the content is related but not a direct match.');
    } else if (s.score_semantic != null) {
      lines.push('Weak topic match — the connection between source and destination is loose.');
    }

    if (s.score_keyword != null && s.score_keyword > 0.5) {
      lines.push('Keyword relevance is high — shared terms appear in both pages.');
    }

    if (s.score_node_affinity != null && s.score_node_affinity > 0.6) {
      lines.push('These pages are structurally close in the link graph.');
    }

    if (s.score_quality != null && s.score_quality > 0.7) {
      lines.push('The destination page has strong engagement signals (views, replies, freshness).');
    }

    if (s.anchor_confidence === 'strong') {
      lines.push('The anchor text is a confident, natural fit for the sentence.');
    } else if (s.anchor_confidence === 'weak') {
      lines.push('The anchor text is a reasonable fit but could be improved.');
    } else if (s.anchor_confidence === 'none') {
      lines.push('No strong anchor phrase found — consider editing the anchor text.');
    }

    if (s.same_silo) {
      lines.push('Both pages are in the same content silo (topical group).');
    }

    if (s.repeated_anchor) {
      lines.push('This anchor text is already used in another suggestion — consider varying it.');
    }

    if (lines.length === 0) {
      lines.push('Score components are within normal range.');
    }

    return lines;
  }
}
