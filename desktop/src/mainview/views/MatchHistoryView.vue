<script setup lang="ts">
import type { MatchHistoryListItem, MatchHistoryViewModel } from '@core/match/history';
import { computed, nextTick, onMounted, ref, shallowRef, watch } from 'vue';
import MatchWorkspace from '../components/MatchWorkspace.vue';
import MatchHistoryEmptyState from '../components/match-history/MatchHistoryEmptyState.vue';
import MatchHistoryListRow from '../components/match-history/MatchHistoryListRow.vue';
import MatchHistoryListShell, {
  type PlatformFilter,
} from '../components/match-history/MatchHistoryListShell.vue';
import MatchHistoryPagination from '../components/match-history/MatchHistoryPagination.vue';
import type { MatchHistoryApi } from '../composables/useMatchHistory';
import type { useComments } from '../composables/useComments';
import {
  historyPrimaryMapTitle,
  matchesPlatformFilter,
  sortHistoryItemsNewestFirst,
} from '../utils/matchHistoryDisplay';
import type { P5ePostMatchReport } from '@platforms/5e/post-match';
import { localize as l } from '../i18n';

const PAGE_SIZE = 20;

const props = defineProps<{
  history: MatchHistoryApi;
  comments?: ReturnType<typeof useComments>;
  viewerSteamId?: string;
  /** 历史 Tab 是否可见；用于在显示后再触发列表入场动画 */
  visible?: boolean;
}>();



const filter = ref<PlatformFilter>('all');
const currentPage = ref(1);
const listShellRef = ref<InstanceType<typeof MatchHistoryListShell> | null>(null);
const selectedKey = ref<string | null>(null);
const detailVm = shallowRef<MatchHistoryViewModel | null>(null);
const detailLoading = ref(false);
const detailError = ref<string | null>(null);
const deleteConfirmItem = ref<MatchHistoryListItem | null>(null);
const detailReady = ref(false);
const listRevealKey = ref(0);

watch(
  () => props.visible,
  (visible) => {
    if (visible !== false) {
      listRevealKey.value += 1;
    }
  },
  { immediate: true },
);

const filteredEntries = computed(() => {
  const list = props.history.listItems.value.filter((item) =>
    matchesPlatformFilter(item.platformId, filter.value),
  );
  return sortHistoryItemsNewestFirst(list);
});

const totalCount = computed(() => filteredEntries.value.length);
const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / PAGE_SIZE)));

const pagedEntries = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE;
  return filteredEntries.value.slice(start, start + PAGE_SIZE);
});

watch(filter, () => {
  currentPage.value = 1;
});

watch([currentPage, filter], () => {
  void nextTick(() => listShellRef.value?.scrollToTop());
});

watch(totalPages, (pages) => {
  if (currentPage.value > pages) {
    currentPage.value = pages;
  }
});

function entryKey(item: Pick<MatchHistoryListItem, 'platformId' | 'id'>): string {
  return `${item.platformId}::${item.id}`;
}

async function openEntry(item: MatchHistoryListItem) {
  selectedKey.value = entryKey(item);
  detailLoading.value = true;
  detailError.value = null;
  detailVm.value = null;
  detailReady.value = false;
  try {
    const vm = await props.history.loadEntry(item.platformId, item.id);
    if (!vm || !vm.record) {
      detailError.value = vm?.unsupportedSections.includes('match')
        ? l('数据格式较新，请升级客户端后查看', 'This data requires a newer app version.')
        : l('无法加载该对局详情', 'Could not load match details');
      return;
    }
    detailVm.value = vm;
    detailReady.value = true;
  } catch (e) {
    detailError.value = e instanceof Error ? e.message : String(e);
  } finally {
    detailLoading.value = false;
  }
}

async function backToList() {
  selectedKey.value = null;
  detailVm.value = null;
  detailReady.value = false;
  detailError.value = null;
}

function goBack(): boolean {
  if (selectedKey.value) {
    void backToList();
    return true;
  }
  return false;
}

function onPostMatchUpdated(report: P5ePostMatchReport) {
  if (!detailVm.value?.record) return;
  void props.history.patchMatchPostMatch(
    detailVm.value.document.id,
    detailVm.value.document.platformId,
    report,
    detailVm.value.record,
  );
}

defineExpose({ goBack });

function requestRemoveItem(item: MatchHistoryListItem, event?: Event) {
  event?.stopPropagation();
  deleteConfirmItem.value = item;
}

