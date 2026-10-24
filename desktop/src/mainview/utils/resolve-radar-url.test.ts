import { describe, expect, it } from 'vitest';

import { resolveRadarUrl } from './resolve-radar-url';

describe('resolveRadarUrl', () => {
  it('resolves the engine relative path against the relay', () => {
    expect(resolveRadarUrl('/maps/de_dust2/radar.png', 'http://192.168.3.46:8787')).toBe(
      'http://192.168.3.46:8787/maps/de_dust2/radar.png',
    );
  });

  it('tolerates a trailing slash on the base url', () => {
    expect(resolveRadarUrl('/maps/de_mirage/radar.png', 'http://127.0.0.1:8787/')).toBe(
      'http://127.0.0.1:8787/maps/de_mirage/radar.png',
    );
  });

  it('keeps an absolute url untouched', () => {
    expect(resolveRadarUrl('https://cdn.example.com/r.png', 'http://127.0.0.1:8787')).toBe(
      'https://cdn.example.com/r.png',
    );
  });

  it('returns undefined when the artifact has no radar', () => {
    expect(resolveRadarUrl(null, 'http://127.0.0.1:8787')).toBeUndefined();
    expect(resolveRadarUrl('  ', 'http://127.0.0.1:8787')).toBeUndefined();
  });

  it('falls back to the raw path when there is no relay url', () => {
    expect(resolveRadarUrl('/maps/de_dust2/radar.png', '')).toBe('/maps/de_dust2/radar.png');
  });
});
