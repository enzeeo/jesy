export interface GeoCoords {
  lat: number;
  lng: number;
  accuracy_m?: number;
}

export type GeoFailureReason = "denied" | "unavailable" | "timeout" | "forced_off";

export class GeoError extends Error {
  override readonly name = "GeoError";

  constructor(public readonly reason: GeoFailureReason, message?: string) {
    super(message ?? reason);
  }
}

export function getCurrentPosition(timeoutMs = 6000): Promise<GeoCoords> {
  if (typeof window !== "undefined") {
    const params = new URLSearchParams(window.location.search);
    if (params.get("gps") === "off") {
      return Promise.reject(new GeoError("forced_off", "GPS forced off via ?gps=off"));
    }
  }

  if (typeof navigator === "undefined" || !navigator.geolocation) {
    return Promise.reject(new GeoError("unavailable", "Geolocation is not available."));
  }

  return new Promise<GeoCoords>((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          accuracy_m: position.coords.accuracy,
        });
      },
      (error) => {
        if (error.code === error.PERMISSION_DENIED) {
          reject(new GeoError("denied", "Location permission denied."));
        } else if (error.code === error.TIMEOUT) {
          reject(new GeoError("timeout", "Location request timed out."));
        } else {
          reject(new GeoError("unavailable", error.message));
        }
      },
      {
        enableHighAccuracy: true,
        timeout: timeoutMs,
        maximumAge: 30000,
      },
    );
  });
}

export function getFallbackLocation(): { lat: number; lng: number } {
  const lat = Number.parseFloat(process.env.NEXT_PUBLIC_DEFAULT_LOCATION_LAT ?? "35.5951");
  const lng = Number.parseFloat(process.env.NEXT_PUBLIC_DEFAULT_LOCATION_LNG ?? "-82.5515");
  return { lat, lng };
}
