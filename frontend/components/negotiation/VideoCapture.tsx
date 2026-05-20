import React, { useEffect, useRef } from 'react';
import { Camera, CameraOff, Video } from 'lucide-react';

interface VideoCaptureProps {
  isActive: boolean;
  onToggle: () => void;
  /** Called each frame with base64 JPEG and a live_mode flag */
  onFrameCapture?: (base64Jpeg: string, isLiveMode: boolean) => void;
  /** Capture interval in ms. Defaults to 1000ms (1 FPS). Scene-change filter
   *  in the backend means Pro only fires when content actually changes. */
  frameIntervalMs?: number;
  /** True when the user is holding the "talk to AI" button — frames are also
   *  forwarded to the Gemini Live session so it can see while listening. */
  isLiveActive?: boolean;
}

export function VideoCapture({
  isActive,
  onToggle,
  onFrameCapture,
  frameIntervalMs = 1000,
  isLiveActive = false,
}: VideoCaptureProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const captureTimerRef = useRef<NodeJS.Timeout | null>(null);
  const isLiveActiveRef = useRef(isLiveActive);
  const lastFrameSignatureRef = useRef<string>('');

  useEffect(() => {
    let active = true;

    async function setupCamera() {
      if (isActive) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
            audio: false
          });

          if (!active) {
            stream.getTracks().forEach(t => t.stop());
            return;
          }

          streamRef.current = stream;
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
          }
        } catch (err) {
          console.error("Error accessing camera:", err);
        }
      } else {
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop());
          streamRef.current = null;
        }
        if (videoRef.current) {
          videoRef.current.srcObject = null;
        }
      }
    }

    setupCamera();

    return () => {
      active = false;
      if (captureTimerRef.current) {
        clearInterval(captureTimerRef.current);
        captureTimerRef.current = null;
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      lastFrameSignatureRef.current = '';
    };
  }, [isActive]);

  // Keep ref in sync so the interval callback always sees the latest value
  useEffect(() => {
    isLiveActiveRef.current = isLiveActive;
  }, [isLiveActive]);

  useEffect(() => {
    if (!isActive || !onFrameCapture || !videoRef.current) {
      if (captureTimerRef.current) {
        clearInterval(captureTimerRef.current);
        captureTimerRef.current = null;
      }
      return;
    }

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    captureTimerRef.current = setInterval(() => {
      const video = videoRef.current;
      if (!video || video.videoWidth === 0 || video.videoHeight === 0) return;

      const maxWidth = 640;
      const scale = Math.min(1, maxWidth / video.videoWidth);
      canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
      canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
      const base64 = dataUrl.split(',')[1];
      if (base64) {
        const frameSignature = `${base64.length}:${base64.slice(0, 96)}:${base64.slice(-96)}`;
        if (frameSignature === lastFrameSignatureRef.current) {
          return;
        }
        lastFrameSignatureRef.current = frameSignature;
        onFrameCapture(base64, isLiveActiveRef.current);
      }
    }, frameIntervalMs);

    return () => {
      if (captureTimerRef.current) {
        clearInterval(captureTimerRef.current);
        captureTimerRef.current = null;
      }
    };
  }, [frameIntervalMs, isActive, onFrameCapture]);

  return (
    <div className="relative w-full aspect-video bg-neutral-900 rounded-xl overflow-hidden shadow-lg border border-neutral-800 flex flex-col group transition-all">
      {/* Container for the video stream (placeholder) */}
      <div className="flex-1 flex items-center justify-center relative">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={`absolute inset-0 w-full h-full object-cover ${isActive ? 'opacity-100' : 'opacity-0'}`}
        />

        {!isActive && (
          <div className="flex flex-col items-center justify-center text-neutral-500 space-y-2 z-10 w-full h-full absolute inset-0 bg-neutral-900">
            <CameraOff className="w-12 h-12 opacity-50" />
            <p className="text-sm font-medium">Camera Inactive</p>
          </div>
        )}

        {isActive && (
          <div className="absolute top-3 left-3 flex items-center gap-1.5 z-10">
            <span className="relative flex h-2.5 w-2.5">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isLiveActive ? 'bg-blue-400' : 'bg-red-400'}`}></span>
              <span className={`relative inline-flex rounded-full h-full w-full ${isLiveActive ? 'bg-blue-500' : 'bg-red-500'}`}></span>
            </span>
            <span className="text-[10px] font-semibold text-white/80 uppercase tracking-wide">
              {isLiveActive ? 'Live Vision' : 'AI Observing'}
            </span>
          </div>
        )}
      </div>

      {/* Overlay controls - visible on hover or active state */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-end p-4 z-20">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 text-white/90">
            <Video className="w-4 h-4" />
            <span className="text-xs font-semibold">{isActive ? "User Feed (Live)" : "User Feed (Paused)"}</span>
          </div>
          <button
            onClick={onToggle}
            className={`p-2 rounded-full backdrop-blur-md transition-colors ${isActive
                ? 'bg-rose-500/20 text-rose-500 hover:bg-rose-500/30'
                : 'bg-white/10 text-white hover:bg-white/20'
              }`}
            title={isActive ? "Turn off camera" : "Turn on camera"}
          >
            {isActive ? <CameraOff className="w-5 h-5" /> : <Camera className="w-5 h-5" />}
          </button>
        </div>
      </div>
    </div>
  );
}
