/**
 * Radar replay renderer.
 *
 * Framework-free on purpose: the phone page imports it directly, and the
 * desktop shell can import the same file later. Coordinates in the payload are
 * CS2 world units; `transform` maps them onto the radar bitmap (1024x1024).
 */

export const RADAR_SIZE = 1024;
export const WINDOW_SECONDS = 20;

const SIDE_COLOR = { CT: '#5b9cf8', T: '#e0a44a' };
const GRENADE_COLOR = {
  smoke: '#9aa4b2',
  flash: '#f0d264',
  he: '#d98c5f',
  molotov: '#e2593f',
  decoy: '#7fb3a8',
};

export function gameToPixel(transform, gx, gy) {
  return [(gx - transform.pos_x) / transform.scale, (transform.pos_y - gy) / transform.scale];
}

/** Latest timestamp present in a round, so a round with a short path still fits. */
export function roundEnd(round, fallback = WINDOW_SECONDS) {
  const path = round && round.path;
  if (!path || !path.length) return fallback;
  const last = path[path.length - 1];
  return typeof last[0] === 'number' ? last[0] : fallback;
}

export function matchesFilter(round, side, rtype) {
  if (!round) return false;
  if (side && round.side !== side) return false;
  if (rtype && round.rtype !== rtype) return false;
  return true;
}

/** Position of a round at `t`, linearly interpolated between samples. */
export function sampleAt(path, t) {
  if (!path || !path.length) return null;
  if (t <= path[0][0]) return path[0];
  const last = path[path.length - 1];
  if (t >= last[0]) return last;
  let low = 0;
  let high = path.length - 1;
  while (high - low > 1) {
    const mid = (low + high) >> 1;
    if (path[mid][0] <= t) low = mid;
    else high = mid;
  }
  const a = path[low];
  const b = path[high];
  const span = b[0] - a[0] || 1;
  const ratio = (t - a[0]) / span;
  return [
    t,
    a[1] + (b[1] - a[1]) * ratio,
    a[2] + (b[2] - a[2]) * ratio,
  ];
}

export class ReplayPlayer {
  constructor(canvas, options) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.transform = options.transform || { pos_x: 0, pos_y: 0, scale: 1 };
    this.rounds = options.rounds || [];
    this.side = options.side || null;
    this.rtype = options.rtype || null;
    this.speed = 1;
    this.time = 0;
    this.playing = options.autoplay !== false;
    this.onTick = options.onTick || null;

    this._radar = null;
    this._radarFailed = false;
    this._raf = null;
    this._lastFrame = 0;
    this._dpr = Math.min(window.devicePixelRatio || 1, 2);

