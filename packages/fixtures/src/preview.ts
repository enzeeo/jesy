// =============================================================
// Texas Flood — Fixture UI Preview data
//
// 12 curated synthetic incidents + roster + assignments + clusters
// + routes + victim status states + a scripted 60-second timeline.
//
// IMPORTANT: this is local mock data for the Fixture UI Preview phase.
// Final judged demo must use the live Snowflake processing path.
// =============================================================

import type {
  Assignment,
  ClusterView,
  DashboardState,
  FixtureTimelineEvent,
  IncidentEnriched,
  Profile,
  Responder,
  ResourceRoster,
  RoutePreview,
  ScenarioState,
  UnmetResourceNeed,
  VictimStatusView,
} from '@disaster/types';

// =============================================================
// Houston anchor
// =============================================================
export const HOUSTON_CENTER = { lat: 29.7604, lng: -95.3698 };

// =============================================================
// Synthetic Profiles (fake but realistic; safe for demo/Q&A)
// =============================================================
export const SYNTHETIC_PROFILES: Record<string, Profile> = {
  'pf-sarah': {
    profile_id: 'pf-sarah',
    device_id: 'dev-sarah-001',
    name: 'Sarah W.',
    age: 67,
    conditions: ['diabetes', 'hypertension'],
    devices_owned: ['insulin'],
    emergency_contact: { name: 'Jenny W. (daughter)', phone: '555-0100' },
    created_at: '2026-05-14T16:02:00Z',
  },
  'pf-tanya': {
    profile_id: 'pf-tanya',
    device_id: 'dev-tanya-002',
    name: 'Tanya R.',
    age: 28,
    conditions: ['nursing_mother'],
    devices_owned: [],
    emergency_contact: { name: 'Mark R. (husband)', phone: '555-0101' },
    created_at: '2026-05-15T20:14:00Z',
  },
  'pf-marcus': {
    profile_id: 'pf-marcus',
    device_id: 'dev-marcus-003',
    name: 'Marcus T.',
    age: 45,
    conditions: ['asthma'],
    devices_owned: ['inhaler'],
    created_at: '2026-05-15T22:00:00Z',
  },
  'pf-ella': {
    profile_id: 'pf-ella',
    device_id: 'dev-ella-004',
    name: 'Ella K. (minor, w/ uncle)',
    age: 8,
    conditions: [],
    devices_owned: [],
    emergency_contact: { name: 'Daniel K. (uncle)', phone: '555-0102' },
    created_at: '2026-05-16T01:18:00Z',
  },
  'pf-robert': {
    profile_id: 'pf-robert',
    device_id: 'dev-robert-005',
    name: 'Robert V.',
    age: 72,
    conditions: ['copd', 'oxygen_dependent'],
    devices_owned: ['oxygen'],
    emergency_contact: { name: 'Linda V. (wife)', phone: '555-0103' },
    created_at: '2026-05-13T08:45:00Z',
  },
  'pf-anon': {
    profile_id: 'pf-anon',
    device_id: 'dev-anon-006',
    name: '— anonymous —',
    age: 0,
    conditions: [],
    devices_owned: [],
    created_at: '2026-05-16T14:00:00Z',
  },
};

// =============================================================
// 12 fixture incidents
// =============================================================
const TS = (s: string) => `2026-05-16T15:${s}:00-05:00`;

