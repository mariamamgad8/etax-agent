import React from 'react';

// What MediaRecorder actually produces per browser (checked live): Chrome/Edge
// only offer webm/opus, Firefox also offers ogg/opus. Cohere Transcribe
// rejects both — its supported extensions are flac/mp3/mpeg/mpga/ogg/wav only
// (confirmed via a live 400: "unsupported file extension ... got: webm") — so
// recording straight to webm makes the Cohere-first fallback chain silently
// skip to Groq on every single browser recording. Recording is decoded and
// re-encoded to WAV client-side below specifically so Cohere is actually
// reachable, not just Groq every time.
const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
const MAX_RECORDING_MS = 60_000; // safety cap so a forgotten-on mic can't record indefinitely

function pickMimeType() {
  if (typeof MediaRecorder === 'undefined') return null;
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) ?? '';
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
}

function floatTo16BitPCM(view, offset, input) {
  for (let i = 0; i < input.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
}

function interleaveStereo(left, right) {
  const out = new Float32Array(left.length + right.length);
  for (let i = 0, j = 0; i < left.length; i++) {
    out[j++] = left[i];
    out[j++] = right[i];
  }
  return out;
}

/** Encodes a decoded AudioBuffer as a 16-bit PCM WAV Blob. */
function encodeWav(audioBuffer) {
  const numChannels = audioBuffer.numberOfChannels;
  const sampleRate = audioBuffer.sampleRate;
  const bitDepth = 16;
  const samples =
    numChannels === 2
      ? interleaveStereo(audioBuffer.getChannelData(0), audioBuffer.getChannelData(1))
      : audioBuffer.getChannelData(0);

  const dataLength = samples.length * (bitDepth / 8);
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * (bitDepth / 8), true);
  view.setUint16(32, numChannels * (bitDepth / 8), true);
  view.setUint16(34, bitDepth, true);
  writeString(view, 36, 'data');
  view.setUint32(40, dataLength, true);
  floatTo16BitPCM(view, 44, samples);

  return new Blob([view], { type: 'audio/wav' });
}

/** Decodes whatever MediaRecorder produced (webm/ogg/mp4) into a WAV Blob. */
async function toWavBlob(recordedBlob) {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  const audioCtx = new AudioCtx();
  try {
    const arrayBuffer = await recordedBlob.arrayBuffer();
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
    return encodeWav(audioBuffer);
  } finally {
    audioCtx.close();
  }
}

/**
 * Records mic audio via MediaRecorder and hands back a Blob on stop.
 * Mirrors useCamera's status/error shape so callers follow the same pattern
 * as face capture: start() -> status transitions -> a result via a callback.
 */
export function useVoiceRecorder() {
  const recorderRef = React.useRef(null);
  const chunksRef = React.useRef([]);
  const streamRef = React.useRef(null);
  const autoStopTimerRef = React.useRef(null);
  const [status, setStatus] = React.useState('idle'); // idle | recording | denied | error | unsupported
  const [error, setError] = React.useState('');

  const _cleanupStream = React.useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
  }, []);

  const start = React.useCallback(
    (onResult) => {
      if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
        setStatus('unsupported');
        setError('Voice input is not supported in this browser.');
        return;
      }
      setError('');
      navigator.mediaDevices
        .getUserMedia({ audio: true })
        .then((stream) => {
          streamRef.current = stream;
          const mimeType = pickMimeType();
          const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
          recorderRef.current = recorder;
          chunksRef.current = [];

          recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
          };
          recorder.onstop = async () => {
            const usedType = recorder.mimeType || mimeType || 'audio/webm';
            const recordedBlob = new Blob(chunksRef.current, { type: usedType });
            _cleanupStream();
            setStatus('idle');
            try {
              const wavBlob = await toWavBlob(recordedBlob);
              onResult(wavBlob, 'recording.wav');
            } catch (err) {
              // Decoding failed (unsupported codec in this browser) — send the
              // raw recording; the backend's Groq fallback still accepts it,
              // just skipping Cohere for this one clip.
              onResult(recordedBlob, `recording.${usedType.split('/')[1]?.split(';')[0] || 'webm'}`);
            }
          };
          recorder.onerror = (e) => {
            _cleanupStream();
            setStatus('error');
            setError((e.error && e.error.message) || 'Recording failed.');
          };

          recorder.start();
          setStatus('recording');
          autoStopTimerRef.current = setTimeout(() => recorder.state === 'recording' && recorder.stop(), MAX_RECORDING_MS);
        })
        .catch((err) => {
          setStatus(err && err.name === 'NotAllowedError' ? 'denied' : 'error');
          setError((err && err.message) || 'Could not access the microphone.');
        });
    },
    [_cleanupStream],
  );

  const stop = React.useCallback(() => {
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      recorderRef.current.stop();
    }
  }, []);

  React.useEffect(() => () => _cleanupStream(), [_cleanupStream]);

  return { status, error, start, stop };
}
