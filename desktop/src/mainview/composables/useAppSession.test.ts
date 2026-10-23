import { describe, expect, it } from 'vitest';
import { useAppSession } from './useAppSession';

describe('app session (5E only)', () => {
  it('starts on the 5E launch screen', () => {
    const session = useAppSession();
    expect(session.phase.value).toBe('p5e-launch');
  });

  it('enters the main view after the client is hooked up', () => {
    const session = useAppSession();
    session.completeP5eSetup();
    expect(session.phase.value).toBe('main');
  });

  it('can go back to the launch screen', () => {
    const session = useAppSession();
    session.completeP5eSetup();
    session.resetToP5eLaunch();
    expect(session.phase.value).toBe('p5e-launch');
  });
});
