import {
  ServiceStatus,
  NativeModuleStatus,
} from './diagnostics.service';

/**
 * Runtime-card types + pure builders extracted from `diagnostics.component.ts`
 * so the component stays under the 500-line file-length hook. The component
 * imports `buildRuntimeLaneCards` + `buildRuntimeExecutionCards` and the
 * three interfaces; all other helpers in this file stay module-local.
 *
 * Pure functions by design: each one takes service data as input and returns
 * a card descriptor. No DI, no state, no side effects — testable standalone.
 */

export interface RuntimeLaneCard {
  id: 'broken_link_scan' | 'graph_sync' | 'import' | 'pipeline';
  title: string;
  owner: 'celery' | 'unknown';
  state: 'healthy' | 'degraded' | 'failed';
  statusLine: string;
  explanation: string;
  nextStep: string;
  badges: RuntimeLaneBadge[];
}

export interface RuntimeLaneBadge {
  label: string;
  value: string;
  tone: 'good' | 'warn' | 'bad';
}

export interface RuntimeExecutionCard {
  id:
    | 'native_scoring'
    | 'slate_diversity_runtime'
    | 'embedding_specialist'
    | 'scheduler_lane';
  title: string;
  runtime: 'cpp' | 'python' | 'mixed' | 'unknown';
  state: 'healthy' | 'degraded' | 'failed';
  statusLine: string;
  explanation: string;
  nextStep: string;
  badges: RuntimeLaneBadge[];
  details: Array<{ label: string; value: string }>;
  moduleStatuses: NativeModuleStatus[];
}

export function buildRuntimeLaneCards(services: ServiceStatus[]): RuntimeLaneCard[] {
  const runtimeService = services.find(s => s.service_name === 'runtime_lanes');
  const celeryWorkerService = services.find(s => s.service_name === 'celery_worker');
  const metadata = runtimeService?.metadata ?? {};

  return [
    buildLaneCard('broken_link_scan', 'Broken Link Scan', metadata.broken_link_scan_owner, celeryWorkerService),
    buildLaneCard('graph_sync', 'Graph Sync', metadata.graph_sync_owner, celeryWorkerService),
    buildLaneCard('import', 'Import', metadata.import_owner, celeryWorkerService),
    buildLaneCard('pipeline', 'Pipeline', metadata.pipeline_owner, celeryWorkerService),
  ];
}

export function buildRuntimeExecutionCards(services: ServiceStatus[]): RuntimeExecutionCard[] {
  const byName = new Map(services.map(s => [s.service_name, s]));
  const cards: RuntimeExecutionCard[] = [];

  const nativeScoring = byName.get('native_scoring');
  if (nativeScoring) {
    const moduleStatuses = Array.isArray(nativeScoring.metadata?.module_statuses)
      ? nativeScoring.metadata.module_statuses
      : [];
    cards.push({
      id: 'native_scoring',
      title: 'C++ Hot Path',
      runtime: asRuntime(nativeScoring.metadata?.runtime_path),
      state: asCardState(nativeScoring.state),
      statusLine: nativeScoring.explanation,
      explanation: nativeScoring.metadata?.fallback_reason
        ? `Fallback reason: ${nativeScoring.metadata.fallback_reason}`
        : 'This summarizes the native C++ kernels used for scoring, search, parsing, and reranking.',
      nextStep: nativeScoring.next_action_step,
      badges: [
        booleanBadge('Compiled', nativeScoring.metadata?.compiled, true),
        booleanBadge('Importable', nativeScoring.metadata?.importable, true),
        booleanBadge('Safe To Use', nativeScoring.metadata?.safe_to_use, true),
        booleanBadge('Fallback Active', nativeScoring.metadata?.fallback_active, false),
      ],
      details: [
        detail('Runtime', displayRuntime(nativeScoring.metadata.runtime_path)),
        detail('Healthy Modules', displayCount(nativeScoring.metadata.healthy_module_count)),
        detail('Degraded Modules', displayCount(nativeScoring.metadata.degraded_module_count)),
        detail('Benchmark', displayBenchmark(nativeScoring.metadata.benchmark_status, nativeScoring.metadata.speedup_vs_python)),
        detail('C++ Time', displayMilliseconds(nativeScoring.metadata.last_benchmark_ms)),
        detail('Python Time', displayMilliseconds(nativeScoring.metadata.python_benchmark_ms)),
      ],
      moduleStatuses,
    });
  }

  const slateRuntime = byName.get('slate_diversity_runtime');
  if (slateRuntime) {
    cards.push(buildSimpleExecutionCard(
      'slate_diversity_runtime',
      'C++ Slate Diversity',
      slateRuntime,
      [
        booleanBadge('C++ Active', slateRuntime.metadata.cpp_fast_path_active, true),
        booleanBadge('Fallback Active', slateRuntime.metadata.fallback_active, false),
        booleanBadge('Safe To Use', slateRuntime.metadata.safe_to_use, true),
      ],
    ));
  }

  const embeddingSpecialist = byName.get('embedding_specialist');
  if (embeddingSpecialist) {
    cards.push(buildSimpleExecutionCard(
      'embedding_specialist',
      'Python Specialist Lane',
      embeddingSpecialist,
      [
        booleanBadge('Python Active', embeddingSpecialist.metadata?.runtime_path === 'python', true),
        booleanBadge('Fallback Active', embeddingSpecialist.metadata?.fallback_active, false),
        booleanBadge('Safe To Use', embeddingSpecialist.metadata?.safe_to_use, true),
      ],
    ));
  }

  const schedulerLane = byName.get('scheduler_lane');
  if (schedulerLane) {
    cards.push(buildSimpleExecutionCard(
      'scheduler_lane',
      'Task Scheduler',
      schedulerLane,
      [
        booleanBadge('Fallback Active', schedulerLane.metadata?.fallback_active, false),
        booleanBadge('Safe To Use', schedulerLane.metadata?.safe_to_use, true),
        {
          label: 'Mode',
          value: String(schedulerLane.metadata.scheduler_mode || 'Unknown'),
          tone: schedulerLane.metadata.scheduler_mode === 'active'
            ? 'good'
            : schedulerLane.metadata.scheduler_mode === 'shadow'
              ? 'warn'
              : 'bad',
        },
      ],
    ));
  }

  return cards;
}

