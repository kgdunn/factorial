/**
 * Authentication state management using Svelte 5 runes.
 *
 * Stores tokens in localStorage and provides login/register/logout functions.
 */

import { postLogin, postRefresh, postRegister } from '$lib/api/auth';
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

      // Decode user info from access token payload
      const payload = JSON.parse(atob(tokens.access_token.split('.')[1]));
      this.persistUser({
        id: payload.sub,
        email: payload.email,
        display_name: null,
        background: null,
        is_admin: false,
        created_at: null,
      });
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Login failed';
      throw err;
    } finally {
      this.isLoading = false;
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

      const payload = JSON.parse(atob(tokens.access_token.split('.')[1]));
      this.persistUser({
        id: payload.sub,
        email: payload.email,
        display_name: displayName || null,
        background: background || null,
        is_admin: false,
        created_at: null,
      });
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
    background?: string,
  ): Promise<void> {
    this.isLoading = true;
    this.error = null;
    try {
      const tokens = await postInviteRegister(token, password, displayName, background);
      this.persistTokens(tokens.access_token, tokens.refresh_token);

      const payload = JSON.parse(atob(tokens.access_token.split('.')[1]));
      this.persistUser({
        id: payload.sub,
        email: payload.email,
        display_name: displayName || null,
        background: background || null,
        is_admin: false,
        created_at: null,
      });
    } catch (err) {
      this.error = err instanceof Error ? err.message : 'Registration failed';
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
