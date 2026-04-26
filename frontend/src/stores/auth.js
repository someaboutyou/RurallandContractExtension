import { defineStore } from "pinia";

import { fetchCurrentUser as fetchCurrentUserRequest, login as loginRequest } from "../api/auth";

const TOKEN_KEY = "rural_land_token";
const USER_KEY = "rural_land_user";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || "",
    user: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
    loading: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token),
    displayName: (state) => state.user?.realName || state.user?.username || "未登录",
    permissions: (state) => state.user?.permissions || [],
  },
  actions: {
    hasPermission(permissionCode) {
      return this.permissions.includes(permissionCode);
    },
    hasAnyPermission(permissionCodes) {
      return permissionCodes.some((item) => this.permissions.includes(item));
    },
    persistToken(token) {
      this.token = token;
      localStorage.setItem(TOKEN_KEY, token);
    },
    persistUser(user) {
      this.user = user;
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    },
    clearAuth() {
      this.token = "";
      this.user = null;
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    },
    async login(payload) {
      this.loading = true;
      try {
        const { data } = await loginRequest(payload);
        this.persistToken(data.data.access_token);
        await this.fetchCurrentUser();
      } finally {
        this.loading = false;
      }
    },
    async fetchCurrentUser() {
      if (!this.token) {
        return null;
      }
      const { data } = await fetchCurrentUserRequest();
      this.persistUser(data.data);
      return data.data;
    },
    async bootstrap() {
      if (!this.token) {
        return;
      }
      try {
        await this.fetchCurrentUser();
      } catch {
        this.clearAuth();
      }
    },
    logout() {
      this.clearAuth();
    },
  },
});
