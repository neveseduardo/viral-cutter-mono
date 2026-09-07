import { defineStore } from "pinia"
import { ref } from "vue"

import { api } from "@/api"
import type { FrontendConfig, Health } from "@/api/types"

export const useConfigStore = defineStore("config", () => {
  const config = ref<FrontendConfig | null>(null)
  const health = ref<Health | null>(null)
  const loaded = ref(false)

  async function load() {
    try {
      config.value = (await api.getFrontendConfig()) as FrontendConfig
      health.value = await api.health().catch(() => null)
    } finally {
      loaded.value = true
    }
  }

  return { config, health, loaded, load }
})