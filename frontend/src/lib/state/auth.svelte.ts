/**
 * Authentication state for cookie-based sessions.
 *
 * No tokens, no localStorage, no refresh dance. The browser carries the
 * httpOnly session cookie automatically; the SPA tracks identity by
 * calling ``GET /auth/me`` once at boot and after any login. ``user``
 * is the full source of truth.
 */

import { getMe, postLogin, postLogout, postSetupComplete } from '$lib/api/auth';
import type { UserProfile } from '$lib/api/auth';
import { postInviteRegister } from '$lib/api/signup';

class AuthState {
  user = $state<UserProfile | null>(null);
  isAuthenticated = $derived(!!this.user);
  isLoading = $state(false);
  error = $state<string | null>(null);
  // Tracks the very first /auth/me round-trip so the layout guard
  // can avoid a redirect-flash on cold load.
  bootComplete = $state(false);

  constructor() {
    if (typeof window !== 'undefined') {
      void this.bootstrap();
    } else {
      this.bootComplete = true;
    }
  }

  private async bootstrap(): Promise<void> {
    try {
      this.user = await getMe();
    } catch {
      this.user = null;
    } finally {
      this.bootComplete = true;
    }
  }

  async login(email: string, password: string): Promise<void> {
    this.isLoading = true;
    this.error = null;
    try {
      this.user = await postLogin(email, password);
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Login failed';
      throw err;
    } finally {
      this.isLoading = false;
    }
  }

  async registerWithInvite(
    token: string,
    password: string,
    displayName?: string,
  ): Promise<void> {
    this.isLoading = true;
    this.error = null;
    try {
      this.user = await postInviteRegister(token, password, displayName);
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Registration failed';
      throw err;
    } finally {
      this.isLoading = false;
    }
  }

  async completeSetup(token: string, password: string): Promise<void> {
    this.isLoading = true;
    this.error = null;
    try {
      this.user = await postSetupComplete(token, password);
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Setup failed';
      throw err;
    } finally {
      this.isLoading = false;
    }
  }

  /**
   * Refresh the cached user profile from /auth/me. Used after the
   * profile page mutates anything that's mirrored on ``user``.
   */
  async refreshUser(): Promise<void> {
    this.user = await getMe();
  }

  async logout(): Promise<void> {
    try {
      await postLogout();
    } finally {
      this.user = null;
    }
  }
}

export const authState = new AuthState();