export const FIXTURE_INCIDENTS: IncidentEnriched[] = [
  // ---- 1: Sarah, 67, diabetic, on her roof (CRITICAL, assigned)
  {
    incident_id: 'inc-001',
    profile_id: 'pf-sarah',
    device_id: 'dev-sarah-001',
    location: { lat: 29.791, lng: -95.487, accuracy_m: 8, source: 'gps' },
    raw_text:
      "I'm trapped on my roof, water is up to my chest. I'm 67 and diabetic, I have my insulin but I'm cold and shaking.",
    needs: { medical: true, trapped: true, water: true },
    inventory_have: ['insulin'],
    inventory_need: [],
    ts: TS('00'),
    severity: {
      score: 92,
      category: 'trapped',
      top_reasons: [
        '67-year-old with diabetes — hypothermia risk on roof',
        'Rising water reported at chest level',
        'Caller describes shaking — early hypothermia signal',
      ],
      required_resources: { fire: 1, paramedic: 1 },
      confidence: 0.94,
    },
    triage_status: 'ok',
    summary:
      'Elderly diabetic woman trapped on roof in rising water. Has insulin. Hypothermia signs.',
    cluster_id: 'cl-spring-branch',
    status: 'assigned',
    profile_snapshot: SYNTHETIC_PROFILES['pf-sarah'],
  },

  // ---- 2: Tanya, 28, baby formula, power out (HIGH, assigned)
  {
    incident_id: 'inc-002',
    profile_id: 'pf-tanya',
    device_id: 'dev-tanya-002',
    location: { lat: 29.74, lng: -95.4, accuracy_m: 12, source: 'gps' },
    raw_text:
      "Power is out, my baby needs formula and I can't drive out, streets are flooded around me.",
    needs: { shelter: true, water: true, power: true },
    inventory_have: [],
    inventory_need: [],
    ts: TS('02'),
    severity: {
      score: 71,
      category: 'shelter',
      top_reasons: [
        'Infant in household with no formula access',
        'Power outage — no way to heat or sterilize',
        'Roads impassable for self-evacuation',
      ],
      required_resources: { volunteer: 1, ems: 1 },
      confidence: 0.86,
    },
    triage_status: 'ok',
    summary: 'Mother with infant, no power, no formula. Road-locked.',
    status: 'assigned',
    profile_snapshot: SYNTHETIC_PROFILES['pf-tanya'],
  },

  // ---- 3: Apartment fire (CRITICAL, primary of duplicate group)
  {
    incident_id: 'inc-003',
    profile_id: undefined,
    device_id: 'dev-anon-007',
    location: { lat: 29.81, lng: -95.32, accuracy_m: 15, source: 'gps' },
    raw_text:
      'Apartment fire on the second floor, lots of smoke, six families still inside, the stairwell is blocked.',
    needs: { fire: true, trapped: true },
    inventory_have: [],
    inventory_need: [],
    ts: TS('04'),
    severity: {
      score: 96,
      category: 'fire',
      top_reasons: [
        'Active structure fire with multiple residents trapped',
        'Stairwell egress blocked — extraction required',
        'Smoke inhalation injuries highly likely',
      ],
      required_resources: { fire: 2, ems: 2, paramedic: 1 },
      confidence: 0.97,
    },
    triage_status: 'ok',
    summary:
      'Apartment fire, second floor, ~6 families inside, blocked stairwell.',
    cluster_id: 'cl-northside-fire',
    primary_of_duplicate_group: 'inc-003',
    status: 'assigned',
  },

  // ---- 4: Duplicate of #3 — same fire, different caller (MERGED)
  {
    incident_id: 'inc-004',
    profile_id: undefined,
    device_id: 'dev-anon-008',
    location: { lat: 29.8101, lng: -95.3198, accuracy_m: 22, source: 'gps' },
    raw_text:
      "Big fire at the apartment complex on 18th, can see flames from across the street. People are screaming on the balconies.",
    needs: { fire: true, trapped: true },
    inventory_have: [],
    inventory_need: [],
    ts: TS('04'),
    severity: {
      score: 94,
      category: 'fire',
      top_reasons: [
        'Visible flames at apartment complex',
        'Multiple residents visible/audible in distress',
        'Same location and intent as primary report',
      ],
      required_resources: { fire: 1, ems: 1 },
      confidence: 0.93,
    },
    triage_status: 'ok',
    summary: 'Same apartment fire as inc-003 — semantic duplicate, merged.',
    cluster_id: 'cl-northside-fire',
    primary_of_duplicate_group: 'inc-003',
    status: 'open',
  },

  // ---- 5: Another duplicate of #3 (MERGED)
  {
    incident_id: 'inc-005',
    profile_id: undefined,
    device_id: 'dev-anon-009',
    location: { lat: 29.8098, lng: -95.3203, accuracy_m: 19, source: 'gps' },
    raw_text:
      'My neighbor is calling, the building next to us is on fire, the second floor, smoke everywhere.',
    needs: { fire: true },
    inventory_have: [],
    inventory_need: [],
    ts: TS('05'),
    severity: {
      score: 89,
      category: 'fire',
      top_reasons: [
        'Third reporter of same structure fire',
        'Neighboring witness, smoke spreading',
        'Cluster confidence high — vector similarity > 0.9',
      ],
      required_resources: { fire: 1 },
      confidence: 0.9,
    },
    triage_status: 'ok',
    summary: 'Third caller for same apartment fire.',
    cluster_id: 'cl-northside-fire',
    primary_of_duplicate_group: 'inc-003',
    status: 'open',
  },

  // ---- 6: Marcus, asthmatic, water (HIGH, assigned)
  {
    incident_id: 'inc-006',
    profile_id: 'pf-marcus',
    device_id: 'dev-marcus-003',
    location: { lat: 29.757, lng: -95.415, accuracy_m: 10, source: 'gps' },
    raw_text:
      "Asthma attack, I waded through floodwater to get my kid to higher ground. I'm wheezing bad.",
    needs: { medical: true, water: true },
    inventory_have: ['inhaler'],
    inventory_need: [],
    ts: TS('07'),
    severity: {
      score: 78,
      category: 'medical',
      top_reasons: [
        'Known asthma + acute distress',
        'Recent contaminated-water exposure',
        'Child with caller, secondary risk',
      ],
      required_resources: { ems: 1, paramedic: 1 },
      confidence: 0.88,
    },
    triage_status: 'ok',
    summary: 'Asthmatic adult, acute wheeze, child secondary.',
    status: 'assigned',
    profile_snapshot: SYNTHETIC_PROFILES['pf-marcus'],
  },

  // ---- 7: Ella, 8, trapped in attic (CRITICAL, assigned)
  {
    incident_id: 'inc-007',
    profile_id: 'pf-ella',
    device_id: 'dev-ella-004',
    location: { lat: 29.797, lng: -95.398, accuracy_m: 14, source: 'gps' },
    raw_text:
      "Uncle here, we're in the attic with my niece Ella, water is rising fast through the first floor. She's 8.",
    needs: { trapped: true, water: true },
    inventory_have: [],
    inventory_need: [],
    ts: TS('09'),
    severity: {
      score: 88,
      category: 'trapped',
      top_reasons: [
        'Child trapped in attic with rising floodwater',
        'No clear egress — boat rescue indicated',
        'Time-critical — water still rising',
      ],
      required_resources: { fire: 1, paramedic: 1, volunteer: 1 },
      confidence: 0.95,
    },
    triage_status: 'ok',
    summary: 'Child + adult trapped in attic, water still rising.',
    status: 'assigned',
    profile_snapshot: SYNTHETIC_PROFILES['pf-ella'],
  },

  // ---- 8: Low-confidence place description (MEDIUM, low_confidence_location)
  {
    incident_id: 'inc-008',
    profile_id: 'pf-anon',
    device_id: 'dev-anon-006',
    location: {
      lat: 29.738,
      lng: -95.575,
      source: 'place_description_udf',
      confidence: 0.42,
      description: "near the McDonald's and gas station off I-10 service road, big white church across the street",
    },
    raw_text:
      "I don't know the address, my phone GPS isn't working. Near the McDonald's and the gas station off I-10 service road, there's a big white church across the street.",
    needs: { shelter: true },
    inventory_have: [],
    inventory_need: [],
    ts: TS('11'),
    severity: {
      score: 65,
      category: 'shelter',
      top_reasons: [
        'Caller seeking shelter, no clear medical emergency',
        'Location resolved by description only — low confidence',
        'Service-road area, multiple possible matches',
      ],
      required_resources: { volunteer: 1 },
      confidence: 0.71,
    },
    triage_status: 'ok',
    summary: 'Adult seeking shelter; GPS unavailable, location estimated.',
    status: 'open',
  },

  // ---- 9: Robert, oxygen-dependent, NO DOCTOR AVAILABLE (UNMET RESOURCE)
  {
    incident_id: 'inc-009',
    profile_id: 'pf-robert',
    device_id: 'dev-robert-005',
    location: { lat: 29.7333, lng: -95.4256, accuracy_m: 9, source: 'gps' },
    raw_text:
      'Power has been out four hours, my oxygen concentrator stopped, I have one portable tank left. 72, COPD.',
    needs: { medical: true, power: true },
    inventory_have: ['oxygen'],
    inventory_need: ['oxygen'],
    ts: TS('13'),
    severity: {
      score: 84,
      category: 'medical',
      top_reasons: [
        'COPD patient on dwindling portable oxygen',
        'Power outage prevents concentrator restart',
        'Specialist (doctor) preferred — paramedic + ems already deployed',
      ],
      required_resources: { ems: 1, doctor: 1 },
      confidence: 0.91,
    },
    triage_status: 'ok',
    summary: 'COPD patient, low O2 reserves, power-dependent. Doctor unmet.',
    status: 'assigned', // partially — ems assigned, doctor unmet
    profile_snapshot: SYNTHETIC_PROFILES['pf-robert'],
  },

  // ---- 10: DEGRADED TRIAGE — Cortex JSON parse failure fallback
  {
    incident_id: 'inc-010',
    profile_id: undefined,
    device_id: 'dev-anon-010',
    location: { lat: 29.7964, lng: -95.3984, accuracy_m: 30, source: 'gps' },
    raw_text:
      "help help water everywhere can't see I'm scared please someone come",
    needs: {},
    inventory_have: [],
    inventory_need: [],
    ts: TS('15'),
    severity: {
      score: 50,
      category: 'unknown',
      top_reasons: [
        'AI severity output failed JSON validation — degraded fallback',
        'Free-text panic; no clear category extracted',
        'Manual review recommended in dashboard',
      ],
      required_resources: { volunteer: 1 },
      confidence: 0.2,
    },
    triage_status: 'degraded',
    summary: '(degraded) panic-text fragment; manual review recommended.',
    status: 'open',
  },

  // ---- 11: Low severity (INFO, open)
  {
    incident_id: 'inc-011',
    profile_id: undefined,
    device_id: 'dev-anon-011',
    location: { lat: 29.7522, lng: -95.358, accuracy_m: 11, source: 'gps' },
    raw_text:
      "Just letting you know my street is starting to flood ankle-deep, no one in trouble yet but watch this block.",
    needs: { water: true },
    inventory_have: [],
    inventory_need: [],
    ts: TS('17'),
    severity: {
      score: 32,
      category: 'water',
      top_reasons: [
        'Informational report from concerned resident',
        'No injury or trapped persons',
        'Useful for prepositioning volunteer resources',
      ],
      required_resources: { volunteer: 1 },
      confidence: 0.82,
    },
    triage_status: 'ok',
    summary: 'Ankle-deep flood report, no current injury.',
    status: 'open',
  },

  // ---- 12: CRITICAL INJECT — building collapse downtown
  // Used by "Inject Critical Incident" demo button.
  {
    incident_id: 'inc-012-inject',
    profile_id: undefined,
    device_id: 'dev-anon-inject',
    location: { lat: 29.7604, lng: -95.3698, accuracy_m: 6, source: 'gps' },
    raw_text:
      'Partial building collapse downtown — I count maybe 20 people trapped under debris on the lower levels.',
    needs: { trapped: true, medical: true, fire: true },
    inventory_have: [],
    inventory_need: [],
    ts: TS('45'),
    severity: {
      score: 98,
      category: 'trapped',
      top_reasons: [
        'Mass-casualty incident — ~20 trapped',
        'Structural collapse — heavy rescue required',
        'Downtown, multiple unit availability — recompute routes',
      ],
      required_resources: { fire: 3, paramedic: 2, ems: 2, doctor: 1 },
      confidence: 0.98,
    },
    triage_status: 'ok',
    summary: 'Building collapse downtown, ~20 trapped, heavy rescue needed.',
    status: 'open',
  },
];

