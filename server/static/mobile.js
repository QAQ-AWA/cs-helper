import { ReplayPlayer } from './replay-core.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

let roomCode = (params.get('room') || '').toUpperCase();
let roomMode = 'multi';

const storeKeyFor = (code) => 'cs-helper-room-' + code;
const state = {
  token: null,
  lastSeq: 0,
  ws: null,
  retry: 0,
  match: null,
  paths: null,
  artifactId: null,
  replayCache: new Map(),
  renderer: null,
  currentSteamId: null,
};

/* ---------- connection ---------- */

function setConn(kind, text) {
  $('dot').className = 'dot' + (kind === 'on' ? ' on' : kind === 'warn' ? ' warn' : '');
  $('hint').textContent = text;
}

function showErr(msg) {
  $('join-err').textContent = msg;
}

async function join() {
  const nickname = ($('nick').value || '').trim() || '队友';
  const btn = $('join-btn');
  btn.disabled = true;
  try {
    const res = await fetch('/api/v1/room/join', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roomCode, nickname, deviceType: 'mobile' }),
    });
    const json = await res.json();
    if (json.code !== 0) throw new Error(json.message || '加入失败');
    state.token = json.data.token;
    localStorage.setItem(storeKeyFor(json.data.roomCode || roomCode), state.token);
    $('join').classList.add('hidden');
    connect();
  } catch (err) {
    showErr(err.message || String(err));
  } finally {
    btn.disabled = false;
  }
}

function connect() {
  if (!state.token) {
    $('join').classList.remove('hidden');
    return;
  }
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  setConn('warn', '连接中…');
  const ws = new WebSocket(
    `${proto}://${location.host}/ws?token=${encodeURIComponent(state.token)}&lastSeq=${state.lastSeq}`,
  );
  state.ws = ws;

  ws.onopen = () => {
    state.retry = 0;
    setConn('on', '已连接');
  };
  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg.action !== 'ROOM_STATE_SYNC' && typeof msg.seq === 'number') {
      state.lastSeq = Math.max(state.lastSeq, msg.seq);
    }
    handle(msg.action, msg.payload || {});
  };
  ws.onclose = () => {
    setConn('', '已断开');
    const delay = Math.min(15000, 800 * Math.pow(1.7, state.retry++));
    setTimeout(connect, delay + Math.random() * 400);
  };
  ws.onerror = () => setConn('warn', '连接异常');
}

function handle(action, payload) {
  switch (action) {
    case 'ROOM_STATE_SYNC':
      if (typeof payload.latestSeq === 'number') {
        state.lastSeq = Math.max(state.lastSeq, payload.latestSeq);
      }
      renderMembers(payload.members || []);
      if (payload.match) {
        renderMatch(payload.match);
        if (payload.match.aiText) {
          $('ai-card').classList.remove('hidden');
          $('ai').textContent = payload.match.aiText;
        }
        if (payload.match.artifactId && !state.paths) loadPaths(payload.match.artifactId);
      }
      break;
    case 'ROOM_MEMBERS_CHANGED':
      renderMembers(payload.members || []);
      break;
    case 'MATCH_DETECTED':
      renderMatch(payload);
      if (payload.aiText) {
        $('ai-card').classList.remove('hidden');
        $('ai').textContent = payload.aiText;
      }
      break;
    case 'PROFILE_READY':
      renderMatch(
        { ...(state.match || {}), mapName: payload.mapName || state.match?.mapName, profileState: 'ready' },
        payload,
      );
      break;
    case 'TACTICAL_PATHS_READY':
      renderPaths(payload);
      break;
    case 'AI_STREAM_CHUNK':
      $('ai-card').classList.remove('hidden');
      $('ai').textContent = payload.accumulated || '';
      break;
    case 'AI_REPORT_READY':
      $('ai-card').classList.remove('hidden');
      if (typeof payload.report === 'string') $('ai').textContent = payload.report;
      break;
    case 'ROOM_ERROR':
      setConn('warn', payload.message || '服务端异常');
      $('demo-status').textContent = payload.message || '';
      break;
  }
}

/* ---------- room view ---------- */

