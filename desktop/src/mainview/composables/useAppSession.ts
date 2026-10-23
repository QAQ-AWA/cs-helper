import { setActivePlatformId } from '@platforms/registry';
import { ref } from 'vue';

/**
 * 5E-only app: the launch screen is the entry point. There is no platform
 * picker and no Perfect World login any more.
 */
export type AppPhase = 'p5e-launch' | 'main';

export function useAppSession() {
  setActivePlatformId('5e');
  const phase = ref<AppPhase>('p5e-launch');

  function completeP5eSetup() {
    phase.value = 'main';
  }

  function resetToP5eLaunch() {
    setActivePlatformId('5e');
    phase.value = 'p5e-launch';
  }

  return {
    phase,
    completeP5eSetup,
    resetToP5eLaunch,
  };
}