// =============================================================
// Responder roster (per DEMO.md)
// =============================================================
export const FIXTURE_RESPONDERS: Responder[] = [
  // fire ×5
  { responder_id: 'r-fire-01', type: 'fire', callsign: 'Engine 14', current_location: { lat: 29.785, lng: -95.46 }, status: 'busy' },
  { responder_id: 'r-fire-02', type: 'fire', callsign: 'Engine 22', current_location: { lat: 29.81, lng: -95.33 }, status: 'busy' },
  { responder_id: 'r-fire-03', type: 'fire', callsign: 'Ladder 7', current_location: { lat: 29.795, lng: -95.40 }, status: 'busy' },
  { responder_id: 'r-fire-04', type: 'fire', callsign: 'Engine 31', current_location: { lat: 29.74, lng: -95.41 }, status: 'available' },
  { responder_id: 'r-fire-05', type: 'fire', callsign: 'Engine 09', current_location: { lat: 29.76, lng: -95.37 }, status: 'available' },
  // ems ×4
  { responder_id: 'r-ems-01', type: 'ems', callsign: 'Medic 18', current_location: { lat: 29.81, lng: -95.32 }, status: 'busy' },
  { responder_id: 'r-ems-02', type: 'ems', callsign: 'Medic 24', current_location: { lat: 29.75, lng: -95.41 }, status: 'busy' },
  { responder_id: 'r-ems-03', type: 'ems', callsign: 'Medic 36', current_location: { lat: 29.733, lng: -95.425 }, status: 'busy' },
  { responder_id: 'r-ems-04', type: 'ems', callsign: 'Medic 41', current_location: { lat: 29.76, lng: -95.38 }, status: 'available' },
  // paramedic ×3
  { responder_id: 'r-para-01', type: 'paramedic', callsign: 'Para 3', current_location: { lat: 29.79, lng: -95.48 }, status: 'busy' },
  { responder_id: 'r-para-02', type: 'paramedic', callsign: 'Para 5', current_location: { lat: 29.797, lng: -95.40 }, status: 'busy' },
  { responder_id: 'r-para-03', type: 'paramedic', callsign: 'Para 8', current_location: { lat: 29.76, lng: -95.37 }, status: 'available' },
  // nurse ×2
  { responder_id: 'r-nurse-01', type: 'nurse', callsign: 'RN-A', current_location: { lat: 29.76, lng: -95.40 }, status: 'available' },
  { responder_id: 'r-nurse-02', type: 'nurse', callsign: 'RN-B', current_location: { lat: 29.77, lng: -95.36 }, status: 'available' },
  // doctor ×2 (BOTH BUSY → unmet doctor need on inc-009)
  { responder_id: 'r-doc-01', type: 'doctor', callsign: 'Dr. Reyes', current_location: { lat: 29.80, lng: -95.35 }, status: 'busy' },
  { responder_id: 'r-doc-02', type: 'doctor', callsign: 'Dr. Chen', current_location: { lat: 29.74, lng: -95.42 }, status: 'busy' },
  // police ×6
  ...Array.from({ length: 6 }, (_, i) => ({
    responder_id: `r-pol-0${i + 1}`,
    type: 'police' as const,
    callsign: `PD-${100 + i}`,
    current_location: { lat: 29.76 + (i - 3) * 0.01, lng: -95.37 + (i - 3) * 0.01 },
    status: (i < 2 ? 'busy' : 'available') as 'busy' | 'available',
  })),
  // volunteer ×10
  ...Array.from({ length: 10 }, (_, i) => ({
    responder_id: `r-vol-${String(i + 1).padStart(2, '0')}`,
    type: 'volunteer' as const,
    callsign: `Vol-${i + 1}`,
    current_location: { lat: 29.76 + (i % 5) * 0.012, lng: -95.37 + ((i % 3) - 1) * 0.015 },
    status: (i < 3 ? 'busy' : 'available') as 'busy' | 'available',
  })),
];

