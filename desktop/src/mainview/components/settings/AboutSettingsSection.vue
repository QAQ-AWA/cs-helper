<script setup lang="ts">
import appIcon from '@app-icon';
import iconGithub from '@/assets/icons/github.svg';
import { ExternalLink, Loader2, RefreshCw } from 'lucide-vue-next';
import { computed } from 'vue';
import { useUpdateCheck } from '../../composables/useUpdateCheck';
import { openExternalUrl } from '../../native';
import UpdateBadge from '../UpdateBadge.vue';
import { localize as l } from '../../i18n';

const appName = computed(() => l('CS 匹配助手', 'CS Match Helper'));
const { state, formattedVersion, isBusy, checkManual, openDialog } = useUpdateCheck();
// Tauri 的 getVersion 在某些环境下拿不到，回退到构建期注入的版本，
// 免得「版本」那一行只剩一个空白。
const versionText = computed(() => formattedVersion.value || __APP_VERSION__);
// 模板里取不到全局常量，先落到 setup 作用域。
const buildStamp = __BUILD_STAMP__;

const repoUrl = 'https://github.com/QAQ-AWA/cs-helper';
const repoIssuesUrl = `${repoUrl}/issues`;

const updateActionLabel = computed(() =>
  state.checking ? l('检查中…', 'Checking…') : l('检查更新', 'Check for updates'),
);

function openRepo() {
  void openExternalUrl(repoUrl);
}

function openIssues() {
  void openExternalUrl(repoIssuesUrl);
}
</script>

<template>
  <section class="overflow-hidden rounded-xl border border-border bg-surface">
    <div
      class="flex flex-col items-center gap-3 border-b border-border-subtle bg-elevated/30 px-5 py-6 text-center"
    >
      <img :src="appIcon" :alt="appName" class="h-16 w-16 rounded-2xl object-cover" />
      <div>
        <h3 class="text-[16px] font-semibold tracking-tight text-fg">{{ appName }}</h3>
        <p class="mt-1 text-[12px] text-fg-muted">
          {{ l('5E 对局情报 · 服务端分析', '5E match intel, analysed server-side') }}
        </p>
      </div>
    </div>

    <div class="flex items-center justify-between gap-4 border-b border-border-subtle px-5 py-4">
      <span class="shrink-0 text-[13px] text-fg-muted">{{ l('版本', 'Version') }}</span>
      <div class="min-w-0 text-right">
        <div class="flex items-center justify-end gap-2">
          <span class="text-[13px] font-semibold tabular-nums text-fg">{{ versionText }}</span>
          <UpdateBadge v-if="state.hasUpdate" @click="openDialog" />
        </div>
        <!-- 版本号常年不变，装的是哪次构建只能看这里。 -->
        <p class="mt-0.5 text-[11px] tabular-nums text-fg-muted">{{ l('构建', 'Build') }} {{ buildStamp }}</p>
        <button
          v-if="!state.hasUpdate"
          type="button"
          class="group mt-1 inline-flex cursor-pointer items-center gap-1 rounded-md py-0.5 text-[12px] font-medium leading-none text-accent transition-colors duration-200 hover:bg-accent/10 hover:text-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="state.checking || isBusy"
          :aria-label="updateActionLabel"
          @click="checkManual()"
        >
          <span>{{ updateActionLabel }}</span>
          <Loader2
            v-if="state.checking"
            class="h-3.5 w-3.5 shrink-0 animate-spin text-accent"
            aria-hidden="true"
          />
          <RefreshCw
            v-else
            class="h-3.5 w-3.5 shrink-0 text-accent/75 transition-colors duration-200 group-hover:text-accent"
            aria-hidden="true"
          />
        </button>
      </div>
    </div>

    <div class="flex items-center justify-between gap-4 border-b border-border-subtle px-5 py-4">
      <span class="text-[13px] text-fg-muted">{{ l('反馈', 'Feedback') }}</span>
      <button
        type="button"
        class="group inline-flex cursor-pointer items-center gap-1.5 rounded-md py-px transition-colors duration-200 hover:bg-elevated"
        :aria-label="l('GitHub Issues 反馈', 'Report an issue on GitHub')"
        :title="repoIssuesUrl"
        @click="openIssues"
      >
        <img
          :src="iconGithub"
          alt=""
          class="h-4 w-4 opacity-50 transition-opacity duration-200 group-hover:opacity-100"
          aria-hidden="true"
        />
        <span
          class="text-[13px] font-medium text-accent transition-colors duration-200 group-hover:text-accent-hover"
        >
          Issue
        </span>
      </button>
    </div>

    <div class="flex items-center justify-between gap-4 px-5 py-4">
      <span class="shrink-0 text-[13px] text-fg-muted">{{ l('源代码', 'Source code') }}</span>
      <button
        type="button"
        class="group flex min-w-0 cursor-pointer items-center gap-1.5 text-right transition-colors duration-200"
        :title="repoUrl"
        @click="openRepo"
      >
        <span class="truncate text-[13px] font-medium text-accent group-hover:text-accent-hover">
          github.com/QAQ-AWA/cs-helper
        </span>
        <ExternalLink
          class="h-3.5 w-3.5 shrink-0 text-accent/70 transition-colors duration-200 group-hover:text-accent"
          aria-hidden="true"
        />
      </button>
    </div>
  </section>
</template>
