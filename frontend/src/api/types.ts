export interface Health {
  status: string
  db: string
  redis: string
}

export interface Project {
  id: number
  name: string
  status: "empty" | "ingested" | "transcribed" | "analyzed" | "ready" | "error"
  created_at: string
  updated_at: string
  thumbnail?: string | null
  input_asset?: number | null
}

export type JobStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled" | "skipped"
export type JobStage =
  | "ingest"
  | "transcribe"
  | "analyze"
  | "align"
  | "cut"
  | "edit"
  | "subtitles"
  | "translate"
  | "render"

export interface Job {
  id: number
  pipeline_run: number
  stage: JobStage
  queue: "io" | "cpu" | "gpu"
  status: JobStatus
  progress: number
  attempt: number
  message: string
  error: string | null
  logs: unknown[]
  started_at: string | null
  finished_at: string | null
}

export type PipelineRunStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "partial"

export interface PipelineRun {
  id: number
  project: number
  workflow: "full" | "cut_only" | "subtitles_only"
  status: PipelineRunStatus
  progress: number
  configuration_snapshot: Record<string, unknown>
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export type AssetKind =
  | "source"
  | "downloaded"
  | "normalized"
  | "cut"
  | "edited"
  | "final"
  | "preview"
  | "thumbnail"

export interface VideoAsset {
  id: number
  project: number
  parent_asset: number | null
  kind: AssetKind
  storage_key: string
  mime_type: string
  size: number
  duration: number | null
  width: number | null
  height: number | null
  fps: number | null
  codec: string | null
  checksum: string | null
  created_at: string
  url: string
  download_url: string
  name: string
  segment_index: number | null
}

export interface Segment {
  index: number
  title: string
  reasoning: string | null
  hook: string | null
  score: number
  scores: Record<string, number>
  start_time: number | null
  end_time: number | null
  duration: number | null
  status: "queued" | "cut" | "edited" | "rendered" | "failed"
  rejected?: boolean
  rejection_reason?: string | null
}

export interface TranscriptSegment {
  id: number
  start: number
  end: number
  text: string
  words: { word: string; start: number; end: number; score: number }[]
}

export interface Transcript {
  schema_version: string
  language: string
  source: string
  model: string
  segments: TranscriptSegment[]
}

export interface ProcessingProfile {
  id?: number
  name: string
  segments: number
  min_duration: number
  max_duration: number
  whisper_model: string
  face_mode: string
  subtitle_preset: string
}

export interface SubtitleConfig {
  font_family: string
  font_size: number
  base_color: string
  highlight_color: string
  outline_color: string
  mode: "highlight" | "word_by_word" | "no_highlight"
  position: string
  uppercase: boolean
  remove_punctuation: boolean
}

export interface SubtitleTrack {
  schema_version: string
  language: string
  derived: string[]
  segments: {
    start: number
    end: number
    text: string
    words: { word: string; start: number; end: number; score: number }[]
  }[]
}

export interface FrontendConfig {
  whisper_models: string[]
  providers: string[]
  subtitle_presets: string[]
  profiles: ProcessingProfile[]
  limits: Record<string, number>
}

export interface ApiError {
  error?: string
  code?: string
  detail?: string
}

export class ApiException extends Error {
  constructor(
    public status: number,
    public body: ApiError | string,
  ) {
    super(typeof body === "string" ? body : body?.error ?? body?.detail ?? `HTTP ${status}`)
    this.name = "ApiException"
  }
}