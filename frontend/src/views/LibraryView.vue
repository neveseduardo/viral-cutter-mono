<script setup lang="ts">
import { onMounted } from "vue"
import { useI18n } from "vue-i18n"
import { useProjectsStore } from "@/stores/projectsStore"
import { useConfigStore } from "@/stores/configStore"
import { Button } from "@/components/ui/button"
import AppShell from "@/components/domain/AppShell.vue"
import GalleryCard from "@/components/domain/GalleryCard.vue"
import { api } from "@/api"
import type { PipelineRun, Project } from "@/api/types"

const { t } = useI18n()
const projectsStore = useProjectsStore()
const configStore = useConfigStore()

const runCounts = new Map<number, { total: number; done: number }>()

onMounted(async () => {
  await Promise.all([projectsStore.fetchAll(), configStore.load()])
  for (const p of projectsStore.projects) {
    const runs = (await api.listPipelineRuns(p.id).catch(() => [])) as PipelineRun[]
    const latest = runs.sort((a, b) => b.id - a.id)[0]
    if (!latest) continue
    const jobs = (await api.listJobs(latest.id).catch(() => [])) as { status: string }[]
    runCounts.set(p.id, {
      total: jobs.length,
      done: jobs.filter((j) => ["succeeded", "failed", "cancelled", "skipped"].includes(j.status)).length,
    })
  }
})

function partialLabel(p: Project): string | null {
  const c = runCounts.get(p.id)
  return c && c.done < c.total ? t("library.partialReady").replace("y", String(c.done)).replace("x", String(c.total)) : null
}
</script>

<template>
  <AppShell>
    <div class="mx-auto max-w-6xl p-6">
      <header class="mb-6 flex items-center justify-between">
        <h1 class="font-display text-3xl font-bold">
          {{ t("library.title") }}
        </h1>
        <Button as-child>
          <router-link to="/">
            {{ t("wizard.title") }}
          </router-link>
        </Button>
      </header>

      <div
        v-if="projectsStore.projects.length"
        class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        <GalleryCard
          v-for="p in projectsStore.projects"
          :key="p.id"
          :project="p"
          :partial="partialLabel(p)"
        />
      </div>

      <div
        v-else
        class="rounded-lg border border-dashed p-16 text-center"
      >
        <p class="text-lg font-medium text-muted-foreground">
          {{ t("library.empty") }}
        </p>
        <p class="mt-1 text-sm text-muted-foreground">
          {{ t("library.createFirst") }}
        </p>
      </div>
    </div>
  </AppShell>
</template>