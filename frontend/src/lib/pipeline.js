import {
  Radar, ScanEye, Timer, Wind, Siren, Ruler, Gauge, Droplets, ShieldCheck, CheckCircle2,
  Ban, AlertTriangle, CloudFog, PhoneCall,
} from 'lucide-react';

// Order and metadata of the decision pipeline (mirrors backend app/pipeline.py)
export const STAGES = [
  { key: 'FIRE_DETECTED', short: 'Detect', label: 'YOLOv8 Detection', icon: ScanEye, tag: 'AI' },
  { key: 'TEMPORAL_VALIDATION', short: 'Validate', label: 'Temporal Validation', icon: Timer, tag: 'AI' },
  { key: 'SENSOR_FUSION', short: 'Smoke', label: 'Smoke Corroboration', icon: Wind, tag: 'SENSOR' },
  { key: 'FIRE_CONFIRMED', short: 'Confirm', label: 'Fire Confirmed', icon: Siren, tag: 'SYSTEM' },
  { key: 'DISTANCE_ESTIMATION', short: 'Distance', label: 'LiDAR Distance', icon: Ruler, tag: 'SENSOR' },
  { key: 'PRESSURE_ESTIMATION', short: 'Pressure', label: 'Pressure Estimation', icon: Gauge, tag: 'PHYSICS' },
  { key: 'SUPPRESSION_ACTIVE', short: 'Suppress', label: 'Suppression', icon: Droplets, tag: 'ACTUATOR' },
  { key: 'VERIFICATION', short: 'Verify', label: 'Verification', icon: ShieldCheck, tag: 'AI' },
  { key: 'SUPPRESSION_COMPLETE', short: 'Complete', label: 'Complete', icon: CheckCircle2, tag: 'SYSTEM' },
];

export const STATE_META = {
  MONITORING: { label: 'Monitoring', tone: 'safe', icon: Radar },
  FIRE_DETECTED: { label: 'Fire Detected', tone: 'warn', icon: ScanEye },
  TEMPORAL_VALIDATION: { label: 'Temporal Validation', tone: 'warn', icon: Timer },
  SENSOR_FUSION: { label: 'Smoke Corroboration', tone: 'warn', icon: Wind },
  FIRE_CONFIRMED: { label: 'Fire Confirmed', tone: 'fire', icon: Siren },
  DISTANCE_ESTIMATION: { label: 'Distance Estimation', tone: 'info', icon: Ruler },
  PRESSURE_ESTIMATION: { label: 'Pressure Estimation', tone: 'info', icon: Gauge },
  SUPPRESSION_ACTIVE: { label: 'Suppression Active', tone: 'water', icon: Droplets },
  VERIFICATION: { label: 'Verification', tone: 'water', icon: ShieldCheck },
  SUPPRESSION_COMPLETE: { label: 'Suppression Complete', tone: 'safe', icon: CheckCircle2 },
  FALSE_ALARM_REJECTED: { label: 'False Alarm Rejected', tone: 'muted', icon: Ban },
  VISION_ONLY_ALERT: { label: 'Unconfirmed - Operator Check', tone: 'alert', icon: AlertTriangle },
  SMOKE_ONLY_ALERT: { label: 'Smoke Only - Operator Check', tone: 'alert', icon: CloudFog },
  ESCALATED: { label: 'Escalated to Fire Services', tone: 'fire', icon: PhoneCall },
};

export const TONES = {
  safe: { text: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30', solid: 'border-green-500', dot: 'bg-green-500', hex: '#22c55e' },
  warn: { text: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30', solid: 'border-orange-500', dot: 'bg-orange-500', hex: '#f97316' },
  fire: { text: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30', solid: 'border-red-500', dot: 'bg-red-500', hex: '#ef4444' },
  info: { text: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30', solid: 'border-blue-500', dot: 'bg-blue-500', hex: '#3b82f6' },
  water: { text: 'text-sky-300', bg: 'bg-sky-500/10', border: 'border-sky-500/30', solid: 'border-sky-400', dot: 'bg-sky-400', hex: '#38bdf8' },
  alert: { text: 'text-yellow-300', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', solid: 'border-yellow-400', dot: 'bg-yellow-400', hex: '#facc15' },
  muted: { text: 'text-gray-300', bg: 'bg-gray-500/10', border: 'border-gray-500/30', solid: 'border-gray-400', dot: 'bg-gray-400', hex: '#9ca3af' },
};

export const OUTCOME_META = {
  EXTINGUISHED: { label: 'Extinguished', tone: 'safe' },
  FALSE_ALARM_REJECTED: { label: 'False alarm rejected', tone: 'muted' },
  VISION_ONLY_ALERT: { label: 'Operator alert (no smoke)', tone: 'alert' },
  SMOKE_ONLY_ALERT: { label: 'Operator alert (smoke only)', tone: 'alert' },
  ESCALATED: { label: 'Escalated', tone: 'fire' },
  ABORTED: { label: 'Aborted (reset)', tone: 'muted' },
};

export const toneOf = (state) => TONES[STATE_META[state]?.tone ?? 'muted'];

export const fmt = (v, digits = 2, fallback = '—') =>
  v === null || v === undefined || Number.isNaN(v) ? fallback : Number(v).toFixed(digits);
