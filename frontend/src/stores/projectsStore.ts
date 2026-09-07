import { defineStore } from "pinia"
import { computed, ref } from "vue"

import { api } from "@/api"
import type { Project, Segment, VideoAsset } from "@/api/types"

export const useProjectsStore = defineStore("projects", () => {
  const projects = ref<Project[]>([])
  const current = ref<Project | null>(null)
  const assets = ref<VideoAsset[]>([])
  const segments = ref<Segment[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const finalAssets = computed(() =>
    assets.value.filter((a) => a.kind === "final").sort((a, b) => (a.name ?? "").localeCompare(b.name ?? "")),
  )

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      projects.value = await api.listProjects()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  async function fetchOne(id: number | string) {
    loading.value = true
    error.value = null
    try {
      const [project, assetList, segList] = await Promise.all([
        api.getProject(id),
        api.listAssets(id).catch(() => []),
        api.getSegments(id).catch(() => []),
      ])
      current.value = project as Project
      assets.value = assetList as VideoAsset[]
      segments.value = segList as Segment[]
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  async function create(name: string) {
    const project = await api.createProject(name)
    await fetchAll()
    return project
  }

  async function remove(id: number | string) {
    await api.deleteProject(id)
    await fetchAll()
  }

  async function ingest(id: number | string, payload: Record<string, unknown>) {
    await api.ingestProject(id, payload)
    await fetchOne(id)
  }

  async function upload(id: number | string, file: File) {
    await api.uploadVideo(id, file)
    await fetchOne(id)
  }

  return {
    projects,
    current,
    assets,
    segments,
    finalAssets,
    loading,
    error,
    fetchAll,
    fetchOne,
    create,
    remove,
    ingest,
    upload,
  }
})