import type { MatchRecord } from '@core/match/models';

export function shouldReplayMatchReveal(
  record: MatchRecord,
  nextId: string,
  previousId?: string,
): boolean {
  if (previousId == null || previousId === nextId) return false;
  // 完美世界已移除，只剩 5E，切换对局时始终播放入场动画。
  return Boolean(record);
}
