import { createI18n } from "vue-i18n"

import en from "./en"
import ptBR from "./pt-BR"

export const LOCALES = [
  { code: "pt-BR", label: "Português" },
  { code: "en", label: "English" },
]

export const i18n = createI18n({
  legacy: false,
  locale: localStorage.getItem("vc:locale") ?? navigator.language.startsWith("pt") ? "pt-BR" : "en",
  fallbackLocale: "en",
  messages: {
    "pt-BR": ptBR,
    en,
  },
})