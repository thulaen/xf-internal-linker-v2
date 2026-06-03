import { APP_INITIALIZER, ErrorHandler, NgModule } from '@angular/core';
import {
  faro,
  getWebInstrumentations,
  initializeFaro,
  type Faro,
} from '@grafana/faro-web-sdk';

import { environment } from '../../environments/environment';

type FaroInitializer = (config: Parameters<typeof initializeFaro>[0]) => Faro;

let faroStarted = false;

export function resetFaroForTests(): void {
  faroStarted = false;
}

export function createFaroInitializer(
  startFaro: FaroInitializer = initializeFaro,
): () => void {
  return () => {
    if (faroStarted || !environment.faroEnabled || !environment.faroEndpoint) {
      return;
    }

    startFaro({
      url: environment.faroEndpoint,
      app: {
        name: 'xf-internal-linker',
        version: '1.0.0',
        environment: environment.production ? 'prod' : 'dev',
      },
      instrumentations: getWebInstrumentations(),
    });

    faroStarted = true;
  };
}

export class FaroErrorHandler implements ErrorHandler {
  private readonly defaultHandler = new ErrorHandler();

  handleError(error: unknown): void {
    try {
      faro.api.pushError(error instanceof Error ? error : new Error(String(error)));
    } catch {
      // Faro reporting must never hide the original Angular error.
    }

    this.defaultHandler.handleError(error);
  }
}

@NgModule({
  providers: [
    {
      provide: APP_INITIALIZER,
      useFactory: createFaroInitializer,
      multi: true,
    },
    {
      provide: ErrorHandler,
      useClass: FaroErrorHandler,
    },
  ],
})
export class FaroModule {}
