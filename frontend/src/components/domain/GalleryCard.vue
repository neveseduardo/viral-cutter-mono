<script setup lang="ts">
import { Download, ExternalLink, Film, MoreHorizontal } from "lucide-vue-next"
import { useI18n } from "vue-i18n"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { Project } from "@/api/types"
import { api } from "@/api"

const props = defineProps<{
  project: Project
  finalCount?: number
  partial?: string | null
}>()

const { t } = useI18n()

function statusLabel(s: string) {
  return t(`project.${s}` as never)
}

async function downloadFinal() {
  try {
    const assets = (await api.listAssets(props.project.id)) as { name: string; download_url?: string; kind: string }[]
    for (const a of assets.filter((x) => x.kind === "final")) {
      if (a.download_url) window.open(`${import.meta.env.VITE_API_BASE ?? "/api/v1"}${a.download_url}`, "_blank")
    }
  } catch (e) {
    console.warn("downloadFinal failed", e)
  }
}
</script>

<template>
  <Card class="flex flex-col overflow-hidden">
    <div class="flex aspect-video w-full items-center justify-center bg-muted">
      <img
        v-if="props.project.thumbnail"
        :src="props.project.thumbnail"
        :alt="props.project.name"
        class="h-full w-full object-cover"
      >
      <Film
        v-else
        class="h-10 w-10 text-muted-foreground"
      />
    </div>
    <CardHeader class="pb-2">
      <div class="flex items-start justify-between gap-2">
        <CardTitle class="truncate text-sm">
          {{ props.project.name }}
        </CardTitle>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Ações"
            >
              <MoreHorizontal class="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem as-child>
              <router-link :to="`/projects/${props.project.id}`">
                <ExternalLink class="mr-2 h-4 w-4" /> {{ t("library.open") }}
              </router-link>
            </DropdownMenuItem>
            <DropdownMenuItem as-child>
              <router-link :to="`/projects/${props.project.id}/editor`">
                <Film class="mr-2 h-4 w-4" /> {{ t("library.editSubtitles") }}
              </router-link>
            </DropdownMenuItem>
            <DropdownMenuItem
              v-if="finalCount"
              @click="downloadFinal()"
            >
              <Download class="mr-2 h-4 w-4" /> {{ t("library.downloadFinal") }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <CardDescription>
        <Badge
          variant="secondary"
          class="mr-2"
        >
          {{ statusLabel(props.project.status) }}
        </Badge>
        <span
          v-if="props.partial"
          class="text-xs text-amber-400"
        >{{ props.partial }}</span>
      </CardDescription>
    </CardHeader>
    <CardFooter class="mt-auto pt-2 text-xs text-muted-foreground">
      <span>{{ new Date(props.project.updated_at).toLocaleString() }}</span>
    </CardFooter>
  </Card>
</template>