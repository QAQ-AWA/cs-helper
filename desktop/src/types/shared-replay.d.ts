declare module '@shared/replay-core.js' {
  export const RADAR_SIZE: number;
  export const WINDOW_SECONDS: number;

  export interface ReplayTransform {
    pos_x: number;
    pos_y: number;
    scale: number;
  }

  export interface ReplayRound {
    side: 'CT' | 'T';
    rtype: string;
    round_id: number;
    path: number[][];
    grenades?: unknown[];
    death_t?: number | null;
  }

  export interface ReplayPlayerOptions {
    radar?: string;
    transform: ReplayTransform;
    rounds: ReplayRound[];
    side?: string | null;
    rtype?: string | null;
    autoplay?: boolean;
    onTick?: (player: ReplayPlayer) => void;
  }

  export function gameToPixel(transform: ReplayTransform, gx: number, gy: number): [number, number];
  export function roundEnd(round: { path?: number[][] }, fallback?: number): number;
  export function matchesFilter(
    round: { side?: string; rtype?: string },
    side?: string | null,
    rtype?: string | null,
  ): boolean;
  export function sampleAt(path: number[][], t: number): number[] | null;

  export class ReplayPlayer {
    constructor(canvas: HTMLCanvasElement, options: ReplayPlayerOptions);
    readonly duration: number;
    readonly progress: number;
    readonly activeRounds: number;
    playing: boolean;
    setFilter(side: string | null, rtype: string | null): void;
    setSpeed(speed: number): void;
    play(): void;
    pause(): void;
    toggle(): boolean;
    seek(seconds: number): void;
    seekRatio(ratio: number): void;
    resize(): void;
    destroy(): void;
  }
}
