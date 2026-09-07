<script setup lang="ts">
import { computed, onMounted } from "vue"
import { useI18n } from "vue-i18n"
import { useConfigStore } from "@/stores/configStore"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import AppShell from "@/components/domain/AppShell.vue"

const { t } = useI18n()
const configStore = useConfigStore()

onMounted(() => configStore.load())

interface ProviderInfo {
  name: string
  label: string
  local: boolean
}

const providers = computed<ProviderInfo[]>(() =>
  (configStore.config?.providers ?? []).map((name) => ({
    name,
    label: name,
    local: name === "ollama" || name === "manual",
  })),
)

const limits = computed(() => Object.entries(configStore.config?.limits ?? {}))

function setProviderKey(name: string, value: string) {
  localStorage.setItem(`vc:provider:${name}`, value)
}
function getProviderKey(name: string) {
  return localStorage.getItem(`vc:provider:${name}`) ?? ""
}
</script>

<template>
  <AppShell>
    <div class="mx-auto max-w-4xl p-6">
      <header class="mb-8">
        <h1 class="font-display text-3xl font-bold">
          {{ t("settings.title") }}
        </h1>
        <p class="mt-1 text-muted-foreground">
          {{ t("settings.restoreFromServer") }}
        </p>
      </header>

      <div class="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle class="text-base">
              {{ t("settings.providers") }}
            </CardTitle>
            <CardDescription>Chaves ficam no servidor (env).</CardDescription>
          </CardHeader>
          <CardContent class="space-y-3">
            <div
              v-if="providers.length"
              class="grid gap-3 sm:grid-cols-2"
            >
              <div
                v-for="p in providers"
                :key="p.name"
                class="space-y-1.5 rounded-md border p-3"
              >
                <div class="flex items-center justify-between">
                  <Label>{{ p.label }}</Label>
                  <Badge variant="secondary">
                    {{ p.local ? "local" : p.name }}
                  </Badge>
                </div>
                <Input
                  v-if="!p.local"
                  :model-value="getProviderKey(p.name)"
                  type="password"
                  placeholder="chave (opcional no modo local)"
                  @update:model-value="setProviderKey(p.name, String($event))"
                />
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

        <Card>
          <CardHeader>
            <CardTitle class="text-base">
              {{ t("settings.limits") }}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table v-if="limits.length">
              <TableHeader>
                <TableRow><TableHead>Limite</TableHead><TableHead>Valor</TableHead></TableRow>
              </TableHeader>
              <TableBody>
                <TableRow
                  v-for="[k, v] in limits"
                  :key="k"
                >
                  <TableCell class="font-mono text-sm">
                    {{ k }}
                  </TableCell>
                  <TableCell class="code text-sm">
                    {{ v }}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Separator />

        <p class="text-xs text-muted-foreground">
          AI_FAILOVER, perfis e modelos são controlados pelo servidor (ProcessingProfile §5.8).
        </p>
      </div>
    </div>
  </AppShell>
</template>