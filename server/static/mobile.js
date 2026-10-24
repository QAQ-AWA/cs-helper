import { ReplayPlayer } from './replay-core.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

let roomCode = (params.get('room') || '').toUpperCase();
let roomMode = 'multi';

const storeKeyFor = (code) => 'cs-helper-room-' + code;
const LAST_TAB_KEY = 'cs-helper-tab';

const state = {
  token: null,
  lastSeq: 0,
  ws: null,
  retry: 0,
  /** 连续「连不上」次数：用来判断 token 是不是已经失效。 */
  authFailures: 0,
  opened: false,
  match: null,
  profiles: [],
  mySide: '',
  paths: null,
  artifactId: null,
  replayCache: new Map(),
  renderer: null,
  currentSteamId: null,
  tab: 'roster',
};

/* ---------- 小工具 ---------- */

function escapeHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]),
  );
}
const escapeAttr = escapeHtml;

function fmt(value, digits = 2) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}
function num(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
/** 服务端给的是百分数（46.0），表格要 0-1 的小数。 */
function fraction(value) {
  const raw = num(value);
  if (raw === null) return null;
  return raw > 1 ? raw / 100 : raw;
}
function pct(value) {
  const raw = fraction(value);
  return raw === null ? '—' : `${Math.round(raw * 100)}%`;
}
function resultChips(raw) {
  if (typeof raw !== 'string') return '';
  const flags = raw.toUpperCase().split('').filter((c) => 'WLD'.includes(c)).slice(-5);
  if (!flags.length) return '—';
  return `<span class="wl">${flags
    .map((f) => `<span class="${f === 'W' ? 'w' : f === 'L' ? 'l' : 'd'}">${f}</span>`)
    .join('')}</span>`;
}

/* ---------- 连接 ---------- */

function setConn(kind, text) {
  $('dot').className = 'dot' + (kind === 'on' ? ' on' : kind === 'warn' ? ' warn' : '');
  $('hint').textContent = text;
}

function showErr(msg) {
  $('join-err').textContent = msg || '';
}

/** token 失效时唯一的正确动作：丢掉它，重新要昵称。 */
function resetAuth(reason) {
  state.token = null;
  state.opened = false;
  state.authFailures = 0;
  if (state.ws) {
    try {
      state.ws.onclose = null;
      state.ws.close();
    } catch (_) {
      /* ignore */
    }
    state.ws = null;
  }
  localStorage.removeItem(storeKeyFor(roomCode));
  setConn('warn', '需要重新进入');
  $('join').classList.remove('hidden');
  showErr(reason || '');
}

async function join() {
  const nickname = ($('nick').value || '').trim() || '队友';
  const btn = $('join-btn');
  btn.disabled = true;
  showErr('');
  try {
    const res = await fetch('/api/v1/room/join', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roomCode, nickname, deviceType: 'mobile' }),
    });
    const json = await res.json();
    if (json.code !== 0) throw new Error(json.message || '加入失败');
    state.token = json.data.token;
    state.authFailures = 0;
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
  state.opened = false;

  ws.onopen = () => {
    state.opened = true;
    state.retry = 0;
    state.authFailures = 0;
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
  ws.onclose = (event) => {
    const code = event && event.code;
    if (code === 4401) {
      resetAuth('房间已重置，请重新输入昵称');
      return;
    }
    // 握手被 403 挡掉时 onclose 只给 1006，看不出是 token 的问题。
    // 连续两次连不上就当 token 失效，别让页面永远停在「已断开」。
    if (!state.opened && ++state.authFailures >= 2) {
      resetAuth('登录状态已失效，请重新进入');
      return;
    }
    setConn('', '已断开');
    const delay = Math.min(15000, 800 * Math.pow(1.7, state.retry++));
    setTimeout(connect, delay + Math.random() * 400);
  };
  ws.onerror = () => setConn('warn', '连接异常');
}

/** 用 token 探一次快照：401/403 说明这个 token 已经不能用了。 */
async function tokenWorks(token) {
  try {
    const res = await fetch(`/api/v1/room/${encodeURIComponent(roomCode)}/snapshot`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.ok;
  } catch (_) {
    return true; // 网络问题不该把 token 判死
  }
}

function leaveRoom() {
  resetAuth('已退出，输入昵称可重新进入');
  state.match = null;
  state.profiles = [];
  renderRoster();
  renderAnalysis();
}

/* ---------- 页签 ---------- */

function setTab(tab, { remember = true } = {}) {
  state.tab = tab;
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === tab));
  document.querySelectorAll('[data-panel]').forEach((p) => p.classList.toggle('hidden', p.dataset.panel !== tab));
  if (remember) {
    try {
      sessionStorage.setItem(LAST_TAB_KEY, tab);
    } catch (_) {
      /* ignore */
    }
  }
  if (tab === 'paths' && state.paths) renderPaths(state.paths);
}