export const FIXTURE_ROSTER: ResourceRoster[] = (() => {
  const buckets: Record<string, ResourceRoster> = {};
  for (const r of FIXTURE_RESPONDERS) {
    const b = buckets[r.type] ?? { type: r.type, total: 0, available: 0, busy: 0 };
    b.total += 1;
    if (r.status === 'available') b.available += 1;
    if (r.status === 'busy') b.busy += 1;
    buckets[r.type] = b;
  }
  return Object.values(buckets);
})();

// =============================================================
// Assignments (matches busy responders to incidents)
// =============================================================
export const FIXTURE_ASSIGNMENTS: Assignment[] = [
  // inc-001 (Sarah): fire + paramedic
  { assignment_id: 'a-001', incident_id: 'inc-001', responder_id: 'r-fire-01', resource_type: 'fire', eta_sec: 540, status: 'enroute', assigned_at: TS('01') },
  { assignment_id: 'a-002', incident_id: 'inc-001', responder_id: 'r-para-01', resource_type: 'paramedic', eta_sec: 600, status: 'enroute', assigned_at: TS('01') },
  // inc-002 (Tanya): volunteer + ems
  { assignment_id: 'a-003', incident_id: 'inc-002', responder_id: 'r-vol-01', resource_type: 'volunteer', eta_sec: 720, status: 'enroute', assigned_at: TS('03') },
  { assignment_id: 'a-004', incident_id: 'inc-002', responder_id: 'r-ems-02', resource_type: 'ems', eta_sec: 480, status: 'enroute', assigned_at: TS('03') },
  // inc-003 (apartment fire): fire ×2 + ems ×2 + paramedic ×1 → roster only has fire ×3 enroute capacity here, model partial
  { assignment_id: 'a-005', incident_id: 'inc-003', responder_id: 'r-fire-02', resource_type: 'fire', eta_sec: 240, status: 'enroute', assigned_at: TS('05') },
  { assignment_id: 'a-006', incident_id: 'inc-003', responder_id: 'r-fire-03', resource_type: 'fire', eta_sec: 360, status: 'enroute', assigned_at: TS('05') },
  { assignment_id: 'a-007', incident_id: 'inc-003', responder_id: 'r-ems-01', resource_type: 'ems', eta_sec: 300, status: 'enroute', assigned_at: TS('05') },
  // inc-006 (Marcus): ems
  { assignment_id: 'a-008', incident_id: 'inc-006', responder_id: 'r-ems-03', resource_type: 'ems', eta_sec: 420, status: 'enroute', assigned_at: TS('08') },
  // inc-007 (Ella): paramedic + fire (volunteer unmet)
  { assignment_id: 'a-009', incident_id: 'inc-007', responder_id: 'r-para-02', resource_type: 'paramedic', eta_sec: 360, status: 'enroute', assigned_at: TS('10') },
  // inc-009 (Robert): ems only — doctor unmet
  { assignment_id: 'a-010', incident_id: 'inc-009', responder_id: 'r-doc-01', resource_type: 'doctor', eta_sec: 900, status: 'enroute', assigned_at: TS('14') },
];

