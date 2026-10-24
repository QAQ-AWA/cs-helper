<script setup lang="ts">
import { computed } from 'vue';
import { X } from 'lucide-vue-next';
import { localize as l } from '../i18n';

/**
 * 这一局我方是 CT 还是 T。
 *
 * 服务端只认「客户端明确说过的」和「身份库里认过的」，猜不出的时候不能替用户选：
 * 选错边会把整份分析翻到对手身上，比没有分析更糟。所以第一次遇到未知阵营时
 * 直接问，选完记进身份库，下一局同样五个人就不用再问。
 */
const props = defineProps<{
  open: boolean;
  busy?: boolean;
  teams?: { ct: string[]; t: string[] };
}>();

const emit = defineEmits<{
  pick: [side: 'ct' | 't'];
  analyzeAll: [];
  close: [];
}>();

function names(side: 'ct' | 't'): string {
  const list = (props.teams?.[side] ?? []).filter(Boolean);
  if (!list.length) return l('名单还没到', 'Roster pending');
  const head = list.slice(0, 3).join('、');
  return list.length > 3 ? `${head} 等 ${list.length} 人` : head;
}

const options = computed(() => [
  { side: 'ct' as const, label: 'CT', hint: names('ct') },
  { side: 't' as const, label: 'T', hint: names('t') },
]);
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
    role="dialog"
    aria-modal="true"
    aria-labelledby="side-picker-title"
  >
    <section class="w-full max-w-lg rounded-xl border border-border bg-surface p-5 shadow-xl">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h2 id="side-picker-title" class="text-[15px] font-semibold text-fg">
            {{ l('这一局你在哪边？', 'Which side are you on?') }}
          </h2>
          <p class="mt-1 text-[12px] leading-relaxed text-fg-muted">
            {{ l(
              '服务端没法从名单里认出你，选错边整份分析会翻到对手身上。选完会记住，下一局同样的人不用再选。',
              'The relay cannot tell which player you are. Picking the wrong side flips the whole report onto the opponents. It remembers your choice for next time.',
            ) }}
          </p>
        </div>
        <button
          type="button"
          class="shrink-0 cursor-pointer rounded-md p-1 text-fg-muted transition-colors hover:bg-elevated hover:text-fg"
          :aria-label="l('稍后再说', 'Later')"
          @click="emit('close')"
        >
          <X class="h-4 w-4" />
        </button>
      </div>

      <div class="mt-4 grid gap-2 sm:grid-cols-2">
        <button
          v-for="option in options"
          :key="option.side"
          type="button"
          class="group cursor-pointer rounded-lg border border-border bg-elevated/40 px-4 py-3 text-left transition-colors hover:border-accent hover:bg-accent/5 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="busy"
          @click="emit('pick', option.side)"
        >
          <span class="text-[13px] font-semibold text-fg">
            {{ l(`我方是 ${option.label}`, `We are ${option.label}`) }}
          </span>
          <span class="mt-1 block truncate text-[11px] text-fg-muted">{{ option.hint }}</span>
        </button>
      </div>

      <div class="mt-3 flex items-center justify-between">
        <button
          type="button"
          class="cursor-pointer text-[12px] text-fg-muted underline-offset-2 hover:text-fg hover:underline"
          :disabled="busy"
          @click="emit('analyzeAll')"
        >
          {{ l('先不分敌我，十个人都看', 'Analyze all ten for now') }}
        </button>
        <span v-if="busy" class="text-[11px] text-accent">{{ l('正在按新阵营重算…', 'Re-running…') }}</span>
      </div>
    </section>
  </div>
</template>
