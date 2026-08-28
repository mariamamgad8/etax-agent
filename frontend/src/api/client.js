const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function request(path, { method = 'GET', token, body, isForm } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body && !isForm) headers['Content-Type'] = 'application/json';

  let res;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('Could not reach the server. Check your connection and try again.', 0, null);
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    // no JSON body
  }

  if (!res.ok) {
    const detail = data && data.detail ? data.detail : 'Something went wrong. Try again.';
    const message = typeof detail === 'string' ? detail : 'Something went wrong. Try again.';
    throw new ApiError(message, res.status, data);
  }
  return data;
}

export const api = {
  signup: (payload) => request('/auth/signup', { method: 'POST', body: payload }),
  login: (payload) => request('/auth/login', { method: 'POST', body: payload }),
  me: (token) => request('/auth/me', { token }),
  enrollFace: (token, blob) => {
    const form = new FormData();
    form.append('image', blob, 'capture.jpg');
    return request('/face/enroll', { method: 'POST', token, body: form, isForm: true });
  },
  verifyFace: (token, blob) => {
    const form = new FormData();
    form.append('image', blob, 'capture.jpg');
    return request('/face/verify', { method: 'POST', token, body: form, isForm: true });
  },
  getWelcome: (token, language) => request(`/chat/welcome?language=${encodeURIComponent(language)}`, { token }),
  // threadId is reused across the whole chat session (not just interrupt
  // resumes) once the first response hands one back — this is what lets the
  // backend's cross-turn memory (see graph.py's prepare_db_question) work at
  // all, since a fresh thread_id would start memory over on every message.
  sendChatMessage: (token, message, threadId) =>
    request('/chat/message', { method: 'POST', token, body: { message, thread_id: threadId || undefined } }),
  resumeChatForm: (token, threadId, formResponse) =>
    request('/chat/message', {
      method: 'POST',
      token,
      body: { thread_id: threadId, form_response: formResponse },
    }),
  transcribeAudio: (token, blob, filename) => {
    const form = new FormData();
    form.append('audio', blob, filename);
    return request('/chat/transcribe', { method: 'POST', token, body: form, isForm: true });
  },
  speakText: async (token, text) => {
    let res;
    try {
      res = await fetch(`${API_BASE_URL}/chat/speak`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
    } catch {
      throw new ApiError('Could not reach the server for voice output.', 0, null);
    }
    if (!res.ok) {
      let message = 'Could not generate voice audio.';
      try {
        const data = await res.json();
        if (data && data.detail) message = data.detail;
      } catch {
        // no JSON body
      }
      throw new ApiError(message, res.status, null);
    }
    return res.blob();
  },
};