// =============================================================
// Unmet resource needs (judge-visible partial assignments)
// =============================================================
export const FIXTURE_UNMET: UnmetResourceNeed[] = [
  // inc-003: needs 1 more ems and 1 paramedic
  { incident_id: 'inc-003', resource_type: 'ems', quantity_needed: 1, reason: 'no_available_responder' },
  { incident_id: 'inc-003', resource_type: 'paramedic', quantity_needed: 1, reason: 'no_available_responder' },
  // inc-007: needs a volunteer for second hand
  { incident_id: 'inc-007', resource_type: 'volunteer', quantity_needed: 1, reason: 'no_available_responder' },
  // inc-009: doctor is busy with someone else
  { incident_id: 'inc-009', resource_type: 'doctor', quantity_needed: 1, reason: 'no_available_responder' },
];

// =============================================================
// Clusters (auto-merged duplicates + spatial groupings)
// =============================================================
export const FIXTURE_CLUSTERS: ClusterView[] = [
  {
    cluster_id: 'cl-northside-fire',
    centroid: { lat: 29.8099, lng: -95.32, },
    incident_ids: ['inc-003', 'inc-004', 'inc-005'],
    total_severity: 279,
    category_breakdown: { fire: 3, trapped: 2 },
  },
  {
    cluster_id: 'cl-spring-branch',
    centroid: { lat: 29.791, lng: -95.487 },
    incident_ids: ['inc-001'],
    total_severity: 92,
    category_breakdown: { trapped: 1, medical: 1 },
  },
  {
    cluster_id: 'cl-heights',
    centroid: { lat: 29.797, lng: -95.398 },
    incident_ids: ['inc-007', 'inc-010'],
    total_severity: 138,
    category_breakdown: { trapped: 1, unknown: 1 },
  },
];