function buildLaneCard(
  id: RuntimeLaneCard['id'],
  title: string,
  rawOwner: unknown,
  celeryWorkerService?: ServiceStatus,
): RuntimeLaneCard {
  const owner = rawOwner === 'celery' ? 'celery' : 'unknown';

  if (owner === 'celery') {
    const workerHealthy = celeryWorkerService?.state === 'healthy';
    return {
      id,
      title,
      owner,
      state: workerHealthy
        ? 'healthy'
        : celeryWorkerService?.state === 'failed'
          ? 'failed'
          : 'degraded',
      statusLine: workerHealthy
        ? 'Celery owns this lane and the worker is healthy.'
        : 'Celery owns this lane but the worker needs attention.',
      explanation: 'This heavy path is handled by the native Python/C++ runtime.',
      nextStep: workerHealthy
        ? 'No action needed.'
        : (celeryWorkerService?.next_action_step || 'Check the Celery worker health.'),
      badges: buildBadges(owner, workerHealthy),
    };
  }

  return {
    id,
    title,
    owner,
    state: 'failed',
    statusLine: 'The active owner for this lane is unknown.',
    explanation: 'Diagnostics did not return a trustworthy runtime owner for this path.',
    nextStep: 'Refresh diagnostics and check the backend runtime-lane snapshot.',
    badges: buildBadges(owner, false),
  };
}

function buildBadges(
  owner: RuntimeLaneCard['owner'],
  workerAlive: boolean,
): RuntimeLaneBadge[] {
  return [
    {
      label: 'Worker Alive',
      value: workerAlive ? 'Yes' : 'No',
      tone: workerAlive ? 'good' : 'bad',
    },
    {
      label: 'Owner',
      value: owner === 'unknown' ? 'Unknown' : owner.toUpperCase(),
      tone: owner === 'celery' ? 'good' : 'bad',
    },
  ];
}

function buildSimpleExecutionCard(
  id: RuntimeExecutionCard['id'],
  title: string,
  service: ServiceStatus,
  badges: RuntimeLaneBadge[],
): RuntimeExecutionCard {
  return {
    id,
    title,
    runtime: asRuntime(service.metadata?.runtime_path),
    state: asCardState(service.state),
    statusLine: service.explanation,
    explanation: String(service.metadata?.fallback_reason || 'This runtime is tracked through the existing diagnostics system.'),
    nextStep: service.next_action_step,
    badges,
    details: [
      detail('Runtime', displayRuntime(service.metadata?.runtime_path)),
      detail('Owner', String(service.metadata?.owner_selected || 'Tracked by service health')),
      detail('Last Error', String(service.metadata?.last_error_summary || 'None reported')),
    ],
    moduleStatuses: [],
  };
}

function asRuntime(value: unknown): RuntimeExecutionCard['runtime'] {
  return value === 'cpp' || value === 'python' || value === 'mixed' ? value : 'unknown';
}

function asCardState(value: string): RuntimeExecutionCard['state'] {
  return value === 'healthy' || value === 'degraded' || value === 'failed' ? value : 'degraded';
}

function booleanBadge(label: string, value: boolean | undefined, truthyGood: boolean): RuntimeLaneBadge {
  const boolValue = !!value;
  const good = truthyGood ? boolValue : !boolValue;
  return {
    label,
    value: boolValue ? 'Yes' : 'No',
    tone: good ? 'good' : 'bad',
  };
}

function detail(label: string, value: string): { label: string; value: string } {
  return { label, value };
}

function displayRuntime(value: unknown): string {
  const runtime = asRuntime(value);
  return runtime === 'unknown' ? 'Unknown' : runtime.toUpperCase();
}

function displayCount(value: unknown): string {
  return typeof value === 'number' ? String(value) : 'Unknown';
}

function displayBenchmark(status: unknown, speedup: unknown): string {
  if (typeof speedup === 'number') {
    return `${speedup.toFixed(2)}x vs Python`;
  }
  return String(status || 'Not captured yet').replace(/_/g, ' ');
}

function displayMilliseconds(value: unknown): string {
  return typeof value === 'number' ? `${value.toFixed(2)} ms` : 'Not captured yet';
}
