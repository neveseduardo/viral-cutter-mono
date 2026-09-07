<script setup lang="ts">
import { Download, Pencil, Clapperboard, ArrowLeft, Loader2 } from "lucide-vue-next"
import { onMounted, ref } from "vue"
import { useI18n } from "vue-i18n"
import { useProjectsStore } from "@/stores/projectsStore"
import { usePipelineRunsStore } from "@/stores/pipelineRunsStore"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import AppShell from "@/components/domain/AppShell.vue"
import SegmentCard from "@/components/domain/SegmentCard.vue"
import JobProgressStepper from "@/components/domain/JobProgressStepper.vue"
import { api } from "@/api"
import type { PipelineRun, VideoAsset } from "@/api/types"

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const store = useProjectsStore()
const runsStore = usePipelineRunsStore()

const runs = ref<PipelineRun[]>([])
const canceled = ref<number | null>(null)

onMounted(async () => {
  await store.fetchOne(props.id)
  runs.value = (await api.listPipelineRuns(props.id).catch(() => [])) as PipelineRun[]
  const latest = [...runs.value].sort((a, b) => b.id - a.id)[0]
  if (latest) runsStore.start(latest.id, latest.project)
})

function downloadUrl(a: VideoAsset) {
  return `${import.meta.env.VITE_API_BASE ?? "/api/v1"}/projects/${props.id}/assets/${a.id}/download`
}

async function reprocess(runId: number, workflow?: string, overrides?: Record<string, unknown>) {
  const res = await api.createPipelineRun(props.id, {
    workflow: workflow ?? "full",
    overrides: overrides ?? {},
  })
  runsStore.start(res.id, Number(props.id))
}

async function cancelRun(runId: number) {
  canceled.value = runId
  try {
    await api.cancelPipelineRun(runId)
  } finally {
    canceled.value = null
  }
}
</script>

<template>
  <AppShell>
    <div class="mx-auto max-w-6xl p-6">
      <header class="mb-8">
        <Button
          variant="ghost"
          size="sm"
          as-child
          class="mb-3"
        >
          <router-link to="/library">
            <ArrowLeft class="mr-1 h-4 w-4" />{{ t("common.back") }}
          </router-link>
        </Button>
        <div class="flex items-start justify-between gap-4">
          <div>
            <h1 class="font-display text-3xl font-bold">
              {{ store.current?.name }}
            </h1>
            <div class="mt-2 flex items-center gap-3">
              <Badge variant="secondary">
                {{ store.current?.status }}
              </Badge>
              <Badge
                v-if="runsStore.run"
                :variant="runsStore.run.status === 'succeeded' ? 'default' : 'secondary'"
                class="code"
              >
                #{{ runsStore.run.id }} {{ runsStore.run.status }}
              </Badge>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              :disabled="!runsStore.run"
              @click="runsStore.run && cancelRun(runsStore.run.id)"
            >
              <Loader2
                v-if="canceled === runsStore.run?.id"
                class="mr-1 h-4 w-4 animate-spin"
              />
              {{ t("common.cancel") }}
            </Button>
            <Button
              size="sm"
              @click="reprocess(runsStore.run?.id ?? 0)"
            >
              {{ t("library.reprocess") }}
            </Button>
          </div>
        </div>
        <Separator class="mt-6" />
      </header>

      <div class="grid gap-8 lg:grid-cols-5">
        <div class="lg:col-span-3 space-y-6">
          <Card v-if="runsStore.run">
            <CardHeader>
              <CardTitle class="text-base">
                {{ t("jobs.title") }}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <JobProgressStepper
                :run="runsStore.run"
                :jobs="runsStore.jobs"
              />
            </CardContent>
          </Card>

          <section>
            <h2 class="mb-3 text-lg font-semibold">
              {{ t("segments.title") }}
            </h2>
            <div
              v-if="store.segments.length"
              class="grid gap-4 sm:grid-cols-2"
            >
              <SegmentCard
                v-for="s in store.segments"
                :key="s.index"
                :segment="s"
              />
            </div>
            <p
              v-else
              class="text-sm text-muted-foreground"
            >
              {{ t("segments.title") }}
            </p>
          </section>
        </div>

        <div class="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle class="text-base">
                Vídeos finais
              </CardTitle>
            </CardHeader>
            <CardContent class="space-y-3">
              <article
                v-for="a in store.finalAssets"
                :key="a.id"
                class="flex items-center justify-between gap-3 rounded-lg border p-3"
              >
                <div class="flex items-center gap-3">
                  <Clapperboard class="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p class="text-sm font-medium">
                      {{ a.name }}
                    </p>
                    <p class="code text-xs text-muted-foreground">
                      {{ a.width }}×{{ a.height }} · {{ a.duration?.toFixed(1) }}s
                    </p>
                  </div>
                </div>
                <a
                  :href="downloadUrl(a)"
                  download
                >
                  <Button
                    size="sm"
                    variant="outline"
                  ><Download class="mr-1 h-4 w-4" />{{ t("common.download") }}</Button>
                </a>
              </article>
              <p
                v-if="!store.finalAssets.length"
                class="text-sm text-muted-foreground"
              >
                {{ t("library.thumbnailMissing") }}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader class="flex-row items-center justify-between space-y-0">
              <CardTitle class="text-base">
                {{ t("library.editSubtitles") }}
              </CardTitle>
              <Button
                size="sm"
                variant="secondary"
                as-child
              >
                <router-link :to="`/projects/${props.id}/editor`">
                  <Pencil class="mr-1 h-4 w-4" />{{ t("common.edit") }}
                </router-link>
              </Button>
            </CardHeader>
          </Card>
        </div>
      </div>
    </div>
  </AppShell>
</template>