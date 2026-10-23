<script setup lang="ts">
import { Layers } from 'lucide-vue-next';
import { computed, ref } from 'vue';
import PlatformLogo from '../PlatformLogo.vue';
import { historyFilterOptions, type HistoryPlatformFilter } from '../../utils/matchHistoryDisplay';
import { localize as l } from '../../i18n';

export type PlatformFilter = HistoryPlatformFilter;

defineProps<{
  filter: PlatformFilter;
  totalCount: number;
  loading?: boolean;
}>();

const emit = defineEmits<{
  'update:filter': [PlatformFilter];
}>();

const filters = computed(() => historyFilterOptions());
const scrollContainerRef = ref<HTMLElement | null>(null);

function scrollToTop() {
  const el = scrollContainerRef.value;
  if (el) el.scrollTop = 0;
}

defineExpose({ scrollToTop });
</script>

<template>
  <div class="flex h-full min-h-0 flex-col bg-[#FAFAFA]">
    <div ref="scrollContainerRef" class="min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto max-w-4xl px-6 py-8 sm:px-8 sm:py-10">
        <header class="mb-6 flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex items-baseline gap-2.5">
            <h1 class="text-[1.75rem] font-bold tracking-tight text-fg">
              {{ l('历史对局', 'Match history') }}
            </h1>
            <span
              v-if="loading || totalCount > 0"
              class="inline-flex min-w-8 items-center justify-center rounded-full bg-border/70 px-2.5 py-0.5 text-sm font-medium tabular-nums text-fg-secondary"
              :class="loading ? 'animate-pulse text-transparent' : ''"
              :aria-label="loading ? l('加载中', 'Loading') : l(`共 ${totalCount} 条`, `${totalCount} matches`)"
            >
              {{ loading ? '0' : totalCount }}
            </span>
          </div>

          <div
            class="flex rounded-lg bg-border/50 p-0.5"
            role="tablist"
            :aria-label="l('平台筛选', 'Platform filter')"
          >
            <button
              v-for="opt in filters"
              :key="opt.id"
              type="button"
              class="relative inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-all duration-200"
              :class="
                filter === opt.id
                  ? 'bg-surface text-fg shadow-sm ring-1 ring-black/5'
                  : 'text-fg-secondary hover:text-fg'
              "
              :aria-selected="filter === opt.id"
              @click="emit('update:filter', opt.id)"
            >
              <Layers
                v-if="opt.id === 'all'"
                class="h-4 w-4 shrink-0 opacity-80"
                aria-hidden="true"
              />
              <PlatformLogo
                v-else
                :platform-id="opt.id"
                size="xs"
              />
              {{ opt.label }}
            </button>
          </div>
        </header>

        <slot />
      </div>
    </div>
  </div>
</template>