function markTab(tab) {
  const button = document.querySelector(`#tabs button[data-tab="${tab}"]`);
  if (!button) return;
  if (state.tab === tab) {
    button.classList.remove('fresh');
    return;
  }
  button.classList.add('fresh');
}

/* ---------- 事件分发 ---------- */

function handle(action, payload) {
  switch (action) {
    case 'ROOM_STATE_SYNC':
      if (typeof payload.latestSeq === 'number') {
        state.lastSeq = Math.max(state.lastSeq, payload.latestSeq);
      }
      renderMembers(payload.members || []);
      if (payload.profiles && payload.profiles.length) state.profiles = payload.profiles;
      if (payload.match) {
        applyMatch(payload.match);
        if (payload.match.postReport) renderPost(payload.match.postReport);
        if (payload.match.artifactId) loadPaths(payload.match.artifactId);
      }
      break;
    case 'ROOM_MEMBERS_CHANGED':
      renderMembers(payload.members || []);
      break;
    case 'MATCH_DETECTED':
      applyMatch(payload);
      if (payload.postReport) renderPost(payload.postReport);
      break;
    case 'POST_MATCH_READY':
      renderPost(payload);
      break;
    case 'PROFILE_READY':
      if (payload.players && payload.players.length) state.profiles = payload.players;
      applyMatch({ ...(state.match || {}), mapName: payload.mapName || state.match?.mapName, profileState: 'ready' });
      break;
    case 'TACTICAL_PATHS_READY':
      renderPaths(payload);
      break;
    case 'AI_STREAM_CHUNK':
      renderAiProgress(payload);
      break;
    case 'AI_REPORT_READY':
      applyMatch({ ...(state.match || {}), aiState: 'ready', aiText: payload.report, aiResult: payload.result || null });
      break;
    case 'AI_TACTICS_CHUNK':
      renderTacticsProgress(payload);
      break;
    case 'PATHS_REPORT_READY':
      if (payload.report) {
        state.match = { ...(state.match || {}), pathReport: payload.report };
        renderPathReport();
        markTab('paths');
      }
      break;
    case 'AI_TACTICS_READY':
      applyMatch({ ...(state.match || {}), tacticsState: 'ready', tacticsText: payload.report });
      break;
    case 'ROOM_ERROR':
      if (payload.stage === 'home') {
        $('season-source').classList.add('warn');
        $('season-source').textContent = payload.message || '赛季数据拉取失败';
      } else if (payload.stage === 'ai') {
        $('ai').dataset.error = payload.message || '分析失败';
        renderAnalysis();
      } else {
        setConn('warn', payload.message || '服务端异常');
        $('demo-status').textContent = payload.message || '';
      }
      break;
  }
}

function applyMatch(match) {
  state.match = { ...(state.match || {}), ...match };
  state.mySide = state.match.mySide || '';
  renderHeader();
  renderRoster();
  renderAnalysis();
  renderTactics();
  if (state.match.postReport) renderPost(state.match.postReport);
  if (state.match.artifactId && !state.paths) loadPaths(state.match.artifactId);
  else if (state.paths) renderPaths(state.paths);
}

/* ---------- 顶栏 ---------- */

function renderHeader() {
  const match = state.match || {};
  $('map').textContent = match.mapName && match.mapName !== 'de_unknown' ? match.mapName : '等待地图确认…';
  const seconds = match.countdownSeconds;
  $('countdown').textContent = typeof seconds === 'number' && seconds > 0 ? `准备 ${seconds}s` : '';
  renderSideLabel();
}

function renderMembers(members) {
  const box = $('members');
  if (!members.length) {
    box.innerHTML = '<span class="muted">暂无成员</span>';
    return;
  }
  const host = members.find((m) => m.deviceType === 'pc');
  box.innerHTML = members
    .map((m) => {
      const tag = host && m.id === host.id ? ' · 房主' : m.deviceType === 'pc' ? ' · 电脑' : '';
      return `<span class="chip ${m.isOnline ? '' : 'off'}">${escapeHtml(m.nickname)}${tag}</span>`;
    })
    .join('');
}

/* ---------- 阵容 ---------- */

const SIGNAL_LABEL = {
  carry: '强点',
  anchor: '支点',
  specialist: '专长',
  weakLink: '短板',
  volatile: '变量',
  watch: '关注',
};

