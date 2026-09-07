import { defineStore } from "pinia"
import { computed, ref } from "vue"

import { api } from "@/api"

export const useAuthStore = defineStore("auth", () => {
  const authenticated = ref(false)
  const authDisabled = ref(true)
  const username = ref<string | null>(null)
  const loading = ref(false)

  const isAuthEnabled = computed(() => !authDisabled.value)

  async function init() {
    try {
      const cfg = (await api.getFrontendConfig()) as { auth_disabled?: boolean } & Record<string, unknown>
      authDisabled.value = cfg.auth_disabled ?? true
      authenticated.value = !authDisabled.value ? (localStorage.getItem("vc:token") != null) : true
    } catch {
      authenticated.value = true
    }
  }

  async function login(usernameOrEmail: string, password: string) {
    loading.value = true
    try {
      const res = await fetch(`/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: usernameOrEmail, password }),
      })
      if (!res.ok) throw new Error("Login falhou")
      const data = await res.json()
      localStorage.setItem("vc:token", data.access)
      localStorage.setItem("vc:refresh", data.refresh)
      authenticated.value = true
      username.value = usernameOrEmail
    } finally {
      loading.value = false
    }
  }

  function logout() {
    localStorage.removeItem("vc:token")
    localStorage.removeItem("vc:refresh")
    authenticated.value = false
  }

  // expose a token header helper for REST calls when auth is enabled
  function authHeaders(): Record<string, string> {
    const token = localStorage.getItem("vc:token")
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  return { authenticated, authDisabled, isAuthEnabled, username, loading, init, login, logout, authHeaders }
})