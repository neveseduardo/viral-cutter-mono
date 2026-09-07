<script setup lang="ts">
import { UploadCloud } from "lucide-vue-next"
import { ref } from "vue"
import { useI18n } from "vue-i18n"
import { useProjectsStore } from "@/stores/projectsStore"

const props = defineProps<{
  projectId?: number | string | null
}>()

const emit = defineEmits<{ uploaded: [projectId: number] }>()

const { t } = useI18n()
const store = useProjectsStore()
const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const error = ref<string | null>(null)

async function handleFile(file: File | undefined | null) {
  if (!file) return
  uploading.value = true
  error.value = null
  try {
    let pid: number | string = props.projectId as number | string
    if (!pid) {
      const created = await store.create(`Projeto ${new Date().toLocaleString()}`)
      pid = created.id
    }
    await store.upload(pid, file)
    emit("uploaded", Number(pid))
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    uploading.value = false
  }
}

function onChange(e: Event) {
  void handleFile((e.target as HTMLInputElement).files?.[0])
}

function handleDrop(e: DragEvent) {
  dragging.value = false
  void handleFile(e.dataTransfer?.files?.[0])
}
</script>

<template>
  <div
    class="cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors hover:border-primary"
    :class="dragging ? 'border-primary bg-primary/5' : 'border-border'"
    @click="fileInput?.click()"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="handleDrop"
  >
    <UploadCloud class="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
    <p class="text-sm font-medium">
      {{ t("wizard.uploadFile") }}
    </p>
    <p class="text-xs text-muted-foreground">
      MP4, MOV, WEBM — clique ou arraste
    </p>
    <input
      ref="fileInput"
      type="file"
      accept="video/*"
      class="hidden"
      @change="onChange"
    >
    <p
      v-if="uploading"
      class="mt-2 text-xs text-blue-400"
    >
      {{ t("common.loading") }}
    </p>
    <p
      v-if="error"
      class="mt-2 text-xs text-red-400"
    >
      {{ error }}
    </p>
  </div>
</template>