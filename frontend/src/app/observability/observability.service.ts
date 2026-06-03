import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import { ServiceStatus } from '../diagnostics/diagnostics.service';

@Injectable({ providedIn: 'root' })
export class ObservabilityService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl;

  stack(): Observable<{ services: ServiceStatus[] }> {
    return this.http.get<{ services: ServiceStatus[] }>(`${this.base}/observability/stack/`);
  }
}

