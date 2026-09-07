<script setup lang="ts">
import { Play, Library, Settings, AudioLines } from "lucide-vue-next"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { useI18n } from "vue-i18n"
import { LOCALES } from "@/locales"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const { t, locale } = useI18n()
</script>

<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <aside class="hidden md:flex w-56 flex-col gap-2 border-r bg-card p-4">
      <div class="mb-6 flex items-center gap-2 px-2">
        <div class="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <AudioLines class="h-5 w-5" />
        </div>
        <span class="font-display text-lg font-bold">ViralCutter</span>
      </div>
      <Button
        as-child
        variant="ghost"
        class="justify-start"
      >
        <router-link to="/">
          <Play class="mr-2 h-4 w-4" />
          {{ t("nav.newEdition") }}
        </router-link>
      </Button>
      <Button
        as-child
        variant="ghost"
        class="justify-start"
      >
        <router-link to="/library">
          <Library class="mr-2 h-4 w-4" />
          {{ t("nav.library") }}
        </router-link>
      </Button>
      <Button
        as-child
        variant="ghost"
        class="justify-start"
      >
        <router-link to="/settings">
          <Settings class="mr-2 h-4 w-4" />
          {{ t("nav.settings") }}
        </router-link>
      </Button>

      <div class="mt-auto">
        <Separator class="mb-4" />
        <Select
          :model-value="locale"
          @update:model-value="(v: any) => (locale = v)"
        >
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Idioma / Language" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              v-for="l in LOCALES"
              :key="l.code"
              :value="l.code"
            >
              {{ l.label }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    </aside>

    <main class="flex-1 overflow-y-auto">
      <slot />
    </main>
  </div>
</template>