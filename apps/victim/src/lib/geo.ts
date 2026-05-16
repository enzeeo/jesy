export interface GeoCoords {
  lat: number;
  lng: number;
  accuracy_m?: number;
}

export type GeoFailureReason = 'denied' | 'unavailable' | 'timeout' | 'forced_off';

export class GeoError extends Error {
  override readonly name = 'GeoError';
  constructor(public readonly reason: GeoFailureReason, message?: string) {
    super(message ?? reason);
  }
}

interface GetCurrentPositionOptions {
  timeoutMs?: number;
}

/**
 * Wrap navigator.geolocation in a Promise that resolves to {lat,lng,accuracy_m}
 * or rejects with a typed GeoError.
 *
 * For the demo flow we honor `?gps=off` on the URL to force the manual-location
 * fallback path without having to deny permission in the browser.
 */
export function getCurrentPosition(
  opts: GetCurrentPositionOptions = {},
): Promise<GeoCoords> {
  const timeoutMs = opts.timeoutMs ?? 6_000;

  if (typeof window !== 'undefined') {
    const params = new URLSearchParams(window.location.search);
    if (params.get('gps') === 'off') {
      return Promise.reject(new GeoError('forced_off', 'GPS forced off via ?gps=off'));
    }
  }

  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    return Promise.reject(new GeoError('unavailable', 'Geolocation is not available.'));
  }

  return new Promise<GeoCoords>((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          accuracy_m: pos.coords.accuracy,
        });
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          reject(new GeoError('denied', 'Location permission denied.'));
        } else if (err.code === err.TIMEOUT) {
          reject(new GeoError('timeout', 'Location request timed out.'));
        } else {
          reject(new GeoError('unavailable', err.message));
        }
      },
      {
        enableHighAccuracy: true,
        timeout: timeoutMs,
        maximumAge: 30_000,
      },
    );
  });
}