/** 模型正文写的是「A 队 / B 队」，界面上要按我方视角说。 */
function persp(text) {
  if (!text) return '';
  const raw = String(text);
  if (!state.mySide) return raw;
  return raw
    .replace(/A\s*队/g, '我方')
    .replace(/B\s*队/g, '对方')
    .replace(/Team\s*A\b/gi, '我方')
    .replace(/Team\s*B\b/gi, '对方');
}

function sideName(side) {
  // 服务端约定：A = 我方（认出来时），否则 A = CT。
  if (!state.mySide) return side === 'A' ? 'A 队' : 'B 队';
  return side === 'A' ? '我方' : '对方';
}

function renderSideLabel() {
  const label = $('side-label');
  if (!state.mySide) {
    label.textContent = '我方未定 · 先选一下';
    label.style.color = 'var(--warn)';
  } else {
    const source = state.match?.mySideSource;
    const tag = source === 'library' ? 'ID 库' : source === 'explicit' ? '手动' : '';
    label.textContent = `我方 ${state.mySide.toUpperCase()}${tag ? ` · ${tag}` : ''}`;
    label.style.color = 'var(--fg-secondary)';
  }
}

/** 名册优先用服务端补齐的画像；没有就用上报里带的名单。 */
function rosterRows() {
  const byNick = new Map();
  (state.profiles || []).forEach((p) => p.nickname && byNick.set(p.nickname, p));
  const teams = state.match?.teams || {};
  const rows = [];
  ['ct', 't'].forEach((side) => {
    (teams[side] || []).forEach((player) => {
      const profile = byNick.get(player.nickname) || {};
      const stats = { ...(player.stats || {}), ...(profile.stats || {}) };
      rows.push({
        side,
        nickname: player.nickname || profile.nickname || 'Unknown',
        steamId: profile.steamId || player.steamId || '',
        avatar: profile.avatarUrl || player.avatarUrl || '',
        isSelf: Boolean(profile.isSelf),
        stats,
      });
    });
  });
  // 服务端画像里可能有上报里没有的人（换人/补录）。
  (state.profiles || []).forEach((p) => {
    if (!rows.some((row) => row.nickname === p.nickname)) {
      rows.push({
        side: p.team || 'ct',
        nickname: p.nickname || 'Unknown',
        steamId: p.steamId || '',
        avatar: p.avatarUrl || '',
        isSelf: Boolean(p.isSelf),
        stats: p.stats || {},
      });
    }
  });
  return rows;
}

function signalsBySteam() {
  const map = new Map();
  const signals = state.match?.aiResult?.playerSignals || [];
  signals.forEach((s) => s.steamId && map.set(String(s.steamId), s));
  return map;
}

function renderRoster() {
  const box = $('roster');
  const rows = rosterRows();
  if (!rows.length) {
    box.innerHTML = '<div class="card ai-empty">等待电脑端上报阵容…</div>';
    renderSeason();
    return;
  }
  const signals = signalsBySteam();
  // 服务端约定 A = 我方；没认出我方时 A = CT。别把 CT 固定写成「我方」。
  const tokenFor = (side) =>
    state.mySide ? (side === state.mySide ? 'A' : 'B') : side === 'ct' ? 'A' : 'B';
  const blocks = [
    { side: 'ct', label: 'CT' },
    { side: 't', label: 'T' },
  ].map((team) => {
    const token = tokenFor(team.side);
    const members = rows
      .filter((row) => row.side === team.side)
      .sort((a, b) => (num(b.stats.seasonRating) ?? 0) - (num(a.stats.seasonRating) ?? 0));
    const ratings = members.map((m) => num(m.stats.seasonRating)).filter((v) => v !== null);
    const avg = ratings.length ? ratings.reduce((s, v) => s + v, 0) / ratings.length : null;
    const title = state.mySide ? (token === 'A' ? '我方' : '对方') : token === 'A' ? 'A 队' : 'B 队';
    const body = members.length
      ? members.map((row) => rosterRow(row, signals)).join('')
      : '<div class="note" style="padding:10px 12px">暂无数据</div>';
    return `<section class="team-block">
      <header class="team-head">
        <span class="tag ${token === 'A' ? 'a' : 'b'}">${team.label} · ${title}</span>
        <span class="avg">${members.length} 人${avg !== null ? ` · 均 ${avg.toFixed(2)}` : ''}</span>
      </header>
      <div class="prows">${body}</div>
    </section>`;
  });
  box.innerHTML = blocks.join('');
  renderSeason();
}

