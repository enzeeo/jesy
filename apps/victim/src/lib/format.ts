import type { ResourceType, SeverityBand } from '@disaster/types';

export function formatEta(seconds: number | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total} sec`;
  const m = Math.round(total / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem === 0 ? `${h} hr` : `${h} hr ${rem} min`;
}

export function formatTimeSince(iso: string, nowMs = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return 'just now';
  const diffSec = Math.max(0, Math.round((nowMs - then) / 1000));
  if (diffSec < 30) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  return `${h} hr ago`;
}

export function severityBandToLabel(band: SeverityBand): string {
  switch (band) {
    case 'critical':
      return 'Critical';
    case 'high':
      return 'High';
    case 'medium':
      return 'Medium';
    case 'low':
      return 'Low';
    case 'info':
      return 'Watch';
    default: {
      const _exhaustive: never = band;
      return _exhaustive;
    }
  }
}

export const RESOURCE_LABEL: Record<ResourceType, string> = {
  police: 'Police',
  fire: 'Fire crew',
  ems: 'EMT',
  paramedic: 'Paramedic',
  nurse: 'Nurse',
  doctor: 'Doctor',
  volunteer: 'Volunteer',
};

/** Human, calm verb-phrase for one resource (used in copy on Status). */
export function resourceLabelHuman(type: ResourceType): string {
  return RESOURCE_LABEL[type] ?? String(type);
}