// =============================================================
// Route previews (one per dispatched responder; demonstrates fallback)
// =============================================================
export const FIXTURE_ROUTES: RoutePreview[] = [
  {
    responder_id: 'r-para-01',
    assignment_ids: ['a-002'],
    stops: [{ incident_id: 'inc-001', eta_sec: 600, order: 1 }],
    polyline: 'mockpolyline_para01',
    total_eta_sec: 600,
    route_source: 'mapbox',
  },
  {
    responder_id: 'r-fire-02',
    assignment_ids: ['a-005', 'a-006'],
    stops: [
      { incident_id: 'inc-003', eta_sec: 240, order: 1 },
      { incident_id: 'inc-005', eta_sec: 360, order: 2 },
    ],
    polyline: 'mockpolyline_fire02',
    total_eta_sec: 360,
    route_source: 'mapbox',
  },
  {
    responder_id: 'r-ems-03',
    assignment_ids: ['a-008'],
    stops: [{ incident_id: 'inc-006', eta_sec: 420, order: 1 }],
    total_eta_sec: 420,
    route_source: 'fallback', // <-- visible route fallback case
  },
  {
    responder_id: 'r-vol-01',
    assignment_ids: ['a-003'],
    stops: [{ incident_id: 'inc-002', eta_sec: 720, order: 1 }],
    polyline: 'mockpolyline_vol01',
    total_eta_sec: 720,
    route_source: 'cached',
  },
];

