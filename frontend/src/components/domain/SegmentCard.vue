<script setup lang="ts">
import { Sparkles } from "lucide-vue-next"
import { useI18n } from "vue-i18n"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import type { Segment } from "@/api/types"

const props = defineProps<{
  segment: Segment
}>()

const { t } = useI18n()
</script>

<template>
  <Card class="overflow-hidden">
    <CardHeader class="pb-3">
      <div class="flex items-start justify-between gap-2">
        <CardTitle class="text-base">
          {{ props.segment.title }}
        </CardTitle>
        <Badge
          variant="secondary"
          class="shrink-0"
        >
          {{ t(`segments.statuses.${props.segment.status}` as never) }}
        </Badge>
      </div>
      <CardDescription>
        <template v-if="props.segment.score">
          <span class="flex items-center gap-1">
            <Sparkles class="h-3 w-3" /> {{ t("segments.score") }}: {{ props.segment.score }}/100
          </span>
        </template>
        <span
          v-if="props.segment.duration"
          class="code"
        >
          {{ t("segments.duration") }}: {{ props.segment.duration.toFixed(1) }}s
        </span>
      </CardDescription>
    </CardHeader>
    <CardContent class="space-y-2 pb-3 text-sm">
      <div
        v-if="props.segment.hook"
        class="rounded-md bg-muted p-2 italic"
      >
        “{{ props.segment.hook }}”
      </div>
      <p
        v-if="props.segment.reasoning"
        class="text-muted-foreground"
      >
        {{ props.segment.reasoning }}
      </p>
      <p
        v-if="props.segment.start_time !== null && props.segment.end_time !== null"
        class="code text-xs text-muted-foreground"
      >
        {{ props.segment.start_time.toFixed(1) }}s → {{ props.segment.end_time.toFixed(1) }}s
      </p>
    </CardContent>
    <CardFooter
      v-if="props.segment.score"
      class="pb-3"
    >
      <Progress
        :model-value="props.segment.score"
        class="h-1.5"
      />
    </CardFooter>
  </Card>
</template>