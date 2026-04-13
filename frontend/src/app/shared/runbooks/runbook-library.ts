export interface RunbookStep {
  description: string;
  isDestructive: boolean;
  confirmRequired: boolean;
}

export interface Runbook {
  id: string;
  title: string;
  plainEnglishProblem: string;
  steps: RunbookStep[];
  resourceLevel: 'low' | 'medium' | 'high';
  whatItWillPause: string;
  stopCondition: string;
}

export const RUNBOOK_LIBRARY: Runbook[] = [
  {
    id: 'restart-stuck-pipeline',
    title: 'Restart stuck pipeline',
    plainEnglishProblem: 'A pipeline run has been stuck for over 30 minutes with no progress.',
    steps: [
      { description: 'Check if the Celery worker is responsive', isDestructive: false, confirmRequired: false },
      { description: 'Cancel the stuck pipeline run', isDestructive: true, confirmRequired: true },
      { description: 'Clear the task lock so new runs can start', isDestructive: false, confirmRequired: false },
      { description: 'Re-queue the pipeline run', isDestructive: false, confirmRequired: false },
    ],
    resourceLevel: 'low',
    whatItWillPause: 'The stuck pipeline run only. Other tasks continue.',
    stopCondition: 'Stop if the pipeline resumes progress on its own.',
  },
  {
    id: 'clear-stale-alerts',
    title: 'Clear stale alerts',
    plainEnglishProblem: 'The alerts panel is cluttered with old, acknowledged alerts.',
    steps: [
      { description: 'Acknowledge all read alerts older than 7 days', isDestructive: false, confirmRequired: false },
      { description: 'Resolve all acknowledged alerts older than 14 days', isDestructive: false, confirmRequired: true },
    ],
    resourceLevel: 'low',
    whatItWillPause: 'Nothing. This is a cleanup operation.',
    stopCondition: 'Stop if any alert references an unresolved issue.',
  },
  {
    id: 'recheck-health-services',
    title: 'Re-check all health services',
    plainEnglishProblem: 'Health status is stale or showing incorrect results.',
    steps: [
      { description: 'Trigger a fresh health check for all services', isDestructive: false, confirmRequired: false },
      { description: 'Wait for all checks to complete (usually under 30 seconds)', isDestructive: false, confirmRequired: false },
      { description: 'Review results for any new issues', isDestructive: false, confirmRequired: false },
    ],
    resourceLevel: 'low',
    whatItWillPause: 'Nothing. Health checks are read-only.',
    stopCondition: 'N/A — safe to run at any time.',
  },
  {
    id: 'prune-docker-artifacts',
    title: 'Prune safe Docker artifacts',
    plainEnglishProblem: 'Docker is using too much disk space.',
    steps: [
      { description: 'Show a dry-run preview of what would be removed', isDestructive: false, confirmRequired: false },
      { description: 'Remove dangling images (old build leftovers)', isDestructive: true, confirmRequired: true },
      { description: 'Remove build cache older than 7 days', isDestructive: true, confirmRequired: true },
    ],
    resourceLevel: 'low',
    whatItWillPause: 'Nothing. Only removes unused artifacts.',
    stopCondition: 'Stop if app is not idle (active pipeline or sync running).',
  },
  {
    id: 'reset-quarantined-job',
    title: 'Reset a quarantined job',
    plainEnglishProblem: 'A job has been quarantined after repeated failures.',
    steps: [
      { description: 'Review the failure reason and error log', isDestructive: false, confirmRequired: false },
      { description: 'Clear the quarantine flag', isDestructive: false, confirmRequired: true },
      { description: 'Re-queue the job with a fresh attempt counter', isDestructive: false, confirmRequired: false },
    ],
    resourceLevel: 'medium',
    whatItWillPause: 'Nothing, but the job will consume resources when it runs.',
    stopCondition: 'Stop if the root cause has not been identified.',
  },
  {
    id: 'retrigger-embedding',
    title: 'Re-trigger embedding for failed items',
    plainEnglishProblem: 'Some content items failed to generate embeddings.',
    steps: [
      { description: 'Identify items with missing embeddings', isDestructive: false, confirmRequired: false },
      { description: 'Queue embedding generation for failed items only', isDestructive: false, confirmRequired: true },
      { description: 'Monitor progress in the Jobs page', isDestructive: false, confirmRequired: false },
    ],
    resourceLevel: 'high',
    whatItWillPause: 'GPU may be used. Other GPU work will queue behind this.',
    stopCondition: 'Stop if GPU temperature exceeds 76°C (automatic).',
  },
];
