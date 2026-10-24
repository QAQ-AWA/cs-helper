import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import '../core/format.dart';
import '../models/analysis.dart';
import '../models/match.dart';
import '../models/player.dart';
import '../models/replay.dart';
import '../services/api_client.dart';
import '../services/settings_store.dart';

enum ConnState { idle, connecting, connected, disconnected }

/// 一个房间的全部状态：连接、快照、事件、轨迹缓存。
class RoomController extends ChangeNotifier {
  RoomController({required this.api, required this.store});

  final ApiClient api;
  final SettingsStore store;

  String serverUrl = '';
  String roomCode = '';
  String nickname = '';
  String? token;
  ServerConfig? serverConfig;

  bool booting = true;
  bool joining = false;
  String? joinError;
  String? probeMessage;

  ConnState conn = ConnState.idle;
  String connHint = '未连接';

  List<Member> members = <Member>[];
  List<PlayerInfo> profiles = <PlayerInfo>[];
  MatchSession? match;
  String mySide = '';

  String? artifactId;
  List<PathPlayer> pathPlayers = <PathPlayer>[];
  bool pathsLoading = false;
  String? pathsError;

  String? aiError;
  String? aiProgress;
  String? aiPreview;
  bool aiStreaming = false;
  String? tacticsProgress;
  String? seasonError;
  String? demoMessage;
  String? identityMessage;

  int lastSeq = 0;
  int activeTab = 0;
  final Set<int> freshTabs = <int>{};

  Map<String, dynamic>? _matchRaw;
  final Map<String, ReplayBundle> _replays = <String, ReplayBundle>{};

  WebSocket? _socket;
  Timer? _retryTimer;
  int _retry = 0;
  int _authFailures = 0;
  bool _opened = false;
  bool _disposed = false;
  int _generation = 0;

  bool get hasToken => token != null && token!.isNotEmpty;

  bool get hasPaths => pathPlayers.isNotEmpty;

  String get sideText {
    if (mySide.isEmpty) return '我方未定 · 先选一下';
    final source = match?.mySideSource;
    final tag = source == 'library' ? 'ID 库' : source == 'explicit' ? '手动' : '';
    return '我方 ${mySide.toUpperCase()}${tag.isEmpty ? '' : ' · $tag'}';
  }

  List<RosterRow> get rosterRows {
    final byNickname = <String, PlayerInfo>{};
    for (final profile in profiles) {
      if (profile.nickname.isNotEmpty) byNickname[profile.nickname] = profile;
    }
    final rows = <RosterRow>[];
    final teams = match?.teams ?? TeamPayload.empty;
    for (final side in const <String>['ct', 't']) {
      for (final player in teams.forSide(side)) {
        final profile = byNickname[player.nickname];
        rows.add(
          RosterRow(
            side: side,
            player: player,
            profile: profile,
            stats: player.stats.mergedWith(profile?.stats),
          ),
        );
      }
    }
    // 服务端画像里可能有上报名单没有的人（换人 / 补录）。
    for (final profile in profiles) {
      if (rows.any((row) => row.nickname == profile.nickname)) continue;
      rows.add(
        RosterRow(
          side: profile.team ?? 'ct',
          player: profile,
          profile: profile,
          stats: profile.stats,
        ),
      );
    }
    return rows;
  }

  Map<String, PlayerSignal> get signalsBySteam {
    final map = <String, PlayerSignal>{};
    for (final signal in match?.aiResult?.signals ?? const <PlayerSignal>[]) {
      if (signal.steamId.isNotEmpty) map[signal.steamId] = signal;
    }
    return map;
  }

  String resolveAsset(String path) => api.absoluteUrl(serverUrl, path);

  // -- 启动 ------------------------------------------------------------

  Future<void> boot() async {
    final saved = await store.load();
    serverUrl = normalizeServer(saved.serverUrl);
    roomCode = saved.roomCode;
    nickname = saved.nickname;

    if (serverUrl.isNotEmpty) {
      serverConfig = await _tryConfig(serverUrl);
      if (roomCode.isEmpty) roomCode = serverConfig?.roomCode ?? '';
    }

    if (serverUrl.isNotEmpty && roomCode.isNotEmpty) {
      final savedToken = await store.tokenFor(serverUrl, roomCode);
      if (savedToken != null && savedToken.isNotEmpty) {
        token = savedToken;
        try {
          final snapshot = await api.snapshot(serverUrl, roomCode, savedToken);
          _applySnapshot(snapshot);
          booting = false;
          _safeNotify();
          await connect();
          return;
        } on ApiException catch (error) {
          if (error.isAuth) {
            await store.clearToken(serverUrl, roomCode);
            token = null;
            joinError = '上次的登录状态已失效，重新输入昵称即可';
          } else {
            // 网络问题不该把 token 判死：先进房间，靠 WS 重连拿快照。
            booting = false;
            _safeNotify();
            await connect();
            return;
          }
        } catch (_) {
          token = null;
        }
      }
    }

    booting = false;
    _safeNotify();
  }

