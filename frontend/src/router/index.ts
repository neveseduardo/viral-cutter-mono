import { createRouter, createWebHistory } from "vue-router"

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: "/",
      name: "new-edition",
      component: () => import("@/views/NewEditionView.vue"),
    },
    {
      path: "/library",
      name: "library",
      component: () => import("@/views/LibraryView.vue"),
    },
    {
      path: "/projects/:id",
      name: "project",
      component: () => import("@/views/ProjectDetailView.vue"),
      props: true,
    },
    {
      path: "/projects/:id/editor",
      name: "subtitle-editor",
      component: () => import("@/views/SubtitleEditorView.vue"),
      props: true,
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/views/SettingsView.vue"),
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
})

export default router