// =============================================================
// Victim status fixtures (one per state for /demo)
// =============================================================
export const FIXTURE_VICTIM_STATUSES: Record<string, VictimStatusView> = {
  received: {
    incident_id: 'inc-001',
    state: 'received',
    message: 'Help is on the way. Stay where you are.',
    severity_score: 92,
    category: 'trapped',
  },
  triaging: {
    incident_id: 'inc-006',
    state: 'triaging',
    message: 'Reviewing your situation right now.',
    severity_score: 78,
    category: 'medical',
  },
  assigned: {
    incident_id: 'inc-001',
    state: 'assigned',
    message: 'A fire crew and a paramedic are headed to you.',
    eta_sec: 540,
    assigned_resource_types: ['fire', 'paramedic'],
    severity_score: 92,
    category: 'trapped',
  },
  low_confidence_location: {
    incident_id: 'inc-008',
    state: 'low_confidence_location',
    message:
      "We're using the description you gave us. If you can, share more about what's around you.",
    location_confidence: 0.42,
    severity_score: 65,
    category: 'shelter',
  },
  unmet_resource: {
    incident_id: 'inc-009',
    state: 'unmet_resource',
    message:
      'An EMT is on the way. A doctor is being requested for follow-up.',
    eta_sec: 600,
    assigned_resource_types: ['ems'],
    severity_score: 84,
    category: 'medical',
  },
};

// =============================================================
// Initial dashboard snapshot (before scenario plays)
// =============================================================
export const FIXTURE_INITIAL_DASHBOARD: DashboardState = {
  mode: 'fixture',
  scenario: {
    name: 'texas-flood',
    label: 'Houston Flash Flood, May 2026',
    elapsed_sec: 0,
    status: 'idle',
  },
  incidents: [],
  clusters: [],
  assignments: [],
  unmet_resource_needs: [],
  routes: [],
  roster: FIXTURE_ROSTER,
  responders: FIXTURE_RESPONDERS,
};

