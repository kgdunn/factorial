/**
 * Inline re-authentication state.
 *
 * When ``authFetch`` sees a 401 it calls ``triggerReauth()``, which opens
 * the ``ReauthModal`` and returns a promise that resolves once the user
 * has signed back in (or rejects if they cancel). All concurrent 401s
 * await the same promise, so a burst of failed requests opens exactly
 * one modal and replays each request once.
 *
 * This is intentionally not a Svelte ``$state`` class because the gate
 * is shared across module instances and modules importing it should not
 * be reactive on the *queue*; only the modal itself reads ``isOpen``.
 */

let pending: { resolve: () => void; reject: (err: Error) => void } | null = null;
let pendingPromise: Promise<void> | null = null;

class ReauthState {
  isOpen = $state(false);
}

export const reauthState = new ReauthState();

/**
 * Open the modal (or join the existing one) and return a promise that
 * resolves when the user has logged back in. Multiple concurrent
 * callers all await the same promise.
 */
export function triggerReauth(): Promise<void> {
  if (pendingPromise) return pendingPromise;

  pendingPromise = new Promise<void>((resolve, reject) => {
    pending = { resolve, reject };
  });
  reauthState.isOpen = true;
  return pendingPromise;
}

/**
 * Resolve all queued requests after a successful re-auth. Called by the
 * modal when the user has signed back in.
 */
export function reauthResolve(): void {
  pending?.resolve();
  pending = null;
  pendingPromise = null;
  reauthState.isOpen = false;
}

/**
 * Reject all queued requests. Called by the modal when the user cancels
 * (closes without logging in). Each pending caller will get a typed
 * error and can decide what to do — typically the page-level UI will
 * route the user to /login.
 */
export function reauthReject(): void {
  pending?.reject(new Error('Re-authentication cancelled'));
  pending = null;
  pendingPromise = null;
  reauthState.isOpen = false;
}
