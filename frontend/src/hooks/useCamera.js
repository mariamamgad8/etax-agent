import React from 'react';

/**
 * Drives a live webcam feed for the face enrollment/verification screens.
 * Frames are captured straight from the <video> element into a canvas and
 * exported as a JPEG Blob — never a file upload — matching the capture
 * approach in the mariam_face_recognition reference UI.
 */
export function useCamera() {
  const videoRef = React.useRef(null);
  const streamRef = React.useRef(null);
  const [status, setStatus] = React.useState('idle'); // idle | starting | ready | denied | error
  const [error, setError] = React.useState('');

  const start = React.useCallback(async () => {
    setStatus('starting');
    setError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setStatus('ready');
    } catch (err) {
      setStatus(err && err.name === 'NotAllowedError' ? 'denied' : 'error');
      setError((err && err.message) || 'Could not access the camera.');
    }
  }, []);

  const stop = React.useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const captureFrame = React.useCallback(() => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return Promise.resolve(null);
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.92));
  }, []);

  React.useEffect(() => () => stop(), [stop]);

  return { videoRef, status, error, start, stop, captureFrame };
}
