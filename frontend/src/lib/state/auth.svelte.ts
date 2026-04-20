/**
 * Authentication state management using Svelte 5 runes.
 *
 * Stores tokens in localStorage and provides login/register/logout functions.
 */

import { getMe, postLogin, postRefresh, postRegister } from '$lib/api/auth';
import type { UserProfile } from '$lib/api/auth';
import { postInviteRegister } from '$lib/api/signup';

const TOKEN_KEY = 'doe_access_token';
const REFRESH_KEY = 'doe_refresh_token';
const USER_KEY = 'doe_user';

class AuthState {
  accessToken = $state<string | null>(null);
  refreshToken = $state<string | null>(null);
  user = $state<UserProfile | null>(null);
  isAuthenticated = $derived(!!this.accessToken);
  isLoading = $state(false);
  error = $state<string | null>(null);

  constructor() {
    // Load persisted state on init (client-side only)
    if (typeof window !== 'undefined') {
      this.accessToken = localStorage.getItem(TOKEN_KEY);
      this.refreshToken = localStorage.getItem(REFRESH_KEY);
      const userJson = localStorage.getItem(USER_KEY);
      if (userJson) {
        try {
          this.user = JSON.parse(userJson);
        } catch {
          localStorage.removeItem(USER_KEY);
        }
      }
      if (this.accessToken) {
        void this.refreshUser();
      }
    }
  }

  private async refreshUser(): Promise<void> {
    if (!this.accessToken) return;
    try {
      const profile = await getMe(this.accessToken);
      this.persistUser(profile);
    } catch {
      // Silent fallback to cached localStorage copy; a 401 will be caught
      // on the next authenticated request and trigger a proper logout.
    }
  }

  private persistTokens(access: string, refresh: string) {
    this.accessToken = access;
    this.refreshToken = refresh;
    localStorage.setItem(TOKEN_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  }

  private persistUser(user: UserProfile) {
    this.user = user;
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  async login(email: string, password: string): Promise<void> {
    this.isLoading = true;
    this.error = null;
    try {
      const tokens = await postLogin(email, password);
      this.persistTokens(tokens.access_token, tokens.refresh_token);
      await this.hydrateUser(tokens.access_token);
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Login failed';
      throw err;
    } finally {
      this.isLoading = false;
    }
  }

  private async hydrateUser(accessToken: string): Promise<void> {
    try {
      this.persistUser(await getMe(accessToken));
    } catch {
      // Fall back to a stub derived from the JWT payload so the UI still
      // has an identity to render; balance/is_admin will populate on retry.
      const payload = JSON.parse(atob(accessToken.split('.')[1]));
      this.persistUser({
        id: payload.sub,
        email: payload.email,
        display_name: null,
        background: null,
        is_admin: false,
        created_at: null,
        balance_usd: null,
        balance_tokens: null,
      });
    }
  }

  async register(
    email: string,
    password: string,
    displayName?: string,
    background?: string,
  ): Promise<void> {
    this.isLoading = true;
    this.error = null;
    try {
      const tokens = await postRegister(email, password, displayName, background);
      this.persistTokens(tokens.access_token, tokens.refresh_token);
      await this.hydrateUser(tokens.access_token);
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Registration failed';
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
      const tokens = await postInviteRegister(token, password, displayName);
      this.persistTokens(tokens.access_token, tokens.refresh_token);
      await this.hydrateUser(tokens.access_token);
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
      const { postSetupComplete } = await import('$lib/api/auth');
      const tokens = await postSetupComplete(token, password);
      this.persistTokens(tokens.access_token, tokens.refresh_token);
      await this.hydrateUser(tokens.access_token);
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Setup failed';
      throw err;
    } finally {
      this.isLoading = false;
    }
  }

  async refresh(): Promise<boolean> {
    if (!this.refreshToken) return false;
    try {
      const tokens = await postRefresh(this.refreshToken);
      this.persistTokens(tokens.access_token, tokens.refresh_token);
      return true;
    } catch {
      this.logout();
      return false;
    }
  }

  logout() {
    this.accessToken = null;
    this.refreshToken = null;
    this.user = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  }
}

export const authState = new AuthState();
