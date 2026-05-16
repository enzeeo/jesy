const DEVICE_ID_KEY = "disaster.caller.device_id";

function newDeviceId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `dev-${Math.random().toString(36).slice(2, 10)}-${Date.now().toString(36)}`;
}

export function getOrCreateDeviceId(): string {
  if (typeof window === "undefined") return "dev-ssr";
  try {
    const existingDeviceId = window.localStorage.getItem(DEVICE_ID_KEY);
    if (existingDeviceId) return existingDeviceId;
    const deviceId = newDeviceId();
    window.localStorage.setItem(DEVICE_ID_KEY, deviceId);
    return deviceId;
  } catch {
    return newDeviceId();
  }
}
