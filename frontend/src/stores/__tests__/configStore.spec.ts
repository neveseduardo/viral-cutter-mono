import { beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"

vi.mock("@/api", () => ({
  api: {
    getFrontendConfig: vi.fn(),
    health: vi.fn(),
  },
}))

import { api } from "@/api"
import { useConfigStore } from "@/stores/configStore"
import type { FrontendConfig } from "@/api/types"

const FAKE_CONFIG = {
  whisper_models: ["tiny", "base"],
  providers: ["auto", "gemini"],
  subtitle_presets: ["hormozi-classic", "mrbeast-clean"],
  profiles: [],
  limits: { max_upload_mb: 4096 },
} as unknown as FrontendConfig

describe("configStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it("is unloaded initially", () => {
    const store = useConfigStore()
    expect(store.loaded).toBe(false)
    expect(store.config).toBeNull()
  })

  it("loads config and marks loaded even if health fails", async () => {
    vi.mocked(api.getFrontendConfig).mockResolvedValue(FAKE_CONFIG as never)
    vi.mocked(api.health).mockRejectedValue(new Error("down") as never)

    const store = useConfigStore()
    await store.load()

    expect(store.loaded).toBe(true)
    expect(store.config?.subtitle_presets).toContain("hormozi-classic")
    expect(store.health).toBeNull()
  })
})
