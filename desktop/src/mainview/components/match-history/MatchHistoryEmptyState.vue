<script setup lang="ts">
import { Archive } from 'lucide-vue-next';
import { localize as l } from '../../i18n';
</script>

<template>
  <div class="flex flex-col items-center justify-center py-24 text-center">
    <div class="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-surface shadow-sm ring-1 ring-border/60">
      <Archive class="h-6 w-6 text-fg-muted" />
    </div>
    <div class="text-[1rem] leading-6">
      <h3 class="font-semibold text-fg">{{ l('还没有历史对局', 'No match history yet') }}</h3>
    </div>
    <p class="mt-1.5 max-w-sm text-[0.875rem] leading-5 text-fg-secondary">
      {{ l('匹配成功后会自动保存对局数据快照', 'Match snapshots are saved automatically when a match is found.') }}
    </p>
  </div>
</template>
