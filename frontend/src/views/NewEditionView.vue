<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { useConfigStore } from "@/stores/configStore"
import { useProjectsStore } from "@/stores/projectsStore"
import { usePipelineRunsStore } from "@/stores/pipelineRunsStore"
import { api } from "@/api"
import type { FrontendConfig, ProcessingProfile } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Checkbox } from "@/components/ui/checkbox"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Separator } from "@/components/ui/separator"
import AppShell from "@/components/domain/AppShell.vue"
import VideoUploader from "@/components/domain/VideoUploader.vue"
import JobProgressStepper from "@/components/domain/JobProgressStepper.vue"

const { t } = useI18n()
const configStore = useConfigStore()
const projectsStore = useProjectsStore()
const runsStore = usePipelineRunsStore()

const config = ref<FrontendConfig | null>(null)
const localProjectId = ref<number | null>(null)
const projectName = ref("")
const sourceType = ref<"youtube" | "upload" | "reuse">("youtube")
const youtubeUrl = ref("")
const reuseId = ref<number | null>(null)
const selectedFile = ref<File | null>(null)

const workflow = ref<"full" | "cut_only" | "subtitles_only">("full")
const segments = ref(3)
const minDuration = ref(20)
const maxDuration = ref(60)
const whisperModel = ref("large-v3-turbo")
const aiProvider = ref("gemini")
const faceMode = ref("auto")
const noFaceMode = ref("zoom")
const subtitlePreset = ref("hormozi-classic")
const translateTo = ref("")
const useYouTubeSubs = ref(false)
const selectedProfileId = ref<number | null>(null)

const submitting = ref(false)
const startedRunId = ref<number | null>(null)
const activeProjectId = ref<number | null>(null)

const profiles = ref<ProcessingProfile[]>([])
const providersList = ref<{ name: string; label: string }[]>([])

onMounted(async () => {
  await configStore.load()
  config.value = configStore.config
  profiles.value = (config.value?.profiles as ProcessingProfile[]) ?? []
  providersList.value = (config.value?.providers as string[] ?? []).map((name) => ({
    name,
    label: name,
  }))
  await projectsStore.fetchAll()
})

watch(selectedProfileId, (id) => {
  if (!id) return
  const p = profiles.value.find((x) => x.id === id)
  if (!p) return
  segments.value = p.segments
  minDuration.value = p.min_duration
  maxDuration.value = p.max_duration
  whisperModel.value = p.whisper_model
  faceMode.value = p.face_mode
  subtitlePreset.value = p.subtitle_preset
})

async function ensureProject(): Promise<number> {
  if (localProjectId.value) return localProjectId.value
  if (sourceType.value === "reuse" && reuseId.value) {
    localProjectId.value = reuseId.value
    return reuseId.value
  }
  const p = await projectsStore.create(projectName.value || `Projeto ${new Date().toLocaleString()}`)
  localProjectId.value = p.id
  return p.id
}

async function submit() {
  submitting.value = true
  try {
    const id = await ensureProject()
    const overrides: Record<string, unknown> = {
      segments: segments.value,
      min_duration: minDuration.value,
      max_duration: maxDuration.value,
      whisper_model: whisperModel.value,
      ai_provider: aiProvider.value,
      face_mode: faceMode.value,
      no_face_mode: noFaceMode.value,
      subtitle_preset: subtitlePreset.value,
    }
    if (sourceType.value === "youtube") {
      overrides.url = youtubeUrl.value
      overrides.use_youtube_subs = useYouTubeSubs.value
      overrides.video_quality = "best"
    } else if (sourceType.value === "upload" && selectedFile.value) {
      await api.uploadVideo(id, selectedFile.value)
    }
    if (translateTo.value) overrides.translate_to = translateTo.value
    const res = await api.createPipelineRun(id, { workflow: workflow.value, overrides })
    startedRunId.value = res.id
    activeProjectId.value = id
    runsStore.start(res.id, id)
  } catch (e) {
    console.error("falha ao iniciar", e)
  } finally {
    submitting.value = false
  }
}

function onUploaded(pid: number) {
  localProjectId.value = pid
  selectedFile.value = null
}
</script>