function renderMembers(members) {
  const box = $('members');
  if (!members.length) {
    box.innerHTML = '<span class="muted">暂无</span>';
    return;
  }
  box.innerHTML = members
    .map(
      (m) =>
        `<span class="chip ${m.isOnline ? '' : 'off'}">${escapeHtml(m.nickname)}${
          m.deviceType === 'pc' ? ' · 房主' : ''
        }</span>`,
    )
    .join('');
}

function renderMatch(match, profile) {
  state.match = match;
  $('map').textContent = match.mapName || '未知地图';
  $('countdown').textContent =
    typeof match.countdownSeconds === 'number' ? `准备 ${match.countdownSeconds}s` : match.phase || '';

  const players = (profile && profile.players) || state.profilePlayers || collectPlayers(match);
  if (!players.length) return;
  $('teams-card').classList.remove('hidden');
  $('team-ct').innerHTML =
    players.filter((p) => p.team === 'ct').map(playerRow).join('') || '<div class="muted">—</div>';
  $('team-t').innerHTML =
    players.filter((p) => p.team === 't').map(playerRow).join('') || '<div class="muted">—</div>';
  if (profile) {
    state.profilePlayers = players;
    $('profile-source').textContent = '数据来源：电脑端上报，服务端待补全';
  }
}

function collectPlayers(match) {
  const teams = match.teams || {};
  return ['ct', 't'].flatMap((side) => (teams[side] || []).map((p) => ({ ...p, team: side })));
}

function playerRow(p) {
  const initial = escapeHtml((p.nickname || '?').slice(0, 1));
  const avatar = p.avatarUrl
    ? `<img src="${escapeAttr(p.avatarUrl)}" alt="" loading="lazy" onerror="this.remove()" />`
    : initial;
  const s = p.stats || {};
  const rating = s.rating != null ? Number(s.rating).toFixed(2) : '—';
  const kd = s.kd != null ? Number(s.kd).toFixed(2) : '—';
  return `<div class="player">
    <div class="ava">${avatar}</div>
    <div class="pname">${escapeHtml(p.nickname || 'Unknown')}${p.isSelf ? '<span class="self">我</span>' : ''}</div>
    <div class="stat">${rating}<br>K/D ${kd}</div>
  </div>`;
}

/* ---------- paths ---------- */

function renderPaths(payload) {
  state.paths = payload;
  state.artifactId = payload.artifactId;
  const players = payload.players || [];
  $('demo-status').textContent = players.length
    ? `轨迹已就绪：${players.length} 人`
    : '未取到可用录像';

  const box = $('paths-list');
  if (!players.length) {
    $('paths-card').classList.remove('hidden');
    box.innerHTML = '<div class="muted">这批对手没有可用的历史录像。</div>';
    return;
  }
  $('paths-card').classList.remove('hidden');
  box.innerHTML = players
    .map(
      (p) => `<button class="path-row" data-steam="${escapeAttr(p.steamId)}" data-name="${escapeAttr(
        p.username || '',
      )}">
        <span class="name">${escapeHtml(p.username || p.steamId)}</span>
        <span class="muted">${p.rounds || 0} 回合</span>
        <span class="go">查看 ›</span>
      </button>`,
    )
    .join('');
  box.querySelectorAll('.path-row').forEach((button) => {
    button.addEventListener('click', () =>
      openPlayer(button.dataset.steam, button.dataset.name),
    );
  });
}

async function loadPaths(artifactId) {
  try {
    const res = await fetch(`/api/v1/artifacts/${artifactId}`, {
      headers: { Authorization: `Bearer ${state.token}` },
    });
    const json = await res.json();
    if (json.code !== 0) return;
    renderPaths({ ...json.data, artifactId });
  } catch (_) {
    /* 索引拉取失败不阻塞房间视图 */
  }
}

/* ---------- player view ---------- */

