<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useTeamSync } from '../../composables/useTeamSync';
import { Users, Wifi, WifiOff, Copy, Check, Link, Globe, RefreshCw } from 'lucide-vue-next';

const { settings, status, roomMembers, createRoom, joinRoom, disconnect, updateSettings } = useTeamSync();

const serverUrlInput = ref(settings.value.serverUrl);
const nicknameInput = ref(settings.value.nickname);
const autoReportInput = ref(settings.value.autoReport);
const serverLanIp = ref('');
const linkCopied = ref(false);

const mobileUrl = computed(() => {
  const code = settings.value.roomCode;
  if (!code) return '';
  const url = settings.value.serverUrl.trim();
  const host = serverLanIp.value || '127.0.0.1';
  let target = url;
  if (target.includes('localhost') || target.includes('127.0.0.1')) {
    target = target.replace(/localhost|127\.0\.0\.1/, host);
  }
  return `${target.replace(/\/+$/, '')}/?room=${code}`;
});

watch(
  () => status.value,
  async (newStatus) => {
    if (newStatus === 'connected') {
      try {
        const res = await fetch(`${settings.value.serverUrl.replace(/\/+$/, '')}/api/v1/room/network/info`);
        const json = await res.json();
        if (json.code === 0 && json.data.ips?.length) {
          serverLanIp.value = json.data.ips[0];
        }
      } catch (_) {}
    }
  },
  { immediate: true },
);

function handleSaveSettings() {
  updateSettings({
    serverUrl: serverUrlInput.value.trim(),
    nickname: nicknameInput.value.trim(),
    autoReport: autoReportInput.value,
  });
}

function handleCopyLink() {
  if (!mobileUrl.value) return;
  navigator.clipboard.writeText(mobileUrl.value);
  linkCopied.value = true;
  setTimeout(() => (linkCopied.value = false), 2000);
}
</script>

<template>
  <div class="space-y-6 max-w-2xl text-fg">
    <!-- Header Banner -->
    <div class="rounded-xl border border-border bg-surface p-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Users class="h-5 w-5" />
          </div>
          <div>
            <h3 class="text-sm font-semibold">小队协同中枢</h3>
            <p class="text-xs text-fg-muted mt-0.5">
              开局自动上传对局数据，全队共享 1 次 AI 研判，手机立在显示器前即是战术副屏
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2 rounded-full border border-border bg-elevated px-3 py-1 text-xs">
          <Wifi v-if="status === 'connected'" class="h-3.5 w-3.5 text-emerald-400 animate-pulse" />
          <WifiOff v-else-if="status === 'error'" class="h-3.5 w-3.5 text-rose-400" />
          <span v-else class="h-2 w-2 rounded-full bg-zinc-500"></span>
          <span>
            {{ status === 'connected' ? '协同中枢在线' : status === 'connecting' ? '正在连接...' : '未连接' }}
          </span>
        </div>
      </div>
    </div>

    <!-- Active Room Status if connected -->
    <div v-if="status === 'connected' && settings.roomCode" class="rounded-xl border border-border bg-surface p-4 space-y-3">
      <div class="flex items-center justify-between">
        <span class="text-xs font-semibold text-fg-muted uppercase tracking-wider">当前小队房间</span>
        <span class="font-mono text-base font-bold text-primary tracking-widest">{{ settings.roomCode }}</span>
      </div>
      <div class="flex items-center justify-between rounded-lg bg-elevated p-2.5 text-xs">
        <span class="text-fg-muted">手机副屏直达链接:</span>
        <button
          class="flex items-center gap-1 text-primary hover:underline"
          @click="handleCopyLink"
        >
          <Check v-if="linkCopied" class="h-3.5 w-3.5 text-emerald-400" />
          <Copy v-else class="h-3.5 w-3.5" />
          {{ linkCopied ? '已复制' : '复制链接分享给队友' }}
        </button>
      </div>
      <p class="font-mono text-[11px] text-fg-muted break-all bg-surface p-2 rounded border border-border/50">
        {{ mobileUrl }}
      </p>
    </div>

    <!-- Configuration form -->
    <div class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <h4 class="text-xs font-semibold uppercase tracking-wider text-fg-muted">服务器与上报偏好</h4>

      <div class="space-y-3 text-xs">
        <div>
          <label class="font-medium text-fg">中枢服务器地址</label>
          <div class="mt-1.5 flex gap-2">
            <input
              v-model="serverUrlInput"
              class="flex-1 rounded-md border border-border bg-elevated px-3 py-2 text-xs focus:border-primary focus:outline-none"
              placeholder="http://localhost:3000 或局域网/云端地址"
            />
            <button
              class="rounded-md border border-border bg-elevated px-3 py-2 text-xs hover:bg-surface-hover"
              @click="serverUrlInput = 'http://localhost:3000'"
            >
              设为默认
            </button>
          </div>
          <p class="mt-1 text-[11px] text-fg-muted">
            本地单机运行填 http://localhost:3000；多台电脑局域网开黑填主机局域网 IP，云端部署填 VPS 公网域名。
          </p>
        </div>

        <div>
          <label class="font-medium text-fg">小队显示昵称</label>
          <input
            v-model="nicknameInput"
            class="mt-1.5 w-full rounded-md border border-border bg-elevated px-3 py-2 text-xs focus:border-primary focus:outline-none"
            placeholder="例如: 房主、队长"
          />
        </div>

        <div class="flex items-center justify-between pt-2">
          <div>
            <div class="font-medium text-fg">对局就绪自动上报</div>
            <div class="text-[11px] text-fg-muted">进入 5E / 完美准备阶段后，探针自动打包对局信息广播至小队房间</div>
          </div>
          <input
            v-model="autoReportInput"
            type="checkbox"
            class="h-4 w-4 rounded border-border bg-elevated text-primary focus:ring-0"
          />
        </div>
      </div>

      <div class="pt-3 border-t border-border flex justify-end">
        <button
          class="rounded-lg bg-primary px-4 py-2 text-xs font-medium text-white hover:bg-primary-hover transition-colors"
          @click="handleSaveSettings"
        >
          保存设置
        </button>
      </div>
    </div>
  </div>
</template>
