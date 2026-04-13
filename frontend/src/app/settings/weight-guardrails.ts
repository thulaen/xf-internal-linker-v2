/**
 * Guardrail warnings for weight sliders.
 * Inline HealthBanner appears when any weight exceeds safe bounds.
 */

export interface GuardrailWarning {
  key: string;
  threshold: number;
  direction: 'above' | 'below';
  message: string;
}

export const WEIGHT_GUARDRAILS: GuardrailWarning[] = [
  {
    key: 'semantic_similarity',
    threshold: 0.9,
    direction: 'above',
    message: 'Semantic similarity weight is very high — this may exclude valid cross-topic links.',
  },
  {
    key: 'semantic_similarity',
    threshold: 0.1,
    direction: 'below',
    message: 'Semantic similarity weight is very low — suggestions may link unrelated pages.',
  },
  {
    key: 'quality_score',
    threshold: 0.9,
    direction: 'above',
    message: 'Quality weight is very high — only the most popular pages will receive links.',
  },
  {
    key: 'explore_exploit',
    threshold: 0.9,
    direction: 'above',
    message: 'Exploration is very high — the system will try many unproven link combinations.',
  },
  {
    key: 'diversity',
    threshold: 0.1,
    direction: 'below',
    message: 'Diversity is very low — multiple suggestions may point to the same destination.',
  },
];

/**
 * Check a weight value against guardrails and return any triggered warnings.
 */
export function checkGuardrails(weights: Record<string, number>): GuardrailWarning[] {
  return WEIGHT_GUARDRAILS.filter(g => {
    const val = weights[g.key];
    if (val == null) return false;
    return g.direction === 'above' ? val > g.threshold : val < g.threshold;
  });
}