  Future<ServerConfig?> _tryConfig(String server) async {
    try {
      return await api.fetchConfig(server);
    } catch (_) {
      return null;
    }
  }

  // -- 加入 / 退出 ------------------------------------------------------

  Future<void> joinRoom({
    required String server,
    required String room,
    required String nick,
  }) async {
    final normalized = normalizeServer(server);
    if (normalized.isEmpty) {
      joinError = '请填写电脑端的服务端地址';
      _safeNotify();
      return;
    }

    joining = true;
    joinError = null;
    _safeNotify();

    try {
      final config = await _tryConfig(normalized);
      if (config != null) serverConfig = config;
      final effectiveRoom = room.trim().isNotEmpty
          ? room.trim().toUpperCase()
          : (serverConfig?.roomCode ?? '');
      if (effectiveRoom.isEmpty) {
        throw ApiException('请填写房间码（电脑端设置里能看到）');
      }

      final displayName = nick.trim().isEmpty ? '队友' : nick.trim();
      final result = await api.join(
        normalized,
        roomCode: effectiveRoom,
        nickname: displayName,
      );

      serverUrl = normalized;
      roomCode = result.roomCode.isNotEmpty ? result.roomCode : effectiveRoom;
      nickname = displayName;
      token = result.token;
      await store.saveConnection(
        serverUrl: serverUrl,
        roomCode: roomCode,
        nickname: nickname,
      );
      await store.saveToken(serverUrl, roomCode, result.token);

      joining = false;
      joinError = null;
      _resetMatchState();
      _safeNotify();
      await connect();
    } on ApiException catch (error) {
      joining = false;
      joinError = error.message;
      _safeNotify();
    } catch (error) {
      joining = false;
      joinError = '进入房间失败：$error';
      _safeNotify();
    }
  }

  Future<String> probeServer(String server) async {
    final normalized = normalizeServer(server);
    if (normalized.isEmpty) throw ApiException('先填写服务端地址');
    final config = await api.fetchConfig(normalized);
    serverConfig = config;
    _safeNotify();
    final mode = config.isSingleRoom
        ? '单房间模式（${config.roomCode ?? '—'}）'
        : '多房间模式';
    final ai = config.aiEnabled ? 'AI 已开启' : 'AI 未配置 key';
    final demo = config.demoEnabled ? '轨迹已开启' : '轨迹未开启';
    return '$mode · $ai · $demo';
  }

  Future<void> leaveRoom() async {
    await resetAuth('已退出，输入昵称可重新进入');
    _resetMatchState();
    _safeNotify();
  }

  Future<void> updateConnection({
    required String server,
    required String room,
    required String nick,
  }) async {
    await store.clearToken(serverUrl, roomCode);
    await resetAuth('连接已切换，请重新进入');
    await joinRoom(server: server, room: room, nick: nick);
  }

  Future<void> resetAuth(String reason) async {
    _generation++;
    _retryTimer?.cancel();
    _retryTimer = null;
    final socket = _socket;
    _socket = null;
    if (socket != null) {
      try {
        await socket.close();
      } catch (_) {
        // 已经断了就算了。
      }
    }
    token = null;
    _opened = false;
    _authFailures = 0;
    _retry = 0;
    conn = ConnState.idle;
    connHint = '需要重新进入';
    joinError = reason;
    if (serverUrl.isNotEmpty && roomCode.isNotEmpty) {
      await store.clearToken(serverUrl, roomCode);
    }
    _safeNotify();
  }

  // -- WebSocket -------------------------------------------------------

  /// 回到前台时调用：socket 已经死了就立刻重连，不等指数退避。
  void ensureConnected() {
    if (!hasToken) return;
    if (conn == ConnState.connected && _socket != null) return;
    _retry = 0;
    unawaited(connect());
  }

  Future<void> connect() async {
    final currentToken = token;
    if (currentToken == null || currentToken.isEmpty) return;

    _retryTimer?.cancel();
    _retryTimer = null;
    final generation = ++_generation;
    final previous = _socket;
    _socket = null;
    if (previous != null) {
      try {
        await previous.close();
      } catch (_) {
        // ignore
      }
    }
    if (_disposed || generation != _generation) return;

    _opened = false;
    conn = ConnState.connecting;
    connHint = '连接中…';
    _safeNotify();

    try {
      final socket = await WebSocket.connect(
        api.wsUrl(serverUrl, currentToken, lastSeq),
      );
      if (_disposed || generation != _generation) {
        await socket.close();
        return;
      }
      _socket = socket;
      _opened = true;
      _retry = 0;
      _authFailures = 0;
      conn = ConnState.connected;
      connHint = '已连接';
      _safeNotify();
      socket.pingInterval = const Duration(seconds: 20);
      socket.listen(
        _onSocketData,
        onDone: () => _onSocketClosed(generation, socket.closeCode),
        onError: (Object _) {},
        cancelOnError: false,
      );
    } catch (_) {
      if (generation == _generation) _onSocketClosed(generation, null);
    }
  }

  void _onSocketData(dynamic raw) {
    if (raw is! String) return;
    Map<String, dynamic> message;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;
      message = decoded.cast<String, dynamic>();
    } catch (_) {
      return;
    }

    final action = asString(message['action']) ?? '';
    if (action.isEmpty) return;
    final payload = asMap(message['payload']);
    final seq = asInt(message['seq']);
    if (action != 'ROOM_STATE_SYNC' && seq != null) {
      lastSeq = math.max(lastSeq, seq);
    }
    _handle(action, payload);
  }

  void _onSocketClosed(int generation, int? code) {
    if (generation != _generation || _disposed) return;
    _socket = null;
    if (code == 4401) {
      unawaited(resetAuth('房间已重置，请重新输入昵称'));
      return;
    }
    // 握手被 403 挡掉时只会给 1006，看不出是 token 的问题。
    // 连续两次连不上就当 token 失效，别让界面永远停在「已断开」。
    if (!_opened && ++_authFailures >= 2) {
      unawaited(resetAuth('登录状态已失效，请重新进入'));
      return;
    }
    conn = ConnState.disconnected;
    connHint = '已断开';
    _safeNotify();
    final delay = math.min(15000, (800 * math.pow(1.7, _retry++)).round());
    _retryTimer = Timer(Duration(milliseconds: delay), () => unawaited(connect()));
  }

  // -- 事件 ------------------------------------------------------------

  void _handle(String action, Map<String, dynamic> payload) {
    switch (action) {
      case 'ROOM_STATE_SYNC':
        _applySnapshot(payload);
        break;
      case 'ROOM_MEMBERS_CHANGED':
        members = asMapList(payload['members']).map(Member.fromJson).toList();
        _safeNotify();
        break;
      case 'MATCH_DETECTED':
        _applyMatchPayload(payload, replace: true);
        break;
      case 'PROFILE_READY':
        final players = asMapList(payload['players']);
        if (players.isNotEmpty) {
          profiles = players.map(PlayerInfo.fromJson).toList();
        }
        _applyMatchPayload(<String, dynamic>{'profileState': 'ready'});
        break;
      case 'TACTICAL_PATHS_READY':
        artifactId = asString(payload['artifactId']) ?? artifactId;
        pathPlayers = asMapList(payload['players']).map(PathPlayer.fromJson).toList();
        pathsLoading = false;
        pathsError = null;
        demoMessage = pathPlayers.isEmpty
            ? '这批对手没有可用的历史录像。'
            : '已解析 ${pathPlayers.length} 人，点一个看他的开局走位';
        freshTabs.add(2);
        _safeNotify();
        break;
      case 'JOB_PROGRESS':
        _handleJobProgress(payload);
        break;
      case 'AI_STREAM_CHUNK':
        _handleAiChunk(payload);
        break;
      case 'AI_REPORT_READY':
        aiError = null;
        aiProgress = null;
        aiPreview = null;
        aiStreaming = false;
        final patch = <String, dynamic>{
          'aiState': 'ready',
          'aiText': payload['report'],
        };
        if (payload['result'] is Map) patch['aiResult'] = payload['result'];
        _applyMatchPayload(patch);
        freshTabs.add(1);
        _safeNotify();
        break;
      case 'AI_TACTICS_CHUNK':
        final chars = asInt(payload['chars']) ?? 0;
        tacticsProgress = payload['phase'] == 'thinking'
            ? 'AI 正在读对面的开局轨迹…${chars > 0 ? '（$chars 字）' : ''}'
            : 'AI 正在写开局预判…${chars > 0 ? '（$chars 字）' : ''}';
        freshTabs.add(1);
        _safeNotify();
        break;
      case 'AI_TACTICS_READY':
        tacticsProgress = null;
        _applyMatchPayload(<String, dynamic>{
          'tacticsState': 'ready',
          'tacticsText': payload['report'],
        });
        freshTabs.add(1);
        _safeNotify();
        break;
      case 'POST_MATCH_READY':
        final report = Map<String, dynamic>.of(payload)..remove('sessionId');
        _applyMatchPayload(<String, dynamic>{'postReport': report});
        freshTabs.add(3);
        _safeNotify();
        break;
      case 'ROOM_ERROR':
        _handleRoomError(payload);
        break;
      default:
        break;
    }
  }

  void _handleAiChunk(Map<String, dynamic> payload) {
    final chars = asInt(payload['chars']) ?? 0;
    aiError = null;
    aiStreaming = true;
    final accumulated = asString(payload['accumulated']);
    if (accumulated != null) {
      aiPreview = accumulated;
      aiProgress = null;
    } else if (payload['phase'] == 'thinking') {
      aiProgress = 'AI 正在推理对手数据…${chars > 0 ? '（$chars 字）' : ''}';
    } else {
      aiProgress = 'AI 正在生成报告…${chars > 0 ? '（$chars 字）' : ''}';
    }
    freshTabs.add(1);
    _safeNotify();
  }

  void _handleJobProgress(Map<String, dynamic> payload) {
    if (asString(payload['stage']) != 'demo') return;
    final skipped = asString(payload['skipped']);
    if (skipped != null) {
      demoMessage = skipped;
    } else {
      final done = asInt(payload['done']) ?? 0;
      final total = asInt(payload['total']) ?? 0;
      demoMessage = total > 0 ? '正在下载并解析录像 $done/$total' : '正在准备录像…';
    }
    _safeNotify();
  }

  void _handleRoomError(Map<String, dynamic> payload) {
    final message = asString(payload['message']) ?? '服务端异常';
    final stage = asString(payload['stage']) ?? '';
    if (stage == 'home') {
      seasonError = message;
    } else if (stage == 'ai') {
      aiError = message;
      aiProgress = null;
      aiPreview = null;
      aiStreaming = false;
      freshTabs.add(1);
    } else {
      demoMessage = message;
    }
    _safeNotify();
  }

  // -- 快照 / 合并 ------------------------------------------------------

  void _applySnapshot(Map<String, dynamic> data) {
    members = asMapList(data['members']).map(Member.fromJson).toList();
    final rawMatch = data['match'];
    if (rawMatch is Map && rawMatch.isNotEmpty) {
      _applyMatchPayload(rawMatch.cast<String, dynamic>(), replace: true, notify: false);
    } else {
      _matchRaw = null;
      match = null;
      mySide = '';
      profiles = <PlayerInfo>[];
      _clearDerived();
    }
    final rawProfiles = data['profiles'];
    if (rawProfiles is List && rawProfiles.isNotEmpty) {
      profiles = rawProfiles
          .whereType<Map>()
          .map((item) => PlayerInfo.fromJson(item.cast<String, dynamic>()))
          .toList();
    }
    final seq = asInt(data['latestSeq']);
    if (seq != null) lastSeq = math.max(lastSeq, seq);
    _safeNotify();
  }

  void _applyMatchPayload(
    Map<String, dynamic> patch, {
    bool replace = false,
    bool notify = true,
  }) {
    final incoming = asString(patch['sessionId']);
    final current = asString(_matchRaw?['sessionId']);
    final isNewMatch = incoming != null && current != null && incoming != current;

    if (replace || _matchRaw == null || isNewMatch) {
      _matchRaw = Map<String, dynamic>.of(patch);
      _clearDerived();
      profiles = <PlayerInfo>[];
    } else {
      _matchRaw = <String, dynamic>{...?_matchRaw, ...patch};
    }

    match = MatchSession.fromJson(_matchRaw!);
    mySide = match?.mySide ?? '';

    final artifact = match?.artifactId;
    if (artifact != null && artifact.isNotEmpty && artifact != artifactId) {
      unawaited(loadPaths(artifact));
    }
    if (match?.postReport != null) freshTabs.add(3);
    if (notify) _safeNotify();
  }

  void _clearDerived() {
    artifactId = null;
    pathPlayers = <PathPlayer>[];
    pathsLoading = false;
    pathsError = null;
    _replays.clear();
    aiError = null;
    aiProgress = null;
    aiPreview = null;
    aiStreaming = false;
    tacticsProgress = null;
    seasonError = null;
    demoMessage = null;
  }

  void _resetMatchState() {
    _matchRaw = null;
    match = null;
    mySide = '';
    profiles = <PlayerInfo>[];
    members = <Member>[];
    identityMessage = null;
    _clearDerived();
  }

  // -- 轨迹 ------------------------------------------------------------

  Future<void> loadPaths(String id) async {
    final currentToken = token;
    if (currentToken == null || currentToken.isEmpty) return;
    artifactId = id;
    pathsLoading = true;
    pathsError = null;
    _safeNotify();
    try {
      final data = await api.artifactIndex(serverUrl, id, currentToken);
      final index = ArtifactIndex.fromJson(data, artifactId: id);
      artifactId = index.artifactId;
      pathPlayers = index.players;
      if (pathPlayers.isEmpty) {
        demoMessage = '这批对手没有可用的历史录像。';
      }
    } on ApiException catch (error) {
      if (error.isAuth) {
        await resetAuth('登录状态已失效，请重新进入');
        return;
      }
      pathsError = error.message;
    } catch (error) {
      pathsError = '轨迹索引加载失败：$error';
    } finally {
      pathsLoading = false;
      _safeNotify();
    }
  }

  Future<ReplayBundle> loadReplay(String steamId) async {
    final cached = _replays[steamId];
    if (cached != null) return cached;
    final id = artifactId;
    final currentToken = token;
    if (id == null || id.isEmpty) throw ApiException('轨迹还没准备好');
    if (currentToken == null) throw ApiException('登录状态已失效');
    final data = await api.artifactPlayer(serverUrl, id, steamId, currentToken);
    final raw = data['replay'];
    if (raw is! Map) throw ApiException('轨迹数据不完整');
    final replay = ReplayBundle.fromJson(raw.cast<String, dynamic>());
    _replays[steamId] = replay;
    return replay;
  }

  // -- 交互 ------------------------------------------------------------

  Future<void> chooseSide(String? side) async {
    final currentToken = token;
    if (currentToken == null) return;
    if (_matchRaw == null) throw ApiException('对局还没上报，先等电脑端识别到比赛');
    final previous = mySide;
    mySide = side ?? '';
    _matchRaw = <String, dynamic>{
      ...?_matchRaw,
      'mySide': side,
      'mySideSource': 'explicit',
    };
    match = _matchRaw == null ? null : MatchSession.fromJson(_matchRaw!);
    _safeNotify();

    try {
      final data = await api.setAnalysisSide(
        serverUrl,
        roomCode,
        currentToken,
        mySide: side,
        all: side == null,
      );
      final resolved = asString(data['mySide']);
      mySide = resolved ?? '';
      _matchRaw = <String, dynamic>{
        ...?_matchRaw,
        'mySide': resolved,
        'mySideSource': asString(data['mySideSource']),
      };
      match = MatchSession.fromJson(_matchRaw!);
      final targets = asInt(data['targets']) ?? 0;
      demoMessage = '分析目标：$targets 人';
      _safeNotify();
    } catch (error) {
      mySide = previous;
      _matchRaw = <String, dynamic>{...?_matchRaw, 'mySide': previous};
      match = MatchSession.fromJson(_matchRaw!);
      _safeNotify();
      rethrow;
    }
  }

  Future<int> rememberSide() async {
    final currentToken = token;
    if (currentToken == null || mySide.isEmpty) {
      throw ApiException('先选我方阵营');
    }
    final data = await api.learnIdentity(
      serverUrl,
      roomCode,
      currentToken,
      side: mySide,
    );
    final count = asInt(data['count']) ?? asInt(data['added']) ?? 0;
    identityMessage = '已记住 $count 个 ID，下一局自动判断';
    _safeNotify();
    return count;
  }

  Future<void> rerunAnalysis() async {
    final currentToken = token;
    if (currentToken == null) return;
    aiError = null;
    aiProgress = '已提交重新分析…';
    _safeNotify();
    try {
      await api.rerunAnalysis(serverUrl, roomCode, currentToken);
    } on ApiException catch (error) {
      aiError = error.message;
      aiProgress = null;
      _safeNotify();
      rethrow;
    }
  }

  Future<void> refresh() async {
    final currentToken = token;
    if (currentToken == null) return;
    try {
      final snapshot = await api.snapshot(serverUrl, roomCode, currentToken);
      _applySnapshot(snapshot);
    } on ApiException catch (error) {
      if (error.isAuth) {
        await resetAuth('登录状态已失效，请重新进入');
        return;
      }
      demoMessage = error.message;
      _safeNotify();
    }
  }

  void selectTab(int index) {
    activeTab = index;
    freshTabs.remove(index);
    _safeNotify();
  }

  void _safeNotify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _generation++;
    _retryTimer?.cancel();
    final socket = _socket;
    _socket = null;
    if (socket != null) {
      unawaited(socket.close());
    }
    super.dispose();
  }
}
