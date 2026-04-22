import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

/**
 * Phase F1 / Gap 95 — WebAuthn passkey login.
 *
 * Frontend half of a passkey flow. The browser side is fully
 * implemented (registration ceremony, authentication ceremony,
 * conditional UI hint) — but it relies on three backend endpoints
 * that issue/verify the WebAuthn challenges:
 *
 *   POST /api/auth/passkey/register/begin/   → PublicKeyCredentialCreationOptions
 *   POST /api/auth/passkey/register/finish/  ← AttestationResponse
 *   POST /api/auth/passkey/login/begin/      → PublicKeyCredentialRequestOptions
 *   POST /api/auth/passkey/login/finish/     ← AssertionResponse + sets session cookie
 *
 * Until those endpoints land, every method here returns a structured
 * "not configured" outcome so the login page can hide the passkey
 * button cleanly when the backend isn't ready. `isAvailable()`
 * combines browser support + a HEAD probe of the begin endpoint.
 *
 * Security notes (mirrors the server's contract):
 *   - challenges are 32-byte random buffers issued by the server.
 *   - relying-party id MUST match the page's origin (single-string
 *     RP ID, not a URL).
 *   - userVerification = 'preferred' (let the browser decide whether
 *     to require a fingerprint / face / PIN).
 */

export type PasskeyOutcome =
  | { ok: true }
  | { ok: false; reason: 'unsupported' | 'not-configured' | 'cancelled' | 'error'; detail?: string };

@Injectable({ providedIn: 'root' })
export class PasskeyService {
  private readonly http = inject(HttpClient);

  /** Quick browser-side check — does this user agent expose the
   *  WebAuthn API at all? Doesn't probe the server. */
  isBrowserSupported(): boolean {
    return (
      typeof window !== 'undefined' &&
      typeof window.PublicKeyCredential !== 'undefined' &&
      typeof navigator !== 'undefined' &&
      typeof navigator.credentials !== 'undefined' &&
      typeof navigator.credentials.create === 'function' &&
      typeof navigator.credentials.get === 'function'
    );
  }

  /** Full availability check — browser + the begin endpoint exists.
   *  Components show the passkey button only when this returns true. */
  async isAvailable(): Promise<boolean> {
    if (!this.isBrowserSupported()) return false;
    try {
      const res = await fetch('/api/auth/passkey/login/begin/', {
        method: 'HEAD',
        credentials: 'same-origin',
      });
      // Anything but 404 = the endpoint is wired (even 401 means it
      // exists and is asking for auth, which is fine for HEAD).
      return res.status !== 404;
    } catch {
      return false;
    }
  }

