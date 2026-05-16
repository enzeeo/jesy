const DEVICE_ID_KEY = 'disaster.victim.device_id';

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  // Fallback: not cryptographically strong, but good enough for an anonymous device id.
  return 'dev-' + Math.random().toString(36).slice(2, 10) + '-' + Date.now().toString(36);
}

export function getOrCreateDeviceId(): string {
  if (typeof window === 'undefined') return 'dev-ssr';
  try {
    const existing = window.localStorage.getItem(DEVICE_ID_KEY);
    if (existing && existing.length > 0) return existing;
    const fresh = uuid();
    window.localStorage.setItem(DEVICE_ID_KEY, fresh);
    return fresh;
  } catch {
    // Private mode or storage disabled — generate a session-only id.
    return uuid();
  }
}