<template>
  <AppShell>
    <div class="mx-auto max-w-6xl p-6">
      <header class="mb-8 flex items-center justify-between">
        <div>
          <h1 class="font-display text-3xl font-bold">
            {{ t("wizard.title") }}
          </h1>
          <p class="mt-1 text-muted-foreground">
            {{ t("wizard.subtitle") }}
          </p>
        </div>
        <Button
          variant="outline"
          class="md:hidden"
          as-child
        >
          <router-link to="/library">
            {{ t("nav.library") }}
          </router-link>
        </Button>
      </header>

      <div class="grid gap-8 lg:grid-cols-2">
        <div class="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle class="text-base">
                {{ t("wizard.source") }}
              </CardTitle>
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="space-y-1.5">
                <Label>{{ t("project.name") }}</Label>
                <Input
                  v-model="projectName"
                  :placeholder="`Projeto ${new Date().toLocaleString()}`"
                />
              </div>
              <Tabs
                v-model="sourceType"
                class="w-full"
              >
                <TabsList class="grid w-full grid-cols-3">
                  <TabsTrigger value="youtube">
                    YouTube
                  </TabsTrigger>
                  <TabsTrigger value="upload">
                    {{ t("wizard.uploadFile") }}
                  </TabsTrigger>
                  <TabsTrigger value="reuse">
                    {{ t("wizard.reuseProject") }}
                  </TabsTrigger>
                </TabsList>
                <div class="mt-4 space-y-3">
                  <TabsContent
                    value="youtube"
                    class="space-y-3"
                  >
                    <div class="space-y-1.5">
                      <Label>{{ t("wizard.youtubeUrl") }}</Label>
                      <Input
                        v-model="youtubeUrl"
                        type="url"
                        placeholder="https://www.youtube.com/watch?v=..."
                      />
                    </div>
                    <label class="flex items-center gap-2 text-sm">
                      <Checkbox v-model:checked="useYouTubeSubs" />
                      <span class="text-xs text-muted-foreground">usar legendas oficiais do YouTube</span>
                    </label>
                  </TabsContent>
                  <TabsContent value="upload">
                    <VideoUploader
                      :project-id="localProjectId"
                      @uploaded="onUploaded"
                    />
                  </TabsContent>
                  <TabsContent
                    value="reuse"
                    class="space-y-1.5"
                  >
                    <Label>{{ t("wizard.reuseProject") }}</Label>
                    <Select v-model="reuseId">
                      <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                      <SelectContent>
                        <SelectItem
                          v-for="p in projectsStore.projects"
                          :key="p.id"
                          :value="String(p.id)"
                        >
                          {{ p.name }}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </TabsContent>
                </div>
              </Tabs>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle class="text-base">
                {{ t("wizard.profile") }}
              </CardTitle>
              <CardDescription>
                <Select
                  v-if="profiles.length"
                  v-model="selectedProfileId"
                >
                  <SelectTrigger class="w-full">
                    <SelectValue placeholder="Perfis salvos..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem
                      v-for="p in profiles"
                      :key="p.id"
                      :value="String(p.id)"
                    >
                      {{ p.name }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </CardDescription>
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="grid grid-cols-2 gap-3">
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.segments") }}</Label>
                  <Input
                    v-model.number="segments"
                    type="number"
                    min="1"
                    max="10"
                  />
                </div>
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.whisperModel") }}</Label>
                  <Select v-model="whisperModel">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem
                        v-for="m in (config?.whisper_models ?? ['tiny','base','small','medium','large-v3-turbo'])"
                        :key="m"
                        :value="m"
                      >
                        {{ m }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.minDuration") }}</Label>
                  <Input
                    v-model.number="minDuration"
                    type="number"
                    min="1"
                  />
                </div>
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.maxDuration") }}</Label>
                  <Input
                    v-model.number="maxDuration"
                    type="number"
                    min="1"
                  />
                </div>
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.aiProvider") }}</Label>
                  <Select v-model="aiProvider">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem
                        v-for="p in providersList"
                        :key="p.name"
                        :value="p.name"
                      >
                        {{ p.label }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.subtitlePreset") }}</Label>
                  <Select v-model="subtitlePreset">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem
                        v-for="pr in (config?.subtitle_presets ?? ['hormozi-classic'])"
                        :key="pr"
                        :value="pr"
                      >
                        {{ pr }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.faceMode") }}</Label>
                  <Select v-model="faceMode">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">
                        {{ t("wizard.autoFace") }}
                      </SelectItem>
                      <SelectItem value="center">
                        {{ t("wizard.centerCrop") }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.noFaceMode") }}</Label>
                  <Select v-model="noFaceMode">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="zoom">
                        Zoom
                      </SelectItem>
                      <SelectItem value="padding">
                        Barras
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Separator />
              <div class="grid grid-cols-2 gap-3">
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.workflow") }}</Label>
                  <Select v-model="workflow">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="full">
                        {{ t("wizard.fullFlow") }}
                      </SelectItem>
                      <SelectItem value="cut_only">
                        {{ t("wizard.cutOnly") }}
                      </SelectItem>
                      <SelectItem value="subtitles_only">
                        {{ t("wizard.subtitlesOnly") }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-1.5">
                  <Label>{{ t("wizard.translateTo") }}</Label>
                  <Input
                    v-model="translateTo"
                    placeholder="ex.: en, es, zh-CN"
                  />
                </div>
              </div>

              <Button
                class="w-full"
                :disabled="submitting"
                @click="submit"
              >
                {{ submitting ? t("wizard.processing") : t("wizard.submit") }}
              </Button>
            </CardContent>
          </Card>
        </div>

        <div>
          <Card>
            <CardHeader>
              <CardTitle class="text-base">
                {{ t("jobs.title") }}
              </CardTitle>
              <CardDescription v-if="startedRunId">
                Run #{{ startedRunId }}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <JobProgressStepper
                v-if="runsStore.run"
                :run="runsStore.run"
                :jobs="runsStore.jobs"
              />
              <p
                v-else
                class="text-sm text-muted-foreground"
              >
                {{ t("wizard.subtitle") }}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  </AppShell>
</template>