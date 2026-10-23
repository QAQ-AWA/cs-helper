<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useTeamSync } from '../composables/useTeamSync';
import { Users, Wifi, WifiOff, Copy, Plus, LogIn, LogOut, Check, Link } from 'lucide-vue-next';

defineProps<{
  open: boolean;
}>();

const emit = defineEmits<{
  close: [];
}>();

const {
  settings,
  status,
  roomMembers,
  createRoom,
  joinRoom,
  disconnect,
  updateSettings,
} = useTeamSync();

const inputRoomCode = ref('');
const inputServerUrl = ref(settings.value.serverUrl);
const inputNickname = ref(settings.value.nickname);
const copied = ref(false);
const linkCopied = ref(false);
const serverLanIp = ref('');
const errorMsg = ref('');
const loading = ref(false);

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

function handleCopyLink() {
  if (!mobileUrl.value) return;
  navigator.clipboard.writeText(mobileUrl.value);
  linkCopied.value = true;
  setTimeout(() => (linkCopied.value = false), 2000);
}

function handleCopyCode() {
  if (!settings.value.roomCode) return;
  navigator.clipboard.writeText(settings.value.roomCode);
  copied.value = true;
  setTimeout(() => (copied.value = false), 2000);
}

async function handleCreateRoom() {
  errorMsg.value = '';
  loading.value = true;
  try {
    updateSettings({
      serverUrl: inputServerUrl.value.trim(),
      nickname: inputNickname.value.trim(),
    });
    await createRoom(inputNickname.value.trim());
  } catch (err: unknown) {
    errorMsg.value = String(err);
  } finally {
    loading.value = false;
  }
}

async function handleJoinRoom() {
  if (!inputRoomCode.value.trim()) {
    errorMsg.value = '请输入 6 位小队房间码';
    return;
  }
  errorMsg.value = '';
  loading.value = true;
  try {
    updateSettings({
      serverUrl: inputServerUrl.value.trim(),
      nickname: inputNickname.value.trim(),
    });
    await joinRoom(inputRoomCode.value.trim(), inputNickname.value.trim());
  } catch (err: unknown) {
    errorMsg.value = String(err);
  } finally {
    loading.value = false;
  }
}

