<template>
  <div class="login-shell">
    <section class="login-hero">
      <div class="eyebrow">农村承包经营权一体化平台</div>
      <h1>从权限、业务流到一张图的统一工作台</h1>
      <p>
        当前已接入数据库和 JWT 登录。接下来会继续扩展发包方管理、业务申请、三级审核流程和 WebGIS
        能力。
      </p>
    </section>

    <section class="login-card">
      <div class="panel-title">登录系统</div>
      <div class="login-tip">默认演示账号：admin / Admin123456</div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="compact-form"
        label-position="top"
        status-icon
        @submit.prevent="handleSubmit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            placeholder="请输入密码"
            show-password
            type="password"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-alert
          v-if="errorMessage"
          :closable="false"
          :title="errorMessage"
          class="login-alert"
          type="error"
        />

        <el-button
          :loading="authStore.loading"
          class="login-button"
          type="success"
          @click="handleSubmit"
        >
          登录
        </el-button>
      </el-form>
    </section>
  </div>
</template>

<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "../stores/auth";

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();
const errorMessage = ref("");
const formRef = ref();

const form = reactive({
  username: "admin",
  password: "Admin123456",
});

const rules = {
  username: [{ required: true, message: "请输入用户名", trigger: "blur" }],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

async function handleSubmit() {
  errorMessage.value = "";
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    return;
  }

  try {
    await authStore.login(form);
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/dashboard";
    router.push(redirect);
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "登录失败，请检查用户名和密码";
  }
}
</script>
