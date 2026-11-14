import { useState, useRef, useCallback } from 'react';
import { Camera, Maximize2, Minimize2 } from 'lucide-react';
import StatusIndicator from '../common/StatusIndicator';
import { getCameraStreamUrl } from '../../services/api';

export default function CameraFeed({ telemetry }) {
  const [imgError, setImgError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef(null);

  const connected = Boolean(telemetry?.camera_connected) && !imgError;
  const source = telemetry?.camera_source;
  const simulated = source === 'scenario';

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  }, []);

  const handleError = () => {
    setImgError(true);
    setTimeout(() => { setImgError(false); setRetryKey((k) => k + 1); }, 3000); // auto-retry the stream
  };

  return (
    <div ref={containerRef} className={`bg-[#1a1f2e] rounded-xl border border-[#2a3142] overflow-hidden flex flex-col ${isFullscreen ? 'bg-black' : ''}`}>
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#2a3142]">
        <div className="flex items-center gap-2">
          <Camera className="w-4 h-4 text-gray-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-300">Camera · AI view</span>
          {source && (
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${simulated ? 'bg-yellow-500/15 text-yellow-300' : 'bg-red-500/15 text-red-300'}`}>
              {simulated ? 'SIMULATED SCENE' : source === 'webcam' ? 'WEBCAM' : 'LIVE IP CAMERA'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <StatusIndicator status={connected ? 'normal' : 'danger'} size="sm" />
          <span className={`text-[10px] font-medium ${connected ? 'text-green-400' : 'text-red-400'}`}>
            {connected ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
        </div>
      </div>

      <div className="relative bg-black aspect-video">
        {!imgError ? (
          <img key={retryKey} src={getCameraStreamUrl()} alt="Annotated camera feed"
            className="absolute inset-0 w-full h-full object-contain" onError={handleError} />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-[#0d1117]">
            <Camera className="w-16 h-16 text-gray-700 mb-3" />
            <p className="text-sm font-medium text-gray-500">Video stream unavailable</p>
            <p className="text-xs text-gray-600 mt-1">Retrying…</p>
          </div>
        )}
        <button onClick={toggleFullscreen} title="Fullscreen"
          className="absolute bottom-3 right-3 p-1.5 rounded-md bg-black/50 backdrop-blur-sm hover:bg-black/70 transition-colors">
          {isFullscreen ? <Minimize2 className="w-4 h-4 text-gray-300" /> : <Maximize2 className="w-4 h-4 text-gray-300" />}
        </button>
      </div>
    </div>
  );
}
