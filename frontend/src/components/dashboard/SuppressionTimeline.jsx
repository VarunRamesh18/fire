import { AlertTriangle } from 'lucide-react';
import PipelineStepper from '../pipeline/PipelineStepper';

export default function SuppressionTimeline({ telemetry }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-4 py-2 rounded-lg bg-yellow-500/5 border border-yellow-500/10">
        <AlertTriangle className="w-4 h-4 text-yellow-500 shrink-0" />
        <p className="text-xs text-yellow-400">
          <span className="font-semibold">SIMULATION</span> — the pump, valve and water jet are simulated; detection runs the real YOLOv8 model.
        </p>
      </div>
      <PipelineStepper pipeline={telemetry?.pipeline} />
    </div>
  );
}