// =============================================================
// 60-second scripted timeline
// Each event is replayed by the fixture adapter at `at_sec`.
// =============================================================
export const FIXTURE_TIMELINE: FixtureTimelineEvent[] = [
  // Beat 1 — flood begins
  { at_sec: 2, type: 'incident_new', payload: FIXTURE_INCIDENTS[0] },
  { at_sec: 4, type: 'incident_new', payload: FIXTURE_INCIDENTS[1] },
  { at_sec: 6, type: 'incident_new', payload: FIXTURE_INCIDENTS[2] },
  { at_sec: 8, type: 'incident_new', payload: FIXTURE_INCIDENTS[3] },
  { at_sec: 9, type: 'incident_new', payload: FIXTURE_INCIDENTS[4] },
  { at_sec: 10, type: 'cluster_update', payload: FIXTURE_CLUSTERS[0] }, // northside fire cluster merges
  { at_sec: 12, type: 'incident_new', payload: FIXTURE_INCIDENTS[5] },
  { at_sec: 15, type: 'incident_new', payload: FIXTURE_INCIDENTS[6] },
  { at_sec: 18, type: 'incident_new', payload: FIXTURE_INCIDENTS[7] }, // low-confidence location
  { at_sec: 21, type: 'incident_new', payload: FIXTURE_INCIDENTS[8] }, // unmet doctor
  { at_sec: 24, type: 'incident_new', payload: FIXTURE_INCIDENTS[9] }, // degraded triage
  { at_sec: 27, type: 'incident_new', payload: FIXTURE_INCIDENTS[10] }, // low sev

  // Beat 2 — assignments roll in
  { at_sec: 13, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[0] },
  { at_sec: 14, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[1] },
  { at_sec: 16, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[2] },
  { at_sec: 17, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[3] },
  { at_sec: 19, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[4] },
  { at_sec: 20, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[5] },
  { at_sec: 22, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[6] },
  { at_sec: 25, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[7] },
  { at_sec: 28, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[8] },
  { at_sec: 30, type: 'assignment_new', payload: FIXTURE_ASSIGNMENTS[9] },

  // Routes
  { at_sec: 23, type: 'route_update', payload: FIXTURE_ROUTES[0] },
  { at_sec: 26, type: 'route_update', payload: FIXTURE_ROUTES[1] },
  { at_sec: 29, type: 'route_update', payload: FIXTURE_ROUTES[2] }, // fallback route visible
  { at_sec: 31, type: 'route_update', payload: FIXTURE_ROUTES[3] },

  // Roster updates as units go busy
  { at_sec: 32, type: 'resource_update', payload: FIXTURE_ROSTER },

  // Clusters fill in
  { at_sec: 33, type: 'cluster_update', payload: FIXTURE_CLUSTERS[1] },
  { at_sec: 35, type: 'cluster_update', payload: FIXTURE_CLUSTERS[2] },

  // Beat 5 — inject critical (will only fire if user clicks Inject or scenario plays to end)
  { at_sec: 45, type: 'incident_new', payload: FIXTURE_INCIDENTS[11] }, // inc-012-inject
];

// Convenience: inject payload alone (used by the Inject button on demand)
export const INJECT_CRITICAL_INCIDENT: IncidentEnriched = FIXTURE_INCIDENTS[11]!;

// =============================================================
// Default initial scenario state for UI
// =============================================================
export const INITIAL_SCENARIO: ScenarioState = {
  name: 'texas-flood',
  label: 'Houston Flash Flood, May 2026',
  elapsed_sec: 0,
  status: 'idle',
};

// =============================================================
// Re-export types we use frequently (convenience for app code)
// =============================================================
export type {
  Assignment,
  ClusterView,
  DashboardState,
  FixtureTimelineEvent,
  IncidentEnriched,
  Profile,
  Responder,
  ResourceRoster,
  RoutePreview,
  ScenarioState,
  UnmetResourceNeed,
  VictimStatusView,
} from '@disaster/types';