/** 手机上用两行卡片而不是八列表格：不用横滑就能看全所有数字。 */
function rosterRow(row, signals) {
  const s = row.stats || {};
  const seasonRating = num(s.seasonRating) ?? num(s.rating);
  let recent = num(s.rating);
  // 两个来源相同时不重复展示：说明没拿到真正的赛季场均。
  if (recent !== null && recent === seasonRating) recent = null;
  const signal = row.steamId ? signals.get(String(row.steamId)) : null;
  const avatar = row.avatar
    ? `<img src="${escapeAttr(row.avatar)}" alt="" loading="lazy" onerror="this.remove()" />`
    : escapeHtml(row.nickname.slice(0, 1));
  const ratingClass =
    seasonRating === null ? '' : seasonRating >= 1.1 ? 'rating-good' : seasonRating < 0.95 ? 'rating-bad' : '';
  const sig = signal
    ? `<span class="sig-tag sig-${signal.kind}">${SIGNAL_LABEL[signal.kind] || '关注'}</span>`
    : '';
  const bits = [
    num(s.seasonAdr) === null ? 'ADR —' : `ADR ${Math.round(s.seasonAdr)}`,
    num(s.seasonRws) === null ? null : `RWS ${fmt(num(s.seasonRws), 1)}`,
    `K/D ${fmt(num(s.kd))}`,
    `爆头 ${pct(s.headshotRate)}`,
  ].filter(Boolean);
  return `<div class="prow">
    <span class="ava">${avatar}</span>
    <div class="p-main">
      <div class="p-top">
        <span class="name">${escapeHtml(row.nickname)}</span>
        ${row.isSelf ? '<span class="self-tag">我</span>' : ''}
        ${sig}
        <span class="rating ${ratingClass}">${fmt(seasonRating)}</span>
      </div>
      <div class="p-sub">
        <span>${bits.join(' · ')}</span>
        ${recent === null ? '' : `<span class="recent">近期 ${fmt(recent)}</span>`}
        ${resultChips(s.recentResults)}
      </div>
    </div>
  </div>`;
}

/** 5E 赛季数据是尽力而为：签名失效要说出来，不能装作有数据。 */
function renderSeason() {
  const box = $('season-source');
  const match = state.match || {};
  const status = match.homeState || '';
  box.classList.toggle('warn', status === 'signature' || status === 'failed');
  if (status === 'signature') box.textContent = match.homeError || '5E 签名失效，赛季数据这次没拿到';
  else if (status === 'failed') box.textContent = match.homeError || '赛季数据拉取失败，仅用本场数据';
  else if (status === 'partial') box.textContent = `赛季数据补全 ${match.homeCoverage || 0} 人，其余用本场数据`;
  else if (status === 'ready') box.textContent = `赛季数据已补全（${match.homeCoverage || 0} 人）`;
  else if (status === 'running') box.textContent = '正在拉取 5E 赛季数据…';
  else box.textContent = '';
  $('profile-source').textContent = state.profiles.length ? '数据来自队友电脑端上报' : '';
}

/* ---------- 分析 ---------- */

const DIM_LABEL = {
  strength: '整体实力',
  aim: '枪法',
  opening: '首杀',
  utility: '道具',
  clutch: '残局',
  map: '地图',
  form: '状态',
  party: '组排',
};

function renderAnalysis() {
  const box = $('ai');
  const match = state.match || {};
  const result = match.aiResult;
  const error = box.dataset.error;

  if (result) {
    delete box.dataset.error;
    box.innerHTML = analysisHtml(result);
    return;
  }
  if (error) {
    box.innerHTML = `<div class="card ai-empty">${escapeHtml(error)}</div>`;
    return;
  }
  if (match.aiText) {
    box.innerHTML = `<div class="card"><h3 class="card-title">AI 战术分析</h3><div class="md" id="ai-md"></div></div>`;
    renderMarkdown(match.aiText, $('ai-md'));
    return;
  }
  const waiting = match.aiWait || [];
  const label =
    match.aiState === 'running'
      ? 'AI 正在分析这局…'
      : waiting.length
        ? `${waiting.join(' · ')}，到位后自动生成`
        : match.aiState === 'waiting'
          ? '等地图确认，到位后自动生成'
          : '等待电脑端上报数据…';
  box.innerHTML = `<div class="card ai-empty">${escapeHtml(label)}</div>`;
}

