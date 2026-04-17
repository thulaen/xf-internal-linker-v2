import { inject } from '@angular/core';
import { HttpHandlerFn, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { DryRunService } from '../services/dry-run.service';

/**
 * Phase MX3 / Gap 343 — stamps `X-Dry-Run: 1` on write requests while
 * the operator has dry-run mode enabled. Backend middleware (future)
 * short-circuits such requests with a synthetic response.
 *
 * Skips GETs, HEADs, and OPTIONS — read-only requests can't damage
 * anything, so the simulate flag is irrelevant for them. Also skips
 * auth flows so the user can still log in while exploring dry-run.
 */

const _WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const _SKIP_PREFIXES = ['/api/auth/', '/api/telemetry/'];

export const dryRunInterceptor: HttpInterceptorFn = (
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
) => {
  if (!_WRITE_METHODS.has(req.method)) return next(req);
  if (_SKIP_PREFIXES.some((p) => req.url.startsWith(p))) return next(req);

  const service = inject(DryRunService);
  if (!service.enabled()) return next(req);

  return next(req.clone({ setHeaders: { 'X-Dry-Run': '1' } }));
};
