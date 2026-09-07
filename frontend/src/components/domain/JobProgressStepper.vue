<script setup lang="ts">
import { Check, Loader2, XCircle, CircleDashed } from "lucide-vue-next"
import { useI18n } from "vue-i18n"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Job, PipelineRun } from "@/api/types"

const props = defineProps<{
  run: PipelineRun | null
  jobs: Job[]
}>()

const { t } = useI18n()

function statusIcon(job: Job) {
  switch (job.status) {
    case "succeeded":
      return Check
    case "running":
      return Loader2
    case "failed":
    case "cancelled":
      return XCircle
    default:
      return CircleDashed
  }
}

function statusClass(job: Job): string {
  switch (job.status) {
    case "succeeded":
      return "bg-emerald-500/15 text-emerald-400"
    case "running":
      return "bg-blue-500/15 text-blue-400 animate-pulse"
    case "failed":
      return "bg-red-500/15 text-red-400"
    case "cancelled":
      return "bg-yellow-500/15 text-yellow-400"
    default:
      return "bg-muted text-muted-foreground"
  }
}

function stageName(stage: string): string {
  return t(`jobs.stageNames.${stage}` as never) ?? stage
}
</script>

<template>
  <div class="space-y-4">
    <div>
      <div class="mb-2 flex items-center justify-between">
        <span class="text-sm font-medium">{{ t("jobs.title") }}</span>
        <span
          v-if="run"
          class="code text-xs text-muted-foreground"
        >{{ Math.round(run.progress) }}%</span>
      </div>
      <Progress
        v-if="run"
        :model-value="run.progress"
        class="h-2"
      />
    </div>

    <Table>
      <TableHeader>
        <TableRow>
          <TableHead class="w-40">
            {{ t("jobs.stage") }}
          </TableHead>
          <TableHead class="w-28">
            {{ t("jobs.status") }}
          </TableHead>
          <TableHead class="w-24">
            {{ t("jobs.progress") }}
          </TableHead>
          <TableHead>{{ t("jobs.message") }}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody v-if="jobs.length">
        <TableRow
          v-for="job in props.jobs"
          :key="job.id"
        >
          <TableCell class="font-medium">
            {{ stageName(job.stage) }}
          </TableCell>
          <TableCell>
            <Badge :class="statusClass(job)">
              <component
                :is="statusIcon(job)"
                class="mr-1 h-3 w-3"
                :class="{ 'animate-spin': job.status === 'running' }"
              />
              {{ t(`jobs.statuses.${job.status}` as never) }}
            </Badge>
          </TableCell>
          <TableCell class="code text-xs">
            {{ job.progress }}%
          </TableCell>
          <TableCell class="text-sm text-muted-foreground">
            {{ job.message }}
          </TableCell>
        </TableRow>
      </TableBody>
      <TableBody v-else>
        <TableRow>
          <TableCell
            :colspan="4"
            class="text-center text-sm text-muted-foreground"
          >
            {{ t("common.loading") }}
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
  </div>
</template>