function analysisHtml(result) {
  const probability = result.modelWinProbability || { A: 50, B: 50 };
  const winA = Math.round(probability.A ?? 50);
  const winB = 100 - winA;
  const verdict =
    result.predictedWinner === 'Even'
      ? '双方势均力敌'
      : result.predictedWinner === 'A' || result.predictedWinner === 'B'
        ? `${sideName(result.predictedWinner)}略占优势`
        : '暂难判断';

  const factors = (result.decisiveFactors || [])
    .map((factor) => {
      const adv = factor.advantage === 'A' ? 'a' : factor.advantage === 'B' ? 'b' : 'even';
      const advText = factor.advantage === 'Even' ? '持平' : sideName(factor.advantage);
      return `<article class="factor">
        <div class="factor-head">
          <span class="dim">${DIM_LABEL[factor.dimension] || '综合'}</span>
          <span class="adv ${adv}">${advText}</span>
        </div>
        <h4>${escapeHtml(persp(factor.title))}</h4>
        <p>${escapeHtml(persp(factor.summary))}</p>
      </article>`;
    })
    .join('');

  const signals = result.playerSignals || [];
  const positive = signals.filter((s) => ['carry', 'anchor', 'specialist'].includes(s.kind));
  const negative = signals.filter((s) => s.kind === 'weakLink');
  const volatile = signals.filter((s) => !['carry', 'anchor', 'specialist', 'weakLink'].includes(s.kind));
  const signalBlock = (list, tone) =>
    list.length
      ? `<div class="signal-group">${list
          .map(
            (signal) => `<article class="signal ${tone}">
              <span class="bar"></span>
              <div class="body">
                <div class="who">
                  <span>${escapeHtml(signal.nickname)}</span>
                  <span class="side ${signal.side === 'A' ? 'a' : 'b'}">${sideName(signal.side)}</span>
                  <span class="sig-tag sig-${signal.kind}">${SIGNAL_LABEL[signal.kind] || '关注'}</span>
                </div>
                <p class="why">${escapeHtml(persp(signal.title))}：${escapeHtml(persp(signal.summary))}</p>
              </div>
            </article>`,
          )
          .join('')}</div>`
      : '';

  const plan = (side) => {
    const block = (result.teamPlans || {})[side] || {};
    const wins = (block.winConditions || []).map((c) => `<li>${escapeHtml(persp(c.text))}</li>`).join('');
    const risks = (block.risks || []).map((c) => `<li>${escapeHtml(c.text)}</li>`).join('');
    if (!wins && !risks) return '';
    return `<div class="plan">
      <h4 class="${side === 'A' ? 'a' : 'b'}">${sideName(side)}</h4>
      ${wins ? `<div class="label">取胜条件</div><ul>${wins}</ul>` : ''}
      ${risks ? `<div class="label">主要隐患</div><ul>${risks}</ul>` : ''}
    </div>`;
  };

  const uncertainties = (result.uncertainties || []).length
    ? `<div class="uncertain"><h4>数据边界</h4><ul>${result.uncertainties
        .map((text) => `<li>${escapeHtml(persp(text))}</li>`)
        .join('')}</ul></div>`
    : '';

  return `
    <section class="hero">
      <div class="hero-top">
        <span class="verdict">${verdict}</span>
        <span class="pill">可信度 ${result.confidence ?? 0}</span>
        <span class="pill">覆盖 ${Math.round((result.dataCoverage ?? 0) * 100)}%</span>
      </div>
      <h2>${escapeHtml(persp(result.headline))}</h2>
      <div class="winbar">
        <div class="winbar-labels">
          <span class="a">${sideName('A')} <b>${winA}%</b></span>
          <span class="b"><b>${winB}%</b> ${sideName('B')}</span>
        </div>
        <div class="winbar-track"><span class="a" style="width:${winA}%"></span><span class="b" style="width:${winB}%"></span></div>
      </div>
    </section>
    ${factors ? `<h3 class="card-title">决定本局的因素</h3><div class="factors">${factors}</div>` : ''}
    ${signals.length ? `<h3 class="card-title">玩家信号</h3>${signalBlock(positive, 'pos')}${signalBlock(negative, 'neg')}${signalBlock(volatile, '')}` : ''}
    ${plan('A') || plan('B') ? `<h3 class="card-title">双方取胜路径</h3><div class="plans">${plan('A')}${plan('B')}</div>` : ''}
    ${uncertainties}
  `;
}

function renderAiProgress(payload) {
  markTab('analysis');
  const box = $('ai');
  if (box.querySelector('.hero')) return; // 已有完整结果就不覆盖
  if (payload.phase === 'thinking') {
    box.innerHTML = `<div class="card ai-empty">AI 正在推理对手数据…${payload.chars ? `（${payload.chars} 字）` : ''}</div>`;
  } else if (typeof payload.accumulated === 'string') {
    box.innerHTML = `<div class="card"><div class="md" id="ai-md"></div></div>`;
    renderMarkdown(payload.accumulated, $('ai-md'));
  } else {
    box.innerHTML = `<div class="card ai-empty">AI 正在生成报告…${payload.chars ? `（${payload.chars} 字）` : ''}</div>`;
  }
}