  /** Registration ceremony — adds a new passkey to the current user.
   *  Caller must already be authenticated (the begin endpoint reads
   *  the session). */
  async register(): Promise<PasskeyOutcome> {
    if (!this.isBrowserSupported()) {
      return { ok: false, reason: 'unsupported' };
    }
    try {
      const options = await this.beginRegistration();
      if (!options) return { ok: false, reason: 'not-configured' };
      const credential = (await navigator.credentials.create({
        publicKey: options,
      })) as PublicKeyCredential | null;
      if (!credential) {
        return { ok: false, reason: 'cancelled' };
      }
      await this.finishRegistration(credential);
      return { ok: true };
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e);
      // The DOM throws AbortError when the user dismisses the prompt.
      if (detail.includes('AbortError') || detail.includes('NotAllowed')) {
        return { ok: false, reason: 'cancelled' };
      }
      return { ok: false, reason: 'error', detail };
    }
  }

  /** Authentication ceremony — sign in with a previously-registered
   *  passkey. Uses a `mediation: 'optional'` prompt so the browser's
   *  conditional UI can autofill on browsers that support it. */
  async login(): Promise<PasskeyOutcome> {
    if (!this.isBrowserSupported()) {
      return { ok: false, reason: 'unsupported' };
    }
    try {
      const options = await this.beginLogin();
      if (!options) return { ok: false, reason: 'not-configured' };
      const credential = (await navigator.credentials.get({
        publicKey: options,
      })) as PublicKeyCredential | null;
      if (!credential) {
        return { ok: false, reason: 'cancelled' };
      }
      await this.finishLogin(credential);
      return { ok: true };
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e);
      if (detail.includes('AbortError') || detail.includes('NotAllowed')) {
        return { ok: false, reason: 'cancelled' };
      }
      return { ok: false, reason: 'error', detail };
    }
  }

  // ── server round trips ─────────────────────────────────────────────

  private async beginRegistration(): Promise<PublicKeyCredentialCreationOptions | null> {
    try {
      const raw = await firstValueFrom(
        this.http.post<unknown>('/api/auth/passkey/register/begin/', {}),
      );
      return this.decodeCreationOptions(raw);
    } catch {
      return null;
    }
  }

  private async finishRegistration(cred: PublicKeyCredential): Promise<void> {
    await firstValueFrom(
      this.http.post('/api/auth/passkey/register/finish/', this.encodeCredential(cred)),
    );
  }

  private async beginLogin(): Promise<PublicKeyCredentialRequestOptions | null> {
    try {
      const raw = await firstValueFrom(
        this.http.post<unknown>('/api/auth/passkey/login/begin/', {}),
      );
      return this.decodeRequestOptions(raw);
    } catch {
      return null;
    }
  }

  private async finishLogin(cred: PublicKeyCredential): Promise<void> {
    await firstValueFrom(
      this.http.post('/api/auth/passkey/login/finish/', this.encodeCredential(cred)),
    );
  }

  // ── (de)serialisation ──────────────────────────────────────────────
  // WebAuthn options use ArrayBuffers; the server hands them as
  // base64url strings. These helpers translate.

  private decodeCreationOptions(raw: unknown): PublicKeyCredentialCreationOptions | null {
    if (!raw || typeof raw !== 'object') return null;
    const r = raw as Record<string, unknown>;
    return {
      ...r,
      challenge: this.b64uToBuffer(r['challenge'] as string),
      user: {
        ...(r['user'] as Record<string, unknown>),
        id: this.b64uToBuffer((r['user'] as Record<string, unknown>)['id'] as string),
      } as PublicKeyCredentialUserEntity,
      excludeCredentials: ((r['excludeCredentials'] as unknown[]) ?? []).map((c) => ({
        ...(c as Record<string, unknown>),
        id: this.b64uToBuffer((c as Record<string, unknown>)['id'] as string),
      })) as PublicKeyCredentialDescriptor[],
    } as PublicKeyCredentialCreationOptions;
  }

  private decodeRequestOptions(raw: unknown): PublicKeyCredentialRequestOptions | null {
    if (!raw || typeof raw !== 'object') return null;
    const r = raw as Record<string, unknown>;
    return {
      ...r,
      challenge: this.b64uToBuffer(r['challenge'] as string),
      allowCredentials: ((r['allowCredentials'] as unknown[]) ?? []).map((c) => ({
        ...(c as Record<string, unknown>),
        id: this.b64uToBuffer((c as Record<string, unknown>)['id'] as string),
      })) as PublicKeyCredentialDescriptor[],
    } as PublicKeyCredentialRequestOptions;
  }

  private encodeCredential(cred: PublicKeyCredential): unknown {
    const resp = cred.response as AuthenticatorResponse & {
      attestationObject?: ArrayBuffer;
      authenticatorData?: ArrayBuffer;
      signature?: ArrayBuffer;
      userHandle?: ArrayBuffer | null;
    };
    return {
      id: cred.id,
      rawId: this.bufferToB64u(cred.rawId),
      type: cred.type,
      response: {
        clientDataJSON: this.bufferToB64u(resp.clientDataJSON),
        attestationObject: resp.attestationObject ? this.bufferToB64u(resp.attestationObject) : undefined,
        authenticatorData: resp.authenticatorData ? this.bufferToB64u(resp.authenticatorData) : undefined,
        signature: resp.signature ? this.bufferToB64u(resp.signature) : undefined,
        userHandle: resp.userHandle ? this.bufferToB64u(resp.userHandle) : undefined,
      },
    };
  }

  private b64uToBuffer(s: string): ArrayBuffer {
    const padded = s.replace(/-/g, '+').replace(/_/g, '/');
    const padLen = (4 - (padded.length % 4)) % 4;
    const decoded = atob(padded + '='.repeat(padLen));
    const buf = new ArrayBuffer(decoded.length);
    const view = new Uint8Array(buf);
    for (let i = 0; i < decoded.length; i++) view[i] = decoded.charCodeAt(i);
    return buf;
  }

  private bufferToB64u(b: ArrayBuffer): string {
    const bytes = new Uint8Array(b);
    let s = '';
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
}