async function openPlayer(steamId, username) {
  if (!steamId) return;
  state.currentSteamId = steamId;
  state.artifactId = state.paths?.artifactId || state.artifactId;
  $('view-room').classList.add('hidden');
  $('view-player').classList.remove('hidden');
  $('back').classList.remove('hidden');
  $('p-name').textContent = username || steamId;
  $('p-stats').textContent = '加载轨迹…';
  $('p-rounds').textContent = '';

  let replay = state.replayCache.get(steamId);
  if (!replay) {
    try {
      const res = await fetch(`/api/v1/artifacts/${state.artifactId}/players/${steamId}`, {
        headers: { Authorization: `Bearer ${state.token}` },
      });
      const json = await res.json();
      if (json.code !== 0) throw new Error(json.message || '轨迹不可用');
      replay = json.data.replay;
      state.replayCache.set(steamId, replay);
    } catch (err) {
      $('p-stats').textContent = err.message || '轨迹加载失败';
      return;
    }
  }

  mountReplay(replay);
}

function mountReplay(replay) {
  if (state.renderer) {
    state.renderer.destroy();
    state.renderer = null;
  }
  const stats = replay.combat_stats || {};
  $('p-stats').textContent = `K/D ${fmt(stats.kd)} · AWP ${fmt(stats.awp_rate)}% · ${replay.round_count || 0} 回合`;
  $('p-rounds').textContent = `${(replay.rounds || []).length} 段路径`;

  state.renderer = new ReplayPlayer($('replay'), {
    radar: replay.radar,
    transform: replay.transform,
    rounds: replay.rounds || [],
    onTick: (player) => {
      $('progress-bar').style.width = `${(player.progress * 100).toFixed(1)}%`;
    },
  });
  state.renderer.setSpeed(Number(document.querySelector('#speed .on')?.dataset.speed || 2));
  syncPlayButton();
}

function closePlayer() {
  if (state.renderer) {
    state.renderer.destroy();
    state.renderer = null;
  }
  state.currentSteamId = null;
  $('view-player').classList.add('hidden');
  $('view-room').classList.remove('hidden');
  $('back').classList.add('hidden');
}

function fmt(value) {
  return typeof value === 'number' ? value.toFixed(2) : '—';
}

function syncPlayButton() {
  const player = state.renderer;
  $('play').textContent = player && player.playing ? '暂停' : '播放';
}

/* ---------- controls ---------- */

$('play').addEventListener('click', () => {
  if (!state.renderer) return;
  state.renderer.toggle();
  syncPlayButton();
});

document.querySelectorAll('#speed button').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('#speed button').forEach((b) => b.classList.remove('on'));
    button.classList.add('on');
    if (state.renderer) state.renderer.setSpeed(Number(button.dataset.speed));
  });
});

document.querySelectorAll('#side button').forEach((button) => {
  button.addEventListener('click', () => {
    document.querySelectorAll('#side button').forEach((b) => b.classList.remove('on'));
    button.classList.add('on');
    if (state.renderer) state.renderer.setFilter(button.dataset.side || null, null);
  });
});

$('progress').addEventListener('pointerdown', (event) => {
  if (!state.renderer) return;
  const rect = $('progress').getBoundingClientRect();
  state.renderer.seekRatio((event.clientX - rect.left) / rect.width);
  $('progress-bar').style.width = `${(state.renderer.progress * 100).toFixed(1)}%`;
});

$('back').addEventListener('click', closePlayer);
window.addEventListener('resize', () => state.renderer && state.renderer.resize());

/* ---------- boot ---------- */

function escapeHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]),
  );
}
function escapeAttr(value) {
  return escapeHtml(value);
}

$('code').textContent = roomCode || '----';
$('join-btn').addEventListener('click', join);
$('nick').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') join();
});

async function boot() {
  try {
    const res = await fetch('/api/v1/config');
    const json = await res.json();
    if (json.code === 0 && json.data) {
      roomMode = json.data.mode || 'multi';
      if (!roomCode && json.data.roomCode) roomCode = json.data.roomCode;
      if (roomMode === 'single') {
        $('join-hint').textContent = '当前为单房间模式，输入昵称即可进入。';
      }
    }
  } catch (_) {
    /* 服务端不可达时仍允许手动房间码 */
  }

  $('code').textContent = roomCode || '----';
  if (!roomCode) {
    setConn('', '缺少房间码');
    showErr('请扫描电脑端二维码，或使用带 ?room=XXXXXX 的链接');
    $('join-btn').disabled = true;
    return;
  }

  const saved = localStorage.getItem(storeKeyFor(roomCode));
  if (saved) {
    state.token = saved;
    $('join').classList.add('hidden');
    connect();
  }

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
}

boot();
