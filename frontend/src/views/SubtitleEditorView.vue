<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { useProjectsStore } from "@/stores/projectsStore"
import { useSubtitleEditorStore } from "@/stores/subtitleEditorStore"
import { ArrowLeft, Save, Clapperboard } from "lucide-vue-next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { toast } from "vue-sonner"
import AppShell from "@/components/domain/AppShell.vue"
import { api } from "@/api"

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const projectsStore = useProjectsStore()
const editorStore = useSubtitleEditorStore()

const selectedSegment = ref<number>(0)
const segments = computed(() => projectsStore.segments ?? [])

onMounted(async () => {
  await projectsStore.fetchOne(props.id)
  const seg = segments.value.sort((a, b) => a.index - b.index)[0]
  if (seg) {
    selectedSegment.value = seg.index
    await loadTrack()
  }
})

async function loadTrack() {
  try {
    await editorStore.load(props.id, selectedSegment.value)
  } catch (e) {
    toast.error((e as Error).message)
  }
}

watch(selectedSegment, () => loadTrack())

async function save() {
  try {
    await editorStore.save()
    toast.success(t("common.save"))
  } catch (e) {
    toast.error((e as Error).message)
  }
}

async function render() {
  try {
    await api.renderSegment(props.id, selectedSegment.value)
    toast.success(t("editor.render"))
  } catch (e) {
    toast.error((e as Error).message)
  }
}
</script>

<template>
  <AppShell>
    <div class="mx-auto max-w-6xl p-6">
      <header class="mb-6">
        <Button
          variant="ghost"
          size="sm"
          as-child
          class="mb-3"
        >
          <router-link :to="`/projects/${props.id}`">
            <ArrowLeft class="mr-1 h-4 w-4" />{{ t("common.back") }}
          </router-link>
        </Button>
        <h1 class="font-display text-3xl font-bold">
          {{ t("editor.title") }}
        </h1>
      </header>

      <div class="grid gap-6 lg:grid-cols-4">
        <Card class="lg:col-span-1">
          <CardHeader>
            <CardTitle class="text-base">
              {{ t("segments.title") }}
            </CardTitle>
          </CardHeader>
          <CardContent class="space-y-2">
            <button
              v-for="s in segments"
              :key="s.index"
              class="w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-muted"
              :class="s.index === selectedSegment ? 'border-primary bg-primary/5' : ''"
              @click="selectedSegment = s.index"
            >
              <span class="font-medium">{{ s.title }}</span>
              <span class="block code text-xs text-muted-foreground">
                {{ s.start_time?.toFixed(1) }} → {{ s.end_time?.toFixed(1) }}s
              </span>
            </button>
          </CardContent>
        </Card>

        <div class="lg:col-span-3 space-y-6">
          <Card>
            <CardHeader>
              <div class="flex items-center justify-between">
                <CardTitle class="text-base">
                  {{ t("editor.segment") }} {{ selectedSegment }}
                </CardTitle>
                <div class="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    @click="render"
                  >
                    <Clapperboard class="mr-1 h-4 w-4" />{{ t("editor.render") }}
                  </Button>
                  <Button
                    size="sm"
                    :disabled="!editorStore.dirty"
                    @click="save"
                  >
                    <Save class="mr-1 h-4 w-4" />{{ t("common.save") }}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div
                v-if="editorStore.track"
                class="space-y-3"
              >
                <div
                  v-for="(seg, si) in editorStore.track.segments"
                  :key="si"
                  class="rounded-md border p-3"
                >
                  <div class="mb-2 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <Label>{{ t("editor.start") }}</Label><Input
                        :model-value="seg.start.toFixed(2)"
                        readonly
                        class="code"
                      />
                    </div>
                    <div>
                      <Label>{{ t("editor.end") }}</Label><Input
                        :model-value="seg.end.toFixed(2)"
                        readonly
                        class="code"
                      />
                    </div>
                    <div class="">
                      <Label>{{ t("editor.text") }}</Label>
                    </div>
                  </div>
                  <div class="space-y-1">
                    <div
                      v-for="(w, wi) in seg.words"
                      :key="wi"
                      class="flex items-center gap-2"
                    >
                      <span class="code w-24 shrink-0 text-xs text-muted-foreground">{{ w.start.toFixed(2) }}s</span>
                      <Input
                        :model-value="w.word"
                        class="h-8"
                        @update:model-value="editorStore.updateWord(si, wi, { word: String($event) })"
                      />
                      <span class="code w-24 shrink-0 text-xs text-muted-foreground">{{ w.end.toFixed(2) }}s</span>
                    </div>
                  </div>
                </div>
              </div>
              <p
                v-else
                class="text-sm text-muted-foreground"
              >
                {{ t("common.loading") }}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
      <Separator class="my-6" />
      <p class="text-xs text-muted-foreground">
        JSON canônico — fonte da verdade (§8.3)
      </p>
    </div>
  </AppShell>
</template>