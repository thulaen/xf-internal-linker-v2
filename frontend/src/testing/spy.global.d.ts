// Global test types so the Karma→Vitest migration needs no per-file imports.
// The Jasmine codemod rewrites `jasmine.createSpyObj('Name', ['a','b'])` to the
// global `createSpyObj<T>(['a','b'])`, `jasmine.SpyObj<T>` to `SpyObj<T>`, and
// `jasmine.Spy` to `Spy`. The runtime implementation of `createSpyObj` is
// registered on globalThis in src/test-setup.ts.
import type { Mock, MockInstance } from 'vitest';

declare global {
  /**
   * A single mock function (replaces Jasmine's `Spy`). Permissive so both
   * `vi.fn()` (`Mock`) and `vi.spyOn()` (`MockInstance`) results assign to a
   * `Spy`-typed variable, matching Jasmine's loose `Spy` type.
   */
  type Spy = MockInstance<any>;

  /** An object whose methods are all Vitest mocks (replaces `jasmine.SpyObj`). */
  type SpyObj<T> = {
    [K in keyof T]: T[K] extends (...args: any[]) => any ? Mock : T[K];
  };

  /**
   * Build an object of Vitest mock functions for the named methods. Replaces
   * `jasmine.createSpyObj`. The Jasmine name argument is dropped by the codemod;
   * the optional `properties` map (Jasmine's 3rd argument) is assigned as-is.
   */
  function createSpyObj<T = any>(
    methodNames: Array<keyof T> | readonly string[],
    properties?: Record<string, unknown>,
  ): SpyObj<T>;
}

export {};
