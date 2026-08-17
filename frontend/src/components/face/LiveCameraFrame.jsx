import React from 'react';

const STATUS_TEXT = {
  starting: 'Starting camera…',
  denied: 'Camera permission denied',
  error: 'Camera unavailable',
  idle: 'Waiting for camera…',
};

/** Live webcam feed inside the design's camera frame chrome (ring, LIVE badge). */
export function LiveCameraFrame({ videoRef, stage, failed, cameraStatus }) {
  const live = cameraStatus === 'ready' && !failed && stage !== 'verified';
  const ringColor = failed
    ? 'var(--danger)'
    : stage === 'verified'
      ? 'var(--success)'
      : cameraStatus !== 'ready'
        ? 'rgba(255,255,255,.55)'
        : 'var(--etax-red)';
  return (
    <div style={{ position: 'relative', aspectRatio: '4 / 3', background: 'var(--etax-navy-900)', borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '1px solid var(--etax-navy-800)' }}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{
          position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover',
          transform: 'scaleX(-1)', opacity: cameraStatus === 'ready' ? 1 : 0,
        }}
      />
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{
          width: '46%', height: '72%', border: `2px ${cameraStatus !== 'ready' ? 'dashed' : 'solid'} ${ringColor}`,
          borderRadius: '50% / 42%', transition: 'border-color var(--dur-med) var(--ease-standard)',
        }} />
      </div>
      <span style={{ position: 'absolute', top: 12, left: 12, display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 8px', borderRadius: 'var(--radius-xs)', background: 'rgba(15,37,69,.72)', color: 'var(--white)', fontSize: 'var(--text-caption)', fontFamily: 'var(--font-mono)' }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: live ? 'var(--etax-red)' : 'var(--gray-400)', animation: live ? 'etaxPulse var(--dur-pulse) var(--ease-in-out) infinite' : 'none' }} />
        {live ? 'LIVE' : 'PAUSED'}
      </span>
      {cameraStatus !== 'ready' && (
        <span style={{ position: 'absolute', bottom: 12, left: 12, right: 12, textAlign: 'center', color: 'rgba(255,255,255,.62)', fontSize: 'var(--text-caption)' }}>
          {STATUS_TEXT[cameraStatus] || STATUS_TEXT.idle}
        </span>
      )}
      <style>{'@keyframes etaxPulse{0%,100%{opacity:1}50%{opacity:.25}}'}</style>
    </div>
  );
}
