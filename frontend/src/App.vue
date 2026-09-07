<script setup lang="ts">
import { Toaster } from "@/components/ui/sonner"
</script>

<template>
  <router-view />
  <Toaster class="pointer-events-none fixed inset-0 flex max-h-screen w-full flex-col-reverse p-4 sm:bottom-0 sm:right-0 sm:top-auto sm:flex-col sm:justify-end" />
</template>