function renderTactics() {
  const text = state.match?.tacticsText;
  const card = $('tactics-card');
  if (!text) {
    card.classList.add('hidden');
    return;
  }
  card.classList.remove('hidden');
  renderMarkdown(text, $('tactics'));
}

function renderTacticsProgress(payload) {
  const card = $('tactics-card');
  card.classList.remove('hidden');
  if (payload.phase === 'thinking') {
    $('tactics').textContent = `AI 正在读对面的开局轨迹…${payload.chars ? `（${payload.chars} 字）` : ''}`;
  } else {
    renderMarkdown(payload.accumulated || '', $('tactics'));
  }
}

/** 极简 Markdown：模型只输出 ## 标题、**粗体** 和 - 列表。 */
function renderMarkdown(text, box) {
  if (!box) return;
  if (!text) {
    box.textContent = '';
    return;
  }
  box.innerHTML = escapeHtml(text)
    .replace(/^#{1,4}\s*(.+)$/gm, '<div class="ai-h">$1</div>')
    .replace(/^[-*]\s+(.+)$/gm, '<div class="ai-li">$1</div>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n{2,}/g, '<div class="ai-gap"></div>')
    .replace(/\n/g, '<br>');
}

/* ---------- 选阵营 ---------- */

function openSideSheet() {
  const teams = state.match?.teams || {};
  const names = (side) =>
    (teams[side] || [])
      .map((p) => p.nickname)
      .filter(Boolean)
      .slice(0, 5)
      .join('、') || '名单还没到';
  $('side-ct-names').textContent = names('ct');
  $('side-t-names').textContent = names('t');
  $('remember-side').classList.toggle('hidden', !state.mySide || state.match?.mySideSource === 'library');
  $('side-sheet').classList.remove('hidden');
}

function closeSideSheet() {
  $('side-sheet').classList.add('hidden');
}

async function chooseSide(side) {
  if (!roomCode || !state.token) return;
  const previous = state.mySide;
  state.mySide = side || '';
  renderSideLabel();
  renderRoster();
  renderAnalysis();
  closeSideSheet();
  try {
    const res = await fetch(`/api/v1/room/${roomCode}/analysis-side`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${state.token}` },
      // 「都看」必须压过 ID 库，否则会被自动判定立刻改回去。
      body: JSON.stringify({ mySide: side || null, all: !side }),
    });
    const json = await res.json();
    if (json.code !== 0) throw new Error(json.message || '切换失败');
    state.mySide = json.data.mySide || '';
    state.match = { ...(state.match || {}), mySide: json.data.mySide || null, mySideSource: json.data.mySideSource };
    renderSideLabel();
    renderRoster();
    renderAnalysis();
    $('demo-status').textContent = `分析目标：${json.data.targets} 人`;
  } catch (err) {
    state.mySide = previous;
    renderSideLabel();
    renderRoster();
    renderAnalysis();
    setConn('warn', String(err.message || err));
  }
}

async function rememberSide() {
  if (!roomCode || !state.token || !state.mySide) return;
  try {
    const res = await fetch(`/api/v1/identity/learn?roomCode=${roomCode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${state.token}` },
      body: JSON.stringify({ side: state.mySide }),
    });
    const json = await res.json();
    if (json.code !== 0) throw new Error(json.message || '保存失败');
    $('side-hint').textContent = `已记住 ${json.data.count} 个 ID，下一局自动判断`;
  } catch (err) {
    setConn('warn', String(err.message || err));
  }
}

/* ---------- 轨迹 ---------- */

/** 轨迹页顶部的 AI 走位解读：每个人怎么走、大概率在哪、怎么针对。 */
function renderPathReport() {
  const box = $('path-report');
  const report = state.match?.pathReport;
  if (!box) return;
  if (!report) {
    box.innerHTML = '';
    return;
  }
  const players = (report.players || [])
    .map(
      (item) => `<article class="signal">
        <span class="bar"></span>
        <div class="body">
          <div class="who">
            <span>${escapeHtml(item.nickname)}</span>
            ${item.side ? `<span class="side ${item.side === 'CT' ? 'a' : 'b'}">${escapeHtml(item.side)}</span>` : ''}
          </div>
          ${item.habit ? `<p class="why">${escapeHtml(item.habit)}</p>` : ''}
          ${item.likely ? `<p class="why"><span class="muted">大概率：</span>${escapeHtml(item.likely)}</p>` : ''}
          ${item.counter ? `<p class="why" style="color:var(--accent)"><span class="muted">针对：</span>${escapeHtml(item.counter)}</p>` : ''}
        </div>
      </article>`,
    )
    .join('');
  const counters = (report.counters || []).length
    ? `<div class="uncertain" style="background:var(--accent-soft);border-color:#c7d2fe">
         <h4 style="color:var(--accent)">整队对策</h4>
         <ul>${report.counters.map((line) => `<li style="color:var(--fg-secondary)">${escapeHtml(line)}</li>`).join('')}</ul>
       </div>`
    : '';
  box.innerHTML = `<div class="card">
    <div class="hero-top">
      <span class="verdict">开局走位解读</span>
      ${report.tempo ? `<span class="pill">${escapeHtml(report.tempo)}</span>` : ''}
      ${report.sitePreference ? `<span class="pill">${escapeHtml(report.sitePreference)}</span>` : ''}
    </div>
    ${report.summary ? `<h2 style="font-size:15px;margin:10px 0 0">${escapeHtml(report.summary)}</h2>` : ''}
    <div class="signal-group" style="margin-top:12px">${players}</div>
    ${counters ? `<div style="margin-top:12px">${counters}</div>` : ''}
  </div>`;
}

function renderPaths(payload) {
  state.paths = payload;
  state.artifactId = payload.artifactId;
  renderPathReport();
  const players = payload.players || [];
  const box = $('paths-list');
  $('demo-status').textContent = players.length
    ? `已解析 ${players.length} 人，点一个看他的开局走位`
    : state.match?.demoState === 'waiting'
      ? '等地图确认，确认后开始下载录像'
      : '这批对手没有可用的历史录像。';
  if (!players.length) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = players
    .map((p) => {
      const name = displayName(p);
      const mate = teammateFor(p);
      const avatar = mate && mate.avatarUrl
        ? `<span class="ava"><img src="${escapeAttr(mate.avatarUrl)}" alt="" loading="lazy" onerror="this.remove()" /></span>`
        : `<span class="ava">${escapeHtml(name.slice(0, 1))}</span>`;
      return `<button type="button" class="path-row" data-steam="${escapeAttr(p.steamId)}" data-name="${escapeAttr(name)}">
        ${avatar}
        <span class="name">${escapeHtml(name)}</span>
        <span class="muted">${p.rounds || 0} 回合</span>
        <span class="go">查看 ›</span>
      </button>`;
    })
    .join('');
  box.querySelectorAll('.path-row').forEach((button) => {
    button.addEventListener('click', () => openPlayer(button.dataset.steam, button.dataset.name));
  });
  markTab('paths');
}

function teammateFor(player) {
  const steamId = String(player.steamId || '');
  return (state.profiles || []).find(
    (p) => String(p.steamId || '') === steamId || (player.domain && p.platformUserId === player.domain),
  );
}

function displayName(player) {
  return player.nickname || player.username || teammateFor(player)?.nickname || String(player.steamId || '');
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

async function openPlayer(steamId, username) {
  if (!steamId) return;
  state.currentSteamId = steamId;
  state.artifactId = state.paths?.artifactId || state.artifactId;
  $('view-room').classList.add('hidden');
  $('view-player').classList.remove('hidden');
  $('p-name').textContent = username || steamId;
  $('p-stats').textContent = '加载轨迹…';
  $('p-rounds').textContent = '';
  $('progress-bar').style.width = '0%';

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
  const awp = Number.isFinite(stats.awp_rate) ? `${Math.round(stats.awp_rate)}%` : '—';
  $('p-stats').textContent = `该场 K/D ${fmt(stats.kd)} · AWP ${awp} · ${replay.round_count || 0} 回合`;
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
  $('progress-bar').style.width = '0%';
}

function syncPlayButton() {
  $('play').textContent = state.renderer && state.renderer.playing ? '暂停' : '播放';
}

/* ---------- 赛后 ---------- */

function renderPost(report) {
  const box = $('post');
  if (!report) {
    box.innerHTML = '<div class="card ai-empty">这局还没有赛后数据</div>';
    return;
  }
  const winner = report.winnerSide;
  const half = report.halfScores;
  const rows = (teamSide) =>
    (report.players || [])
      .filter((p) => p.teamSide === teamSide)
      .sort((a, b) => (b.rating || 0) - (a.rating || 0))
      .map(
        (p) => `<div class="post-row">
          <span>${escapeHtml(p.nickname || '')}${
            p.isMvp ? '<span class="badge mvp">MVP</span>' : ''
          }${p.isSvp ? '<span class="badge svp">SVP</span>' : ''}</span>
          <span class="num">${p.kill || 0}/${p.death || 0}/${p.assist || 0}</span>
          <span class="num">${fmt(p.rating)}</span>
          <span class="num">${Math.round(p.adr || 0)}</span>
        </div>`,
      )
      .join('');
  const cmp = report.comparison;
  const headline = cmp
    ? cmp.headline || (cmp.isCorrect === true ? 'AI 预测命中' : cmp.isCorrect === false ? 'AI 预测落空' : '')
    : '';

  box.innerHTML = `
    <div class="card">
      <div class="score"><b>${report.scoreA ?? 0} : ${report.scoreB ?? 0}</b>
        <span class="pill">${winner === 'Draw' ? '平局' : winner ? `${winner} 队胜` : ''}</span></div>
      <div class="note">${half ? `半场 ${half.fhA}:${half.fhB} · ${half.shA}:${half.shB}` : `${report.roundTotal || 0} 回合`}</div>
      ${headline ? `<div class="note">${escapeHtml(headline)}</div>` : ''}
    </div>
    <section class="post-team"><h4 class="a">A 队</h4>${rows(1) || '<div class="note" style="padding:10px 12px">—</div>'}</section>
    <section class="post-team"><h4 class="b">B 队</h4>${rows(2) || '<div class="note" style="padding:10px 12px">—</div>'}</section>
  `;
  markTab('post');
}

/* ---------- 交互绑定 ---------- */

$('tabs').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-tab]');
  if (!button) return;
  button.classList.remove('fresh');
  setTab(button.dataset.tab);
});

$('join-btn').addEventListener('click', join);
$('nick').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') join();
});
$('leave').addEventListener('click', leaveRoom);
$('pick-side').addEventListener('click', openSideSheet);
$('side-close').addEventListener('click', closeSideSheet);
$('side-all').addEventListener('click', () => chooseSide(null));
$('remember-side').addEventListener('click', rememberSide);
document.querySelectorAll('#side-sheet .side-option').forEach((button) => {
  button.addEventListener('click', () => chooseSide(button.dataset.side));
});

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

/* ---------- 启动 ---------- */

async function boot() {
  $('code').textContent = roomCode || '----';

  try {
    const res = await fetch('/api/v1/config');
    const json = await res.json();
    if (json.code === 0 && json.data) {
      roomMode = json.data.mode || 'multi';
      // 房间码不再由服务端下发（公网部署时那等于把门牌号贴在门外），
      // 只认链接里的 ?room=，也就是电脑端二维码带的那个。
      if (roomMode === 'single') {
        $('join-hint').textContent = '当前为单房间模式，输入昵称即可进入。';
      }
    }
  } catch (_) {
    /* 服务端不可达时仍允许手动房间码 */
  }

  if (!roomCode) {
    setConn('', '缺少房间码');
    showErr('请扫描电脑端二维码，或使用带 ?room=XXXXXX 的链接');
    $('join-btn').disabled = true;
    return;
  }

  renderRoster();
  renderAnalysis();
  // 没有赛后数据时也要有一句话，别让「赛后」页看起来是坏的。
  renderPost(null);

  const savedTab = sessionStorage.getItem(LAST_TAB_KEY);
  setTab(savedTab && ['roster', 'analysis', 'paths', 'post'].includes(savedTab) ? savedTab : 'roster', {
    remember: false,
  });

  const saved = localStorage.getItem(storeKeyFor(roomCode));
  if (saved) {
    // 先探一下这个 token 还能不能用：不能就当场退回登录，别让页面停在「已断开」。
    if (await tokenWorks(saved)) {
      state.token = saved;
      $('join').classList.add('hidden');
      connect();
    } else {
      localStorage.removeItem(storeKeyFor(roomCode));
      showErr('上次的登录状态已失效，重新输入昵称即可');
    }
  }

  // 老版本注册过 Service Worker，会把页面外壳缓存住（只有无痕窗口看到新数据）。
  // 这个工具不需要离线能力，直接注销并清掉缓存。
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker
      .getRegistrations()
      .then((regs) => Promise.all(regs.map((reg) => reg.unregister())))
      .then(() => (window.caches ? caches.keys() : []))
      .then((keys) => (window.caches ? Promise.all(keys.map((key) => caches.delete(key))) : []))
      .catch(() => {});
  }
}

boot();
