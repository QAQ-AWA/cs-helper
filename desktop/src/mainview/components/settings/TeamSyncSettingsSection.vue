<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Check, Copy, LogIn, LogOut, Plus, RefreshCw } from 'lucide-vue-next';
import { useTeamSync } from '../../composables/useTeamSync';

/**
 * 连接服务端 = 这个项目的入口动作。之前这一块只有「保存设置」，
 * createRoom/joinRoom 解构了却没接到按钮上，等于没法从设置页连房间。
 */
const { settings, status, roomMembers, createRoom, joinRoom, disconnect, updateSettings } = useTeamSync();

const serverUrlInput = ref(settings.value.serverUrl);
const nicknameInput = ref(settings.value.nickname);
const autoReportInput = ref(settings.value.autoReport);
const roomCodeInput = ref('');
const reportKeyInput = ref(settings.value.reportKey ?? '');
const reportKeyRequired = ref(false);
const serverLanIp = ref('');
const linkCopied = ref(false);
const busy = ref(false);
const error = ref<string | null>(null);

const connected = computed(() => status.value === 'connected');
const mobileUrl = computed(() => {
  const code = settings.value.roomCode;
  if (!code) return '';
  const base = settings.value.serverUrl.trim().replace(/\/+$/, '');
  const host = serverLanIp.value || '127.0.0.1';
  const target = base.includes('localhost') || base.includes('127.0.0.1')
    ? base.replace(/localhost|127\.0\.0\.1/, host)
    : base;
  return `${target}/?room=${code}`;
});

const statusText = computed(() => {
  switch (status.value) {
    case 'connected':
      return '已连接';
    case 'connecting':
      return '连接中…';
    case 'error':
      return '连接失败';
    default:
      return '未连接';
  }
});

watch(
  () => status.value,
  async (next) => {
    if (next !== 'connected') return;
    try {
      const res = await fetch(`${settings.value.serverUrl.replace(/\/+$/, '')}/api/v1/room/network/info`);
      const json = await res.json();
      if (json.code === 0 && json.data.ips?.length) serverLanIp.value = json.data.ips[0];
    } catch {
      // 局域网信息只是锦上添花
    }
    try {
      const cfg = await fetch(`${serverUrlInput.value.trim().replace(/\/+$/, '')}/api/v1/config`);
      const json = await cfg.json();
      if (json.code === 0) reportKeyRequired.value = json.data?.reportKeyRequired === true;
    } catch {
      // 拿不到就按「不需要」处理，填不填都不影响上报
    }
  },
  { immediate: true },
);

function savePreferences() {
  updateSettings({
    serverUrl: serverUrlInput.value.trim(),
    nickname: nicknameInput.value.trim(),
    autoReport: autoReportInput.value,
    reportKey: reportKeyInput.value.trim(),
  });
}

