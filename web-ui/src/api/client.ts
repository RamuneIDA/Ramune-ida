const BASE = "/api";

async function request<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") url.searchParams.set(k, v);
    }
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `HTTP ${res.status}`);
  }
  return res.json();
}

// Project management
export const getProjects = () =>
  request<{ projects: import("./types").ProjectSummary[] }>(`${BASE}/projects`);

export const getProject = (pid: string) =>
  request<import("./types").ProjectDetail>(`${BASE}/projects/${pid}`);

export const getProjectFiles = (pid: string) =>
  request<{ project_id: string; files: import("./types").ProjectFile[] }>(
    `${BASE}/projects/${pid}/files`,
  );

export const getSystem = () =>
  request<import("./types").SystemInfo>(`${BASE}/system`);

// Analysis
export const decompile = (pid: string, func: string) =>
  request<Record<string, unknown>>(`${BASE}/projects/${pid}/decompile`, { func });

export const disasm = (pid: string, addr: string, count?: string) =>
  request<Record<string, unknown>>(`${BASE}/projects/${pid}/disasm`, { addr, ...(count ? { count } : {}) });

export const xrefs = (pid: string, addr: string) =>
  request<Record<string, unknown>>(`${BASE}/projects/${pid}/xrefs`, { addr });

export const survey = (pid: string) =>
  request<Record<string, unknown>>(`${BASE}/projects/${pid}/survey`);

// Listings
export const listFuncs = (pid: string, filter?: string, exclude?: string) =>
  request<Record<string, unknown>>(`${BASE}/projects/${pid}/functions`, {
    ...(filter ? { filter } : {}),
    ...(exclude ? { exclude } : {}),
  });

export const listStrings = (pid: string, filter?: string, exclude?: string) =>
  request<Record<string, unknown>>(`${BASE}/projects/${pid}/strings`, {
    ...(filter ? { filter } : {}),
    ...(exclude ? { exclude } : {}),
  });

// Activity history
export const getActivity = (limit?: number, projectId?: string) =>
  request<{ events: import("./types").ActivityEvent[] }>(`${BASE}/activity`, {
    ...(limit ? { limit: String(limit) } : {}),
    ...(projectId ? { project_id: projectId } : {}),
  });