function handleDisconnect() {
  disconnect();
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    @click.self="emit('close')"
  >
    <div class="relative w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-2xl">
      <div class="flex items-center justify-between border-b border-border pb-3">
        <div class="flex items-center gap-2">
          <Users class="h-5 w-5 text-primary" />
          <h3 class="text-base font-semibold text-text">小队对局协同中枢</h3>
        </div>
        <button
          class="rounded p-1 text-text-muted hover:bg-surface-hover hover:text-text"
          @click="emit('close')"
        >
          ✕
        </button>
      </div>

      <!-- Connection Status Banner -->
      <div class="mt-4 flex items-center justify-between rounded-lg bg-surface-elevated p-3 border border-border">
        <div class="flex items-center gap-2 text-sm">
          <Wifi v-if="status === 'connected'" class="h-4 w-4 text-emerald-500 animate-pulse" />
          <WifiOff v-else-if="status === 'error'" class="h-4 w-4 text-rose-500" />
          <span v-else class="h-3 w-3 rounded-full bg-amber-500 animate-ping"></span>
          <span class="font-medium text-text">
            {{
              status === 'connected'
                ? '已连接协同中枢'
                : status === 'connecting'
                ? '正在连接中枢...'
                : status === 'error'
                ? '连接失败'
                : '未连接'
            }}
          </span>
        </div>
        <div v-if="settings.roomCode" class="flex items-center gap-1.5">
          <span class="font-mono text-base font-bold tracking-wider text-primary">
            {{ settings.roomCode }}
          </span>
          <button
            class="rounded p-1 text-text-muted hover:text-text hover:bg-surface-hover"
            title="复制房间码"
            @click="handleCopyCode"
          >
            <Check v-if="copied" class="h-4 w-4 text-emerald-400" />
            <Copy v-else class="h-4 w-4" />
          </button>
        </div>
      </div>

      <!-- Error Toast -->
      <div v-if="errorMsg" class="mt-3 rounded bg-rose-500/10 p-2 text-xs text-rose-400 border border-rose-500/20">
        {{ errorMsg }}
      </div>

      <!-- Connected State: Room & Members -->
      <div v-if="status === 'connected' && settings.roomCode" class="mt-4 space-y-4">
        <div>
          <label class="text-xs font-semibold uppercase tracking-wider text-text-muted">
            房间在线小队 ({{ roomMembers.length }} 人)
          </label>
          <div class="mt-1.5 max-h-36 space-y-1.5 overflow-y-auto rounded-lg border border-border bg-surface-elevated p-2">
            <div
              v-for="member in roomMembers"
              :key="member.id"
              class="flex items-center justify-between text-xs py-1 px-1.5 rounded hover:bg-surface"
            >
              <div class="flex items-center gap-2">
                <span
                  class="h-2 w-2 rounded-full"
                  :class="member.isOnline ? 'bg-emerald-500' : 'bg-zinc-600'"
                ></span>
                <span class="font-medium text-text">{{ member.nickname }}</span>
              </div>
              <span class="rounded bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
                {{ member.deviceType === 'pc' ? '电脑探针' : '手机副屏' }}
              </span>
            </div>
          </div>
        </div>

        <!-- Quick Share Mobile Link -->
        <div class="rounded-lg border border-border bg-surface-elevated p-3">
          <div class="flex items-center justify-between text-xs font-semibold text-text-muted">
            <span class="flex items-center gap-1.5 text-text">
              <Link class="h-3.5 w-3.5 text-primary" />
              手机副屏直达链接
            </span>
            <button
              class="flex items-center gap-1 text-[11px] text-primary hover:underline"
              @click="handleCopyLink"
            >
              <Check v-if="linkCopied" class="h-3.5 w-3.5 text-emerald-400" />
              <Copy v-else class="h-3.5 w-3.5" />
              {{ linkCopied ? '已复制' : '复制链接' }}
            </button>
          </div>
          <p class="mt-2 font-mono text-[11px] text-zinc-300 break-all select-all bg-surface p-1.5 rounded border border-border/50">
            {{ mobileUrl }}
          </p>
        </div>

        <p class="text-xs text-text-muted leading-relaxed">
          💡 手机端只需下载/打开 APP 并输入房间码 <strong class="text-text font-mono">{{ settings.roomCode }}</strong>，即可实时同步赛前 AI 战术与对手走位！
        </p>

        <button
          class="w-full flex items-center justify-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 py-2 text-xs font-medium text-rose-400 hover:bg-rose-500/20 transition-colors"
          @click="handleDisconnect"
        >
          <LogOut class="h-3.5 w-3.5" /> 退出当前房间
        </button>
      </div>

      <!-- Disconnected State: Create or Join -->
      <div v-else class="mt-4 space-y-4">
        <div class="space-y-3">
          <div>
            <label class="text-xs font-medium text-text-muted">中枢服务器地址</label>
            <input
              v-model="inputServerUrl"
              class="mt-1 w-full rounded-md border border-border bg-surface-elevated px-3 py-1.5 text-xs text-text focus:border-primary focus:outline-none"
              placeholder="http://127.0.0.1:8787 或局域网/云端IP"
            />
          </div>

          <div>
            <label class="text-xs font-medium text-text-muted">我的小队昵称</label>
            <input
              v-model="inputNickname"
              class="mt-1 w-full rounded-md border border-border bg-surface-elevated px-3 py-1.5 text-xs text-text focus:border-primary focus:outline-none"
              placeholder="例如: 房主、队长"
            />
          </div>
        </div>

        <div class="flex gap-2 pt-2">
          <button
            class="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-primary py-2 text-xs font-medium text-white hover:bg-primary-hover disabled:opacity-50 transition-colors"
            :disabled="loading"
            @click="handleCreateRoom"
          >
            <Plus class="h-3.5 w-3.5" /> 创建新房间
          </button>
        </div>

        <div class="relative flex items-center justify-center">
          <div class="w-full border-t border-border"></div>
          <span class="absolute bg-surface px-2 text-[10px] text-text-muted">或加入已有房间</span>
        </div>

        <div class="flex gap-2">
          <input
            v-model="inputRoomCode"
            maxlength="6"
            class="w-2/3 uppercase text-center font-mono tracking-widest rounded-lg border border-border bg-surface-elevated px-3 py-1.5 text-xs text-text focus:border-primary focus:outline-none"
            placeholder="6位房间码"
          />
          <button
            class="flex-1 flex items-center justify-center gap-1 rounded-lg border border-border bg-surface-elevated py-1.5 text-xs font-medium text-text hover:bg-surface-hover transition-colors"
            :disabled="loading"
            @click="handleJoinRoom"
          >
            <LogIn class="h-3.5 w-3.5" /> 加入
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
