import type {
  IncidentCategory,
  ResourceType,
  SeverityBand,
} from '@disaster/types';
import {
  AlertTriangle,
  Bolt,
  Droplets,
  Flame,
  Heart,
  MapPin,
  Shield,
  Stethoscope,
  Truck,
  User,
  Users,
} from 'lucide-react';
import type { ComponentType, SVGProps } from 'react';

export const SEVERITY_BAND_CLASS: Record<SeverityBand, string> = {
  critical: 'text-red-400 bg-red-500/15 ring-red-500/40',
  high: 'text-orange-400 bg-orange-500/15 ring-orange-500/40',
  medium: 'text-amber-400 bg-amber-500/15 ring-amber-500/40',
  low: 'text-emerald-400 bg-emerald-500/15 ring-emerald-500/40',
  info: 'text-sky-400 bg-sky-500/15 ring-sky-500/40',
};

export const SEVERITY_BAND_DOT: Record<SeverityBand, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  medium: 'bg-amber-500',
  low: 'bg-emerald-500',
  info: 'bg-sky-500',
};

export const SEVERITY_BAND_HEX: Record<SeverityBand, string> = {
  critical: '#ef4444',
  high: '#fb923c',
  medium: '#f59e0b',
  low: '#10b981',
  info: '#38bdf8',
};

export const SEVERITY_BAND_LABEL: Record<SeverityBand, string> = {
  critical: '90+',
  high: '75-89',
  medium: '50-74',
  low: '25-49',
  info: '0-24',
};

type Icon = ComponentType<SVGProps<SVGSVGElement>>;

export const CATEGORY_ICON: Record<IncidentCategory, Icon> = {
  medical: Heart,
  trapped: Users,
  fire: Flame,
  water: Droplets,
  shelter: MapPin,
  power: Bolt,
  evacuation: Truck,
  unknown: AlertTriangle,
};

export const RESOURCE_ICON: Record<ResourceType, Icon> = {
  police: Shield,
  fire: Flame,
  ems: Truck,
  paramedic: Heart,
  nurse: User,
  doctor: Stethoscope,
  volunteer: Users,
};

export const RESOURCE_LABEL: Record<ResourceType, string> = {
  police: 'Police',
  fire: 'Fire',
  ems: 'EMS',
  paramedic: 'Paramedic',
  nurse: 'Nurse',
  doctor: 'Doctor',
  volunteer: 'Volunteer',
};

export const RESOURCE_CLASS: Record<ResourceType, string> = {
  police: 'text-sky-300 bg-sky-500/15 ring-sky-500/30',
  fire: 'text-red-300 bg-red-500/15 ring-red-500/30',
  ems: 'text-amber-300 bg-amber-500/15 ring-amber-500/30',
  paramedic: 'text-orange-300 bg-orange-500/15 ring-orange-500/30',
  nurse: 'text-pink-300 bg-pink-500/15 ring-pink-500/30',
  doctor: 'text-purple-300 bg-purple-500/15 ring-purple-500/30',
  volunteer: 'text-emerald-300 bg-emerald-500/15 ring-emerald-500/30',
};

export const RESOURCE_BAR: Record<ResourceType, string> = {
  police: 'bg-sky-500',
  fire: 'bg-red-500',
  ems: 'bg-amber-500',
  paramedic: 'bg-orange-500',
  nurse: 'bg-pink-500',
  doctor: 'bg-purple-500',
  volunteer: 'bg-emerald-500',
};

export function formatEta(sec: number): string {
  const total = Math.max(0, Math.round(sec));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function timeAgo(iso: string, nowMs = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return 'just now';
  const diffSec = Math.max(0, Math.round((nowMs - then) / 1000));
  if (diffSec < 60) return `${diffSec}s ago`;
  const m = Math.floor(diffSec / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}
