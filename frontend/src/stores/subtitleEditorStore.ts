import { defineStore } from "pinia"
import { ref } from "vue"

import { api } from "@/api"
import type { SubtitleTrack } from "@/api/types"

export const useSubtitleEditorStore = defineStore("subtitleEditor", () => {
  const projectId = ref<number | string | null>(null)
  const segmentIndex = ref<number | null>(null)
  const track = ref<SubtitleTrack | null>(null)
  const dirty = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  async function load(pid: number | string, idx: number) {
    projectId.value = pid
    segmentIndex.value = idx
    track.value = (await api.getSubtitles(pid, idx)) as SubtitleTrack
    dirty.value = false
  }

  function updateWord(segIdx: number, wordIdx: number, patch: { word?: string; start?: number; end?: number }) {
    if (!track.value) return
    const seg = track.value.segments[segIdx]
    const w = seg?.words[wordIdx]
    if (!seg || !w) return
    Object.assign(w, patch)
    // recompute segment boundaries from words
    if (seg.words.length) {
      seg.start = Math.min(...seg.words.map((x) => x.start))
      seg.end = Math.max(...seg.words.map((x) => x.end))
    }
    seg.text = seg.words.map((x) => x.word).join(" ")
    dirty.value = true
  }

  async function save() {
    if (!projectId.value || segmentIndex.value === null || !track.value) return
    saving.value = true
    error.value = null
    try {
      await api.saveSubtitles(projectId.value, segmentIndex.value, track.value)
      dirty.value = false
    } catch (e) {
      error.value = (e as Error).message
      throw e
    } finally {
      saving.value = false
    }
  }

  return { projectId, segmentIndex, track, dirty, saving, error, load, updateWord, save }
})