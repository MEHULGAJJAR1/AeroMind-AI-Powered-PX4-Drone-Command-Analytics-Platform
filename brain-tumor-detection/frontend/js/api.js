/**
 * Thin client for the Flask REST API. All URLs are relative, so the UI works
 * behind any reverse proxy or preview host without configuration.
 */

const BASE_URL = "/api";

export class ApiError extends Error {
  constructor(message, { status = 0, code = "UNKNOWN", details = {} } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch (_networkError) {
    throw new ApiError("Cannot reach the server. Check that the backend is running and try again.", {
      code: "NETWORK_ERROR",
    });
  }

  if (response.status === 204) return null;

  const isJson = (response.headers.get("content-type") || "").includes("application/json");
  const body = isJson ? await response.json().catch(() => null) : null;

  if (!response.ok) {
    const error = body?.error || {};
    throw new ApiError(error.message || `Request failed with status ${response.status}.`, {
      status: response.status,
      code: error.code || "HTTP_ERROR",
      details: error.details || {},
    });
  }
  return body;
}

export const api = {
  health: () => request("/health"),
  model: () => request("/model"),

  uploadScan(file) {
    const form = new FormData();
    form.append("file", file, file.name);
    return request("/uploads", { method: "POST", body: form });
  },

  createPrediction(uploadId) {
    return request("/predictions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: uploadId }),
    });
  },

  listPredictions({ limit = 10, offset = 0 } = {}) {
    return request(`/predictions?limit=${limit}&offset=${offset}`);
  },

  deletePrediction(id) {
    return request(`/predictions/${encodeURIComponent(id)}`, { method: "DELETE" });
  },

  clearPredictions() {
    return request("/predictions", { method: "DELETE" });
  },

  thumbnailUrl(id) {
    return `${BASE_URL}/predictions/${encodeURIComponent(id)}/thumbnail`;
  },
};
