import { ScanEye } from 'lucide-react';
import StageCard, { Meter, Stat } from './StageCard';
import { fmt } from '../../lib/pipeline';

export default function DetectionCard({ t, active }) {
  const det = t?.detector ?? {};
  const thr = det.threshold ?? 0.5;
  const conf = t?.confidence ?? 0;
  const boxes = [...(t?.bounding_boxes ?? [])].sort((a, b) => b.conf - a.conf).slice(0, 4);
  const yolo = det.mode === 'yolov8';
  const modelName = (det.model_path ?? '').split('/').pop();

  return (
    <StageCard title="YOLOv8 Fire Detection" icon={ScanEye} tag="AI" step={1} active={active}>
      <div className={`text-[10px] mb-3 px-2 py-1 rounded border ${yolo ? 'border-purple-500/20 bg-purple-500/5 text-purple-300' : 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300'}`}>
        {yolo
          ? <>Model <span className="font-mono">{modelName}</span> · classes {Object.values(det.classes ?? {}).join(', ')} · {det.imgsz}px</>
          : <>YOLO model not loaded ({det.load_error}) — classical colour-segmentation fallback in use</>}
      </div>
      <div className="flex items-end gap-4 mb-2">
        <div>
          <p className="text-[9px] uppercase tracking-wider text-gray-500">Fire confidence</p>
          <p className={`text-4xl font-mono font-bold tabular-nums ${conf >= thr ? 'text-red-400' : 'text-gray-300'}`}>
            {(conf * 100).toFixed(0)}<span className="text-lg text-gray-500">%</span>
          </p>
        </div>
        <div className="grid grid-cols-3 gap-3 flex-1">
          <Stat small label="Inference" value={fmt(t?.inference_ms, 0)} unit="ms" />
          <Stat small label="AI rate" value={fmt(t?.detection_fps, 1)} unit="fps" />
          <Stat small label="Video" value={fmt(t?.fps, 0)} unit="fps" />
        </div>
      </div>
      <Meter value={conf} max={1} colour={conf >= thr ? 'bg-red-500' : 'bg-gray-500'} marker={thr} markerLabel="alarm threshold" />
      <p className="text-[10px] text-gray-500 mt-1">White marker = alarm threshold {(thr * 100).toFixed(0)}%</p>
      <div className="mt-3 space-y-1">
        {boxes.length === 0 && <p className="text-[11px] text-gray-600">No objects detected in the current frame</p>}
        {boxes.map((b, i) => (
          <div key={i} className="flex items-center gap-2 text-[11px]">
            <span className={`w-14 font-semibold ${b.kind === 'fire' ? 'text-red-400' : b.kind === 'smoke' ? 'text-gray-300' : 'text-gray-500'}`}>{b.label}</span>
            <div className="flex-1"><Meter value={b.conf} height="h-1.5" colour={b.kind === 'fire' ? 'bg-red-500/80' : 'bg-gray-400/70'} /></div>
            <span className="font-mono text-gray-400 w-10 text-right">{(b.conf * 100).toFixed(0)}%</span>
            <span className="font-mono text-gray-600 w-24 text-right hidden xl:inline">{Math.round(b.x2 - b.x1)}×{Math.round(b.y2 - b.y1)} px</span>
          </div>
        ))}
      </div>
    </StageCard>
  );
}