    if (options.radar) this._loadRadar(options.radar);
    this._resize();
    this._loop = this._loop.bind(this);
    this._raf = requestAnimationFrame(this._loop);
  }

  get duration() {
    let end = 1;
    for (const round of this.rounds) {
      if (!matchesFilter(round, this.side, this.rtype)) continue;
      end = Math.max(end, roundEnd(round));
    }
    return Math.min(Math.max(end, 1), WINDOW_SECONDS);
  }

  get progress() {
    return Math.min(1, this.time / this.duration);
  }

  get activeRounds() {
    return this.rounds.filter((round) => matchesFilter(round, this.side, this.rtype)).length;
  }

  _loadRadar(url) {
    const image = new Image();
    image.decoding = 'async';
    image.onload = () => {
      this._radar = image;
      this._draw();
    };
    image.onerror = () => {
      this._radarFailed = true;
      this._draw();
    };
    image.src = url;
  }

  _resize() {
    const rect = this.canvas.getBoundingClientRect();
    const css = Math.max(160, Math.round(rect.width || 320));
    this.canvas.width = Math.round(css * this._dpr);
    this.canvas.height = Math.round(css * this._dpr);
    this._scale = this.canvas.width / RADAR_SIZE;
  }

  setFilter(side, rtype) {
    this.side = side || null;
    this.rtype = rtype || null;
    this.time = Math.min(this.time, this.duration);
    this._draw();
  }

  setSpeed(speed) {
    this.speed = speed;
  }

  resize() {
    this._resize();
    this._draw();
  }

  play() {
    this.playing = true;
  }

  pause() {
    this.playing = false;
  }

  toggle() {
    this.playing = !this.playing;
    return this.playing;
  }

  seek(seconds) {
    this.time = Math.max(0, Math.min(this.duration, seconds));
    this._draw();
  }

  seekRatio(ratio) {
    this.seek(this.duration * Math.max(0, Math.min(1, ratio)));
  }

  destroy() {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
  }

  _loop(timestamp) {
    const delta = this._lastFrame ? (timestamp - this._lastFrame) / 1000 : 0;
    this._lastFrame = timestamp;
    if (this.playing) {
      this.time += delta * this.speed;
      if (this.time > this.duration) this.time = 0; // loop, like the upstream player
      this._draw();
      if (this.onTick) this.onTick(this);
    }
    this._raf = requestAnimationFrame(this._loop);
  }

  _draw() {
    const ctx = this.ctx;
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.setTransform(this._scale, 0, 0, this._scale, 0, 0);

    this._drawBackground(ctx);

    for (const round of this.rounds) {
      if (!matchesFilter(round, this.side, this.rtype)) continue;
      this._drawRound(ctx, round);
    }
  }

  _drawBackground(ctx) {
    if (this._radar) {
      ctx.globalAlpha = 0.92;
      ctx.drawImage(this._radar, 0, 0, RADAR_SIZE, RADAR_SIZE);
      ctx.globalAlpha = 1;
      return;
    }
    ctx.fillStyle = '#141821';
    ctx.fillRect(0, 0, RADAR_SIZE, RADAR_SIZE);
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= RADAR_SIZE; i += 128) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i, RADAR_SIZE);
      ctx.moveTo(0, i);
      ctx.lineTo(RADAR_SIZE, i);
      ctx.stroke();
    }
    if (this._radarFailed) {
      ctx.fillStyle = 'rgba(255,255,255,0.35)';
      ctx.font = '28px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('缺少雷达图资源', RADAR_SIZE / 2, RADAR_SIZE / 2);
    }
  }

  _drawRound(ctx, round) {
    const color = SIDE_COLOR[round.side] || '#c9cfdd';
    const path = round.path || [];
    if (!path.length) return;

    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.34;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.beginPath();
    let started = false;
    for (const point of path) {
      if (point[0] > this.time) break;
      const [px, py] = gameToPixel(this.transform, point[1], point[2]);
      if (!started) {
        ctx.moveTo(px, py);
        started = true;
      } else {
        ctx.lineTo(px, py);
      }
    }
    if (started) ctx.stroke();
    ctx.globalAlpha = 1;

    this._drawGrenades(ctx, round, color);

    const position = sampleAt(path, this.time);
    if (!position) return;
    const [px, py] = gameToPixel(this.transform, position[1], position[2]);
    ctx.beginPath();
    ctx.arc(px, py, 7, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.lineWidth = 2.5;
    ctx.strokeStyle = 'rgba(8,10,14,0.85)';
    ctx.stroke();
  }

  _drawGrenades(ctx, round, sideColor) {
    for (const grenade of round.grenades || []) {
      if (grenade.throw_t > this.time) continue;
      const color = GRENADE_COLOR[grenade.type] || sideColor;
      const arc = grenade.arc || [];
      if (arc.length > 1) {
        ctx.globalAlpha = 0.75;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        let started = false;
        for (const point of arc) {
          if (point[0] > this.time) break;
          const [px, py] = gameToPixel(this.transform, point[1], point[2]);
          if (!started) {
            ctx.moveTo(px, py);
            started = true;
          } else {
            ctx.lineTo(px, py);
          }
        }
        if (started) ctx.stroke();
        ctx.globalAlpha = 1;
      }

      if (grenade.land && grenade.land_t <= this.time) {
        const [lx, ly] = gameToPixel(this.transform, grenade.land[0], grenade.land[1]);
        const active = !grenade.expire_t || grenade.expire_t >= this.time;
        ctx.globalAlpha = active ? 0.85 : 0.25;
        ctx.beginPath();
        ctx.arc(lx, ly, 9, 0, Math.PI * 2);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }
  }
}
