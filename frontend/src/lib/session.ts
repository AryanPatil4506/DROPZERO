// Demo sign-in. There is no auth backend yet (see CONTRACT_REQUESTS.md), so signing in only
// records a flag in sessionStorage for this tab. No password is stored or sent anywhere.
const KEY = "dropzero.demo-session";

export interface DemoSession {
  email: string;
}

export function getSession(): DemoSession | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as DemoSession) : null;
  } catch {
    return null;
  }
}

export function startSession(email: string): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ email } satisfies DemoSession));
  } catch {
    /* storage unavailable: the gate below lets the user through anyway */
  }
}

export function endSession(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

/** True when storage is unavailable, so a blocked sessionStorage never locks the demo out. */
export function storageBlocked(): boolean {
  try {
    sessionStorage.setItem(`${KEY}.probe`, "1");
    sessionStorage.removeItem(`${KEY}.probe`);
    return false;
  } catch {
    return true;
  }
}
