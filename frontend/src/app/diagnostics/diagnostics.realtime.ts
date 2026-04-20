import { ServiceStatus, SystemConflict } from './diagnostics.service';
import { TopicUpdate } from '../core/services/realtime.types';

/**
 * Pure handlers for the websocket realtime stream, extracted from
 * `diagnostics.component.ts` so the component stays under the 500-line
 * file-length hook. Each function takes the current state and an update,
 * returns the new state plus an optional PulseTarget describing a
 * scroll-to-attention pulse the component should trigger. No DI, no
 * DOM access — side effects belong to the caller.
 */

export interface PulseTarget {
  selector: string;
  announce: string;
}

export interface ServiceUpsertResult {
  services: ServiceStatus[];
  pulse: PulseTarget | null;
}

export interface ConflictUpsertResult {
  conflicts: SystemConflict[];
  pulse: PulseTarget | null;
}

export function upsertServiceInto(
  services: ServiceStatus[],
  next: ServiceStatus,
): ServiceUpsertResult {
  const prev = services.find(s => s.id === next.id);
  const wasHealthy = prev ? prev.state === 'healthy' : true;
  const nowFailed = next.state === 'failed';

  const updated = prev
    ? services.map(s => (s.id === next.id ? next : s))
    : [...services, next];

  const pulse: PulseTarget | null =
    wasHealthy && nowFailed
      ? {
          selector: `#service-${next.id}`,
          announce: `${next.service_name} just failed.`,
        }
      : null;

  return { services: updated, pulse };
}

export function removeServiceFrom(
  services: ServiceStatus[],
  id: number,
): ServiceStatus[] {
  return services.filter(s => s.id !== id);
}

export function upsertConflictInto(
  conflicts: SystemConflict[],
  next: SystemConflict,
): ConflictUpsertResult {
  const prev = conflicts.find(c => c.id === next.id);
  const wasResolved = prev ? prev.resolved : true;
  const nowUnresolved = !next.resolved;

  const updated = prev
    ? conflicts.map(c => (c.id === next.id ? next : c))
    : [...conflicts, next];

  const escalating =
    wasResolved && nowUnresolved && (next.severity === 'high' || next.severity === 'critical');
  const pulse: PulseTarget | null = escalating
    ? {
        selector: `#conflict-${next.id}`,
        announce: `New ${next.severity} conflict: ${next.title}.`,
      }
    : null;

  return { conflicts: updated, pulse };
}

export function removeConflictFrom(
  conflicts: SystemConflict[],
  id: number,
): SystemConflict[] {
  return conflicts.filter(c => c.id !== id);
}

export interface RealtimeHandlers {
  onServiceUpsert: (next: ServiceStatus) => void;
  onServiceRemove: (id: number) => void;
  onConflictUpsert: (next: SystemConflict) => void;
  onConflictRemove: (id: number) => void;
}

/**
 * Dispatch a `TopicUpdate` from the realtime stream to the right handler.
 * Unknown event names are ignored intentionally so the emitter can grow
 * without breaking the UI.
 */
export function dispatchRealtimeUpdate(
  update: TopicUpdate,
  handlers: RealtimeHandlers,
): void {
  switch (update.event) {
    case 'service.status.created':
    case 'service.status.updated':
      handlers.onServiceUpsert(update.payload as ServiceStatus);
      break;
    case 'service.status.deleted':
      handlers.onServiceRemove((update.payload as { id: number }).id);
      break;
    case 'conflict.created':
    case 'conflict.updated':
      handlers.onConflictUpsert(update.payload as SystemConflict);
      break;
    case 'conflict.deleted':
      handlers.onConflictRemove((update.payload as { id: number }).id);
      break;
  }
}
