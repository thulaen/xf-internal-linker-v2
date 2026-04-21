import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { environment } from '../../../environments/environment';
import { ErrorLogEntry } from '../../diagnostics/diagnostics.service';

@Injectable({ providedIn: 'root' })
export class GlitchtipService {
  private readonly http = inject(HttpClient);

  readonly baseUrl = environment.glitchtipBaseUrl;

  getRecentEvents(limit = 50, unresolvedOnly = true): Observable<ErrorLogEntry[]> {
    const params = new HttpParams()
      .set('limit', String(limit))
      .set('status', unresolvedOnly ? 'unresolved' : 'all');

    return this.http
      .get<ErrorLogEntry[]>('/api/glitchtip/events/', { params })
      .pipe(catchError(err => throwError(() => err)));
  }
}
