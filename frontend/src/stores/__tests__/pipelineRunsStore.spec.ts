import { beforeEach, describe, expect, it } from "vitest"
import { createPinia, setActivePinia } from "pinia"

import { usePipelineRunsStore, type SseEvent } from "@/stores/pipelineRunsStore"
import type { Job, PipelineRun } from "@/api/types"

function makeRun(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return { id: 1, project: 1, workflow: "full", status: "running", progress: 0, ...overrides } as PipelineRun
}

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: 10,
    stage: "render",
    queue: "gpu",
    status: "running",
    progress: 10,
    attempt: 1,
    message: "",
    ...overrides,
  } as Job
}

describe("pipelineRunsStore.applyEvent (named SSE events → state)", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it("hydrates run + jobs from pipeline.snapshot", () => {
    const store = usePipelineRunsStore()
    store.activeProjectId = 3
    store.applyEvent("pipeline.snapshot", {
      schema_version: "1.0",
      pipeline_run_id: "1",
      project_id: "3",
      workflow: "full",
      status: "running",
      progress: 45,
      jobs: [
        { id: "5", stage: "ingest", queue: "io", status: "succeeded", progress: 100, attempt: 0, message: "ok" },
        { id: "6", stage: "transcribe", queue: "gpu", status: "running", progress: 30, attempt: 1, message: "rodando" },
      ],
    } as SseEvent)
    expect(store.run?.id).toBe(1)
    expect(store.run?.progress).toBe(45)
    expect(store.jobs).toHaveLength(2)
    expect(store.jobs[0].status).toBe("succeeded")
    expect(store.jobs[1].progress).toBe(30)
  })

  it("updates job progress from job.progress event (not run level)", () => {
    const store = usePipelineRunsStore()
    store.run = makeRun()
    store.jobs = [makeJob()]
    store.applyEvent("job.progress", { job_id: "10", progress: 60 })
    expect(store.jobs[0].progress).toBe(60)
    expect(store.run?.progress).toBe(0)
  })

  it("updates run progress/status from pipeline.progress event", () => {
    const store = usePipelineRunsStore()
    store.run = makeRun()
    store.applyEvent("pipeline.progress", { pipeline_run_id: 1, status: "running", progress: 72 })
    expect(store.run?.progress).toBe(72)
    expect(store.run?.status).toBe("running")
  })

  it("updates a matching job by id (string job_id)", () => {
    const store = usePipelineRunsStore()
    store.run = makeRun()
    store.jobs = [makeJob()]
    store.applyEvent("job.progress", {
      job_id: "10",
      stage: "render",
      status: "succeeded",
      progress: 100,
      message: "done",
    })
    expect(store.jobs[0].status).toBe("succeeded")
    expect(store.jobs[0].progress).toBe(100)
    expect(store.jobs[0].message).toBe("done")
  })

  it("creates a job entry if unknown job id arrives (no crash)", () => {
    const store = usePipelineRunsStore()
    store.run = makeRun()
    store.applyEvent("job.started", { job_id: "99", stage: "cut", status: "running", progress: 1 })
    expect(store.jobs).toHaveLength(1)
    expect(store.jobs[0].id).toBe(99)
    expect(store.jobs[0].stage).toBe("cut")
  })

  it("stops polling when snapshot reports a terminal status", () => {
    const store = usePipelineRunsStore()
    store.applyEvent("pipeline.snapshot", {
      pipeline_run_id: 1,
      status: "partial",
      progress: 66,
      jobs: [],
    } as SseEvent)
    expect(store.polling).toBe(false)
  })

  it("ignores malformed event types without crashing", () => {
    const store = usePipelineRunsStore()
    store.run = makeRun()
    store.jobs = [makeJob()]
    expect(() => store.applyEvent("comment", {})).not.toThrow()
    expect(() => store.applyEvent("job.progress", { job_id: 999, progress: 50 })).not.toThrow()
  })
})