import type {
  DeviceFlag,
  IncidentCategory,
} from '@disaster/types';

/**
 * Body shape for `POST /v1/incidents` per CONTEXT.md §1 Incident submission.
 * The location is either GPS coords + accuracy + source, or a free-text
 * place description that the API will resolve via Snowpark UDF.
 */
export interface IncidentSubmitLocationGps {
  source: 'gps';
  lat: number;
  lng: number;
  accuracy_m?: number;
}

export interface IncidentSubmitLocationDescription {
  source: 'place_description_udf';
  description: string;
}

export type IncidentSubmitLocation =
  | IncidentSubmitLocationGps
  | IncidentSubmitLocationDescription;

export interface IncidentSubmitBody {
  profile_id?: string;
  device_id: string;
  location: IncidentSubmitLocation;
  raw_text: string;
  needs: Partial<Record<IncidentCategory, boolean>>;
  inventory_have: DeviceFlag[];
  inventory_need: DeviceFlag[];
  timestamp: string;
}
