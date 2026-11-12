const BASE = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body?.detail?.message ?? body?.detail ?? message;
      if (typeof message !== "string") message = JSON.stringify(message);
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const api = {
  get<T>(path: string) {
    return request<T>(path);
  },
  post<T>(path: string, body?: unknown, isForm = false) {
    if (isForm) {
      return request<T>(path, { method: "POST", body: body as FormData });
    }
    return request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
  upload<T>(path: string, form: FormData) {
    return request<T>(path, { method: "POST", body: form });
  },
  downloadUrl(path: string) {
    return `${BASE}${path}`;
  },
};