async function run(action: () => Promise<unknown>) {
  busy.value = true;
  error.value = null;
  try {
    savePreferences();
    await action();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

function handleCreate() {
  void run(() => createRoom(nicknameInput.value.trim() || undefined));
}

function handleJoin() {
  const code = roomCodeInput.value.trim().toUpperCase();
  if (!code) {
    error.value = '请输入房间码';
    return;
  }
  void run(() => joinRoom(code, nicknameInput.value.trim() || undefined));
}

function handleCopy() {
  if (!mobileUrl.value) return;
  void navigator.clipboard.writeText(mobileUrl.value);
  linkCopied.value = true;
  window.setTimeout(() => (linkCopied.value = false), 2000);
}
</script>

<template>
  <div class="max-w-2xl space-y-4 text-fg">
    <!-- 状态 -->
    <section class="rounded-xl border border-border bg-surface px-4 py-3">
      <div class="flex items-center gap-2">
        <span
          class="h-2 w-2 rounded-full"
          :class="
            connected
              ? 'bg-success'
              : status === 'connecting'
                ? 'bg-warning'
                : status === 'error'
                  ? 'bg-danger'
                  : 'bg-fg-muted'
          "
        />
        <span class="text-sm font-medium">{{ statusText }}</span>
        <span v-if="connected && settings.roomCode" class="font-mono text-sm font-semibold tracking-widest text-accent">
          {{ settings.roomCode }}
        </span>
        <span v-if="connected" class="text-[11px] text-fg-muted">
          {{ roomMembers.length }} 台设备
        </span>
        <button
          v-if="settings.enabled"
          type="button"
          class="ml-auto inline-flex cursor-pointer items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-fg-secondary hover:text-fg"
          :disabled="busy"
          @click="run(async () => disconnect())"
        >
          <LogOut class="h-3 w-3" />断开
        </button>
      </div>

      <p v-if="error" class="mt-2 text-[11px] text-danger">{{ error }}</p>

      <!-- 已连接：房间码 + 手机链接 -->
      <div v-if="connected && settings.roomCode" class="mt-3 space-y-2">
        <div class="flex items-center gap-2 rounded-lg bg-elevated px-3 py-2">
          <span class="text-[11px] text-fg-muted">手机打开</span>
          <span class="min-w-0 flex-1 truncate font-mono text-[11px] text-fg-secondary">{{ mobileUrl }}</span>
          <button
            type="button"
            class="inline-flex cursor-pointer items-center gap-1 text-[11px] text-accent hover:underline"
            @click="handleCopy"
          >
            <Check v-if="linkCopied" class="h-3 w-3" />
            <Copy v-else class="h-3 w-3" />
            {{ linkCopied ? '已复制' : '复制' }}
          </button>
        </div>
        <div v-for="member in roomMembers" :key="member.id" class="flex items-center gap-2 text-[11px] text-fg-muted">
          <span class="h-1.5 w-1.5 rounded-full" :class="member.isOnline ? 'bg-success' : 'bg-fg-muted'" />
          {{ member.nickname }}
          <span class="text-[10px]">{{ member.deviceType === 'pc' ? '电脑' : '手机' }}</span>
        </div>
      </div>

      <!-- 未连接：建房 / 加入 -->
      <div v-else class="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          :disabled="busy"
          @click="handleCreate"
        >
          <Plus class="h-3.5 w-3.5" />创建房间
        </button>
        <span class="text-[11px] text-fg-muted">或</span>
        <input
          v-model="roomCodeInput"
          class="w-28 rounded-md border border-border bg-elevated px-2 py-1.5 font-mono text-xs uppercase tracking-widest focus:border-accent focus:outline-none"
          placeholder="房间码"
          maxlength="12"
        />
        <button
          type="button"
          class="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-fg-secondary hover:text-fg disabled:opacity-50"
          :disabled="busy"
          @click="handleJoin"
        >
          <LogIn class="h-3.5 w-3.5" />加入
        </button>
      </div>
    </section>

    <!-- 偏好 -->
    <section class="space-y-4 rounded-xl border border-border bg-surface p-4">
      <h4 class="text-xs font-semibold uppercase tracking-wider text-fg-muted">服务器与上报</h4>

      <label class="block text-xs">
        <span class="font-medium text-fg">服务端地址</span>
        <div class="mt-1.5 flex gap-2">
          <input
            v-model="serverUrlInput"
            class="flex-1 rounded-md border border-border bg-elevated px-3 py-2 text-xs focus:border-accent focus:outline-none"
            placeholder="http://127.0.0.1:8787"
          />
          <button
            type="button"
            class="cursor-pointer rounded-md border border-border px-3 py-2 text-xs text-fg-secondary hover:text-fg"
            @click="serverUrlInput = 'http://127.0.0.1:8787'"
          >
            本机
          </button>
        </div>
        <p class="mt-1 text-[11px] text-fg-muted">
          本机运行填 127.0.0.1:8787；局域网开黑填主机 IP，手机与电脑要在同一网络。
        </p>
      </label>

      <label class="block text-xs">
        <span class="font-medium text-fg">我的昵称</span>
        <input
          v-model="nicknameInput"
          class="mt-1.5 w-full rounded-md border border-border bg-elevated px-3 py-2 text-xs focus:border-accent focus:outline-none"
          placeholder="房主"
        />
      </label>

      <label class="block text-xs">
        <span class="font-medium text-fg">
          上报密钥
          <span v-if="reportKeyRequired" class="ml-1 rounded bg-warning/15 px-1 py-0.5 text-[10px] text-warning">
            服务端要求
          </span>
        </span>
        <input
          v-model="reportKeyInput"
          type="password"
          autocomplete="off"
          class="mt-1.5 w-full rounded-md border border-border bg-elevated px-3 py-2 font-mono text-xs focus:border-accent focus:outline-none"
          placeholder="服务端没设就留空"
        />
        <p class="mt-1 text-[11px] text-fg-muted">
          服务端设了 <code>CS_HELPER_REPORT_KEY</code> 时必须填一致，否则上报会被拒绝（手机端只看不传，不需要它）。
        </p>
      </label>

      <div class="flex items-center justify-between">
        <div>
          <div class="text-xs font-medium text-fg">检测到对局后自动上报</div>
          <div class="text-[11px] text-fg-muted">5E 进入准备阶段时自动把阵容发给服务端</div>
        </div>
        <input
          v-model="autoReportInput"
          type="checkbox"
          class="h-4 w-4 rounded border-border bg-elevated text-accent focus:ring-0"
        />
      </div>

      <div class="flex items-center justify-between border-t border-border pt-3">
        <span class="text-[11px] text-fg-muted">
          <RefreshCw class="mr-1 inline h-3 w-3 align-[-2px]" />
          改完地址/昵称后需要重新连接
        </span>
        <button
          type="button"
          class="cursor-pointer rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-accent-hover"
          @click="savePreferences"
        >
          保存
        </button>
      </div>
    </section>
  </div>
</template>
