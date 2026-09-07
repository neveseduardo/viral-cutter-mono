import { ApiException, type ApiError, type Health, type Project } from "./types"

const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1"
const STREAM_BASE = import.meta.env.VITE_STREAM_BASE ?? "/stream"

export function authHeaders(): Record<string, string> {
  if (import.meta.env.VITE_AUTH_DISABLED === "true") return {}
  const token = localStorage.getItem("vc:token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    credentials: "same-origin",
    ...init,
  })
  if (!res.ok) {
    let body: ApiError | string = `HTTP ${res.status}`
    try {
      body = (await res.json()) as ApiError
    } catch {
      body = await res.text()
    }
    throw new ApiException(res.status, body)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

// Listagens paginadas (AGENTS.md §11) retornam {count, next, previous, results[]};
// desembrulha para o array nas chamadas de lista do frontend.
export async function httpList<T>(path: string, init?: RequestInit): Promise<T[]> {
  const data = await http<{ results?: T[] } | T[]>(path, init)
  return Array.isArray(data) ? data : (data.results ?? [])
}

export const api = {
  health: () => http<Health>("/health"),

  listProjects: () => httpList<Project>("/projects"),
  createProject: (name: string) =>
    http<Project>("/projects", { method: "POST", body: JSON.stringify({ name }) }),
  getProject: (id: number | string) => http<Project>(`/projects/${id}`),
  deleteProject: (id: number | string) =>
    http<void>(`/projects/${id}`, { method: "DELETE" }),

  ingestProject: (id: number | string, payload: Record<string, unknown>) =>
    http<Project>(`/projects/${id}/ingest`, { method: "POST", body: JSON.stringify(payload) }),

  uploadVideo: (id: number | string, file: File) => {
    const form = new FormData()
    form.append("file", file)
    return fetch(`${BASE}/projects/${id}/ingest`, { method: "POST", body: form })
      .then(async (res) => {
        if (!res.ok) throw new ApiException(res.status, (await res.json()) as ApiError)
        return (await res.json()) as Project
      })
  },

  listAssets: (id: number | string) => httpList<unknown>(`/projects/${id}/assets`),
  assetDownloadUrl: (id: number | string, assetId: number | string) =>
    `${BASE}/projects/${id}/assets/${assetId}/download`,

  listProfiles: () => httpList<unknown>("/profiles"),

  createPipelineRun: (
    id: number | string,
    payload: {
      workflow: string
      profile?: number
      overrides?: Record<string, unknown>
    },
  ) => http<{ id: number }>(`/projects/${id}/pipeline-runs`, { method: "POST", body: JSON.stringify(payload) }),

  listPipelineRuns: (id: number | string) => httpList<unknown>(`/projects/${id}/pipeline-runs/history`),
  getPipelineRun: (id: number | string) => http<unknown>(`/pipeline-runs/${id}`),
  cancelPipelineRun: (id: number | string) =>
    http<void>(`/pipeline-runs/${id}/cancel`, { method: "POST" }),
  listJobs: (id: number | string) => httpList<unknown>(`/pipeline-runs/${id}/jobs`),
  cancelJob: (id: number | string) => http<void>(`/jobs/${id}/cancel`, { method: "POST" }),
  retryJob: (id: number | string) => http<void>(`/jobs/${id}/retry`, { method: "POST" }),

  getTranscript: (id: number | string) => http<unknown>(`/projects/${id}/transcript`),
  getSegments: (id: number | string) => http<unknown[]>(`/projects/${id}/segments`),
  getSubtitles: (id: number | string, idx: number | string) =>
    http<unknown>(`/projects/${id}/segments/${idx}/subtitles`),
  saveSubtitles: (id: number | string, idx: number | string, payload: unknown) =>
    http<unknown>(`/projects/${id}/segments/${idx}/subtitles`, { method: "PUT", body: JSON.stringify(payload) }),
  renderSegment: (id: number | string, idx: number | string) =>
    http<unknown>(`/projects/${id}/segments/${idx}/render`, { method: "POST" }),
  exportSegment: (id: number | string, idx: number | string, format: string) =>
    http<unknown>(`/projects/${id}/segments/${idx}/export`, { method: "POST", body: JSON.stringify({ format }) }),

  getFrontendConfig: () => http<unknown>("/config/frontend"),
  streamUrl: (runId: number | string) => `${STREAM_BASE}/pipeline-runs/${runId}`,
}