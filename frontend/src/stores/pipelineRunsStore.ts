import { defineStore } from "pinia"
import { ref } from "vue"

import { api } from "@/api"
import type { Job, PipelineRun } from "@/api/types"

export interface SseEvent {
  schema_version?: string
  pipeline_run_id?: number | string
  project_id?: number | string
  status?: string
  progress?: number
  workflow?: string
  stages?: Record<string, string>
  jobs?: Array<Record<string, unknown>>
  job_id?: number | string
  stage?: string
  queue?: string
  attempt?: number
  message?: string
  error?: string | null
  segment_index?: number | null
}

// Eventos nomeados do backend (AGENTS.md §8.6): EventSource só dispara o
// listener de "message" para frames SEM `event:` — como o backend sempre nomeia,
// precisamos registrar um listener por nome conhecido.
const KNOWN_EVENTS = [
  "pipeline.snapshot",
  "pipeline.started",
  "pipeline.progress",
  "pipeline.finished",
  "job.started",
  "job.progress",
  "job.finished",
  "comment",
] as const

const TERMINAL_STATUSES = ["succeeded", "failed", "cancelled", "partial"]

export const usePipelineRunsStore = defineStore("pipelineRuns", () => {
  const run = ref<PipelineRun | null>(null)
  const jobs = ref<Job[]>([])
  const connected = ref(false)
  const polling = ref(false)
  const activeProjectId = ref<number | null>(null)

  let es: EventSource | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let currentRunId: number | null = null

  function reset() {
    disconnect()
    run.value = null
    jobs.value = []
    activeProjectId.value = null
    currentRunId = null
  }

  function disconnect() {
    if (es) {
      es.close()
      es = null
    }
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    connected.value = false
    polling.value = false
  }

  function toNum(v: number | string | undefined): number | undefined {
    if (v === undefined || v === null) return undefined
    const n = Number(v)
    return Number.isFinite(n) ? n : undefined
  }

  function finish() {
    connected.value = false
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    polling.value = false
  }

  function applyRunEvent(evt: SseEvent) {
    if (evt.progress !== undefined && run.value) run.value.progress = evt.progress
    if (evt.status && run.value) run.value.status = evt.status as PipelineRun["status"]
    if (evt.status && run.value && TERMINAL_STATUSES.includes(evt.status)) finish()
  }

  function applyJobEvent(evt: SseEvent) {
    const jid = toNum(evt.job_id)
    if (jid === undefined) return
    let job = jobs.value.find((j) => j.id === jid)
    if (!job) {
      job = {
        id: jid,
        stage: (evt.stage ?? "") as Job["stage"],
        queue: (evt.queue ?? "") as Job["queue"],
        status: (evt.status ?? "pending") as Job["status"],
        progress: 0,
        attempt: evt.attempt ?? 0,
        message: evt.message ?? "",
      } as Job
      jobs.value.push(job)
    }
    if (evt.progress !== undefined) job.progress = evt.progress
    if (evt.status) job.status = evt.status as Job["status"]
    if (evt.message !== undefined) job.message = evt.message
    if (evt.stage) job.stage = evt.stage as Job["stage"]
  }

  function applySnapshot(evt: SseEvent) {
    const rid = toNum(evt.pipeline_run_id)
    if (!rid) return
    run.value = {
      id: rid,
      project: toNum(evt.project_id) ?? activeProjectId.value ?? 0,
      workflow: (evt.workflow ?? "full") as PipelineRun["workflow"],
      status: (evt.status ?? "running") as PipelineRun["status"],
      progress: evt.progress ?? 0,
    } as PipelineRun
    jobs.value = ((evt.jobs ?? []) as Array<Record<string, unknown>>).map<Job>((j) => ({
      id: toNum(j.id as number | string) ?? 0,
      pipeline_run: rid,
      stage: (j.stage as Job["stage"]) ?? "ingest",
      queue: (j.queue as Job["queue"]) ?? "cpu",
      status: ((j.status as string) ?? "pending") as Job["status"],
      progress: toNum(j.progress as number | string) ?? 0,
      attempt: toNum(j.attempt as number | string) ?? 0,
      message: (j.message as string) ?? "",
      error: null,
      logs: [],
      started_at: null,
      finished_at: null,
    }))
    if (evt.status && TERMINAL_STATUSES.includes(evt.status)) finish()
  }

  function applyEvent(type: string, evt: SseEvent = {}) {
    switch (type) {
      case "pipeline.snapshot":
        applySnapshot(evt)
        break
      case "job.progress":
      case "job.started":
      case "job.finished":
        applyJobEvent(evt)
        break
      case "pipeline.started":
      case "pipeline.progress":
      case "pipeline.finished":
      case "comment":
      default:
        applyRunEvent(evt)
        break
    }
  }

  async function poll() {
    if (currentRunId === null) return
    try {
      const r = (await api.getPipelineRun(currentRunId)) as PipelineRun
      const j = (await api.listJobs(currentRunId)) as Job[]
      run.value = r
      jobs.value = j
      if (r && TERMINAL_STATUSES.includes(r.status)) finish()
    } catch {
      // transient network errors: keep polling
    }
  }

  function start(runId: number, projectId?: number) {
    reset()
    currentRunId = runId
    activeProjectId.value = projectId ?? activeProjectId.value

    es = new EventSource(api.streamUrl(runId))
    for (const name of KNOWN_EVENTS) {
      es.addEventListener(name, (e) => {
        try {
          const data = JSON.parse((e as MessageEvent<string>).data) as SseEvent
          applyEvent(name, data)
        } catch {
          /* ignore malformed frames */
        }
      })
    }
    es.onopen = () => {
      connected.value = true
    }
    es.onerror = () => {
      // server closed: fall back to polling
      es?.close()
      es = null
      connected.value = false
      startPolling()
    }
    startPolling()
  }

  function startPolling() {
    if (pollTimer) return
    polling.value = true
    poll() // immediate refresh on reconnect (rewrites state, §8.6)
    pollTimer = setInterval(poll, 3000)
  }

  function stop() {
    disconnect()
  }

  async function refresh() {
    if (currentRunId !== null) await poll()
  }

  return {
    run, jobs, connected, polling, activeProjectId,
    start, stop, disconnect, reset, refresh, poll, applyEvent,
  }
})