import { TestBed } from '@angular/core/testing';
import { APP_INITIALIZER, ErrorHandler } from '@angular/core';
import type { Faro } from '@grafana/faro-web-sdk';

import { environment } from '../../environments/environment';
import {
  createFaroInitializer,
  FaroErrorHandler,
  FaroModule,
  resetFaroForTests,
} from './faro.module';

describe('FaroModule', () => {
  beforeEach(() => {
    resetFaroForTests();
  });

  afterEach(() => {
    resetFaroForTests();
  });

  it('initialises Faro with expected URL', () => {
    const initializeSpy = vi.fn().mockReturnValue({
      api: createSpyObj(['pushError']),
    } as unknown as Faro);

    const init = createFaroInitializer(initializeSpy);

    init();

    expect(initializeSpy).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({
        url: environment.faroEndpoint,
        app: {
          name: 'xf-internal-linker',
          version: '1.0.0',
          environment: environment.production ? 'prod' : 'dev',
        },
      }),
    );
  });

  it('registers its initializer and error handler providers', () => {
    TestBed.configureTestingModule({
      imports: [FaroModule],
    });

    const initializers = TestBed.inject(APP_INITIALIZER);

    expect(initializers.length).toBeGreaterThan(0);
    expect(TestBed.inject(ErrorHandler)).toEqual(expect.any(FaroErrorHandler));
  });
});