async function confirmRemoveItem() {
  const item = deleteConfirmItem.value;
  if (!item) return;
  deleteConfirmItem.value = null;
  await props.history.removeEntry(item);
  if (selectedKey.value === entryKey(item)) {
    await backToList();
  }
  if (pagedEntries.value.length === 0 && currentPage.value > 1) {
    currentPage.value -= 1;
  }
}

onMounted(() => {
  void props.history.refreshList();
});
</script>

<template>
  <div class="flex h-full min-h-0 flex-col">
    <template v-if="!selectedKey">
      <MatchHistoryListShell
        ref="listShellRef"
        v-model:filter="filter"
        :total-count="totalCount"
        :loading="history.loading.value && !history.listItems.value.length"
      >
        <div
          v-if="history.loading.value && !history.listItems.value.length"
          class="space-y-3"
        >
          <div
            v-for="i in 4"
            :key="i"
            class="h-[88px] animate-pulse rounded-2xl bg-surface/80 ring-1 ring-border/60"
          />
        </div>
        <div v-else-if="history.error.value" class="py-20 text-center text-[13px] text-danger">
          {{ history.error.value }}
        </div>
        <MatchHistoryEmptyState v-else-if="!filteredEntries.length" />
        <template v-else>
          <TransitionGroup
            :key="`${listRevealKey}:${filter}:${currentPage}`"
            name="history-row"
            tag="ul"
            appear
            class="flex flex-col gap-3"
          >
            <MatchHistoryListRow
              v-for="(item, index) in pagedEntries"
              :key="entryKey(item)"
              v-memo="[item.id, item.platformId, item.updatedAt, item.mapName, item.matchAvgScore, item.aiStatus]"
              :item="item"
              :stagger-index="index"
              @open="openEntry(item)"
              @remove="requestRemoveItem(item, $event)"
            />
          </TransitionGroup>

          <MatchHistoryPagination
            v-model:current-page="currentPage"
            :total-count="totalCount"
            :total-pages="totalPages"
            :page-size="PAGE_SIZE"
          />
        </template>
      </MatchHistoryListShell>
    </template>

    <template v-else>
      <div class="flex h-full min-h-0 flex-col bg-[#F1F5F9]">
        <div
          v-if="detailVm?.unsupportedSections.length"
          class="shrink-0 border-b border-amber-200 bg-amber-50 px-4 py-2 text-[11px] text-amber-700"
        >
          {{ l('部分数据格式较新，请升级客户端后查看完整内容', 'Some data requires a newer app version.') }}
        </div>

        <div class="min-h-0 flex-1 overflow-hidden">
          <div v-if="detailLoading" class="flex h-full items-center justify-center text-[13px] text-fg-secondary">
            {{ l('加载详情…', 'Loading details…') }}
          </div>
          <div v-else-if="detailError" class="flex h-full items-center justify-center text-[13px] text-danger">
            {{ detailError }}
          </div>
          <MatchWorkspace
            v-else-if="detailVm?.record && detailReady"
            history-mode
            :match="detailVm.record"
            :initial-post-match="detailVm.postMatch"
            :stored-ai="detailVm.ai?.result ?? null"
            @post-match-updated="onPostMatchUpdated"
          />
        </div>
      </div>
    </template>

    <!-- 单条删除确认 -->
    <div
      v-if="deleteConfirmItem"
      class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      @pointerdown.self="deleteConfirmItem = null"
    >
      <div class="w-full max-w-sm rounded-2xl bg-surface p-5 shadow-2xl ring-1 ring-black/5">
        <h2 class="text-[15px] font-semibold text-fg">{{ l('删除这条对局记录？', 'Delete this match?') }}</h2>
        <p class="mt-1.5 text-[12px] leading-relaxed text-fg-secondary">
          {{ l(`将删除“${historyPrimaryMapTitle(deleteConfirmItem)}”的本地快照，此操作不可恢复。`, `The local snapshot for “${historyPrimaryMapTitle(deleteConfirmItem)}” will be permanently deleted.`) }}
        </p>
        <div class="mt-5 flex justify-end gap-2">
          <button
            type="button"
            class="cursor-pointer rounded-lg px-3 py-1.5 text-[12px] font-medium text-fg-secondary transition-colors hover:bg-elevated"
            @click="deleteConfirmItem = null"
          >
            {{ l('取消', 'Cancel') }}
          </button>
          <button
            type="button"
            class="cursor-pointer rounded-lg bg-rose-600 px-3 py-1.5 text-[12px] font-semibold text-white transition-colors hover:bg-rose-700 active:scale-[0.96]"
            @click="confirmRemoveItem"
          >
            {{ l('确认删除', 'Delete') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
