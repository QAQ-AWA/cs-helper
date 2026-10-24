import '../core/format.dart';
import 'analysis.dart';
import 'player.dart';
import 'post_match.dart';

class ServerConfig {
  const ServerConfig({
    required this.mode,
    required this.roomCode,
    required this.protocolVersion,
    required this.demoEnabled,
    required this.aiEnabled,
  });

  final String mode;
  final String? roomCode;
  final int protocolVersion;
  final bool demoEnabled;
  final bool aiEnabled;

  bool get isSingleRoom => mode == 'single';

  factory ServerConfig.fromJson(Map<String, dynamic> json) {
    return ServerConfig(
      mode: asString(json['mode']) ?? 'multi',
      roomCode: asString(json['roomCode']),
      protocolVersion: asInt(json['protocolVersion']) ?? 1,
      demoEnabled: json['demoEnabled'] != false,
      aiEnabled: json['aiEnabled'] == true,
    );
  }
}

class JoinResult {
  const JoinResult({
    required this.roomCode,
    required this.roomId,
    required this.token,
    required this.expiresAt,
  });

  final String roomCode;
  final String roomId;
  final String token;
  final int expiresAt;

  factory JoinResult.fromJson(Map<String, dynamic> json) {
    return JoinResult(
      roomCode: asString(json['roomCode']) ?? '',
      roomId: asString(json['roomId']) ?? '',
      token: asString(json['token']) ?? '',
      expiresAt: asInt(json['expiresAt']) ?? 0,
    );
  }
}

class MatchSession {
  const MatchSession({
    required this.sessionId,
    required this.platform,
    required this.matchId,
    required this.mapName,
    required this.phase,
    this.countdownSeconds,
    this.mySide,
    this.mySideSource,
    required this.profileState,
    required this.demoState,
    required this.homeState,
    this.homeError,
    required this.homeCoverage,
    this.artifactId,
    required this.aiState,
    this.aiText,
    this.aiResult,
    this.aiWait = const <String>[],
    required this.tacticsState,
    this.tacticsText,
    this.postReport,
    this.teams = TeamPayload.empty,
    required this.createdAt,
    required this.updatedAt,
  });

  final String sessionId;
  final String platform;
  final String matchId;
  final String mapName;
  final String phase;
  final int? countdownSeconds;

  /// 'ct' | 't' | null
  final String? mySide;

  /// 'explicit' | 'library' | 'self' | 'party' | null
  final String? mySideSource;

  final String profileState;
  final String demoState;
  final String homeState;
  final String? homeError;
  final int homeCoverage;
  final String? artifactId;
  final String aiState;
  final String? aiText;
  final AnalysisResult? aiResult;
  final List<String> aiWait;
  final String tacticsState;
  final String? tacticsText;
  final PostMatchReport? postReport;
  final TeamPayload teams;
  final int createdAt;
  final int updatedAt;

  bool get hasAnalysis => aiResult != null || (aiText != null && aiText!.isNotEmpty);

  factory MatchSession.fromJson(Map<String, dynamic> json) {
    return MatchSession(
      sessionId: asString(json['sessionId']) ?? '',
      platform: asString(json['platform']) ?? '5e',
      matchId: asString(json['matchId']) ?? '',
      mapName: asString(json['mapName']) ?? 'de_unknown',
      phase: asString(json['phase']) ?? 'ready',
      countdownSeconds: asInt(json['countdownSeconds']),
      mySide: asString(json['mySide']),
      mySideSource: asString(json['mySideSource']),
      profileState: asString(json['profileState']) ?? 'pending',
      demoState: asString(json['demoState']) ?? 'pending',
      homeState: asString(json['homeState']) ?? 'pending',
      homeError: asString(json['homeError']),
      homeCoverage: asInt(json['homeCoverage']) ?? 0,
      artifactId: asString(json['artifactId']),
      aiState: asString(json['aiState']) ?? 'pending',
      aiText: asString(json['aiText']),
      aiResult: json['aiResult'] is Map
          ? AnalysisResult.fromJson(asMap(json['aiResult']))
          : null,
      aiWait: asStringList(json['aiWait']),
      tacticsState: asString(json['tacticsState']) ?? 'pending',
      tacticsText: asString(json['tacticsText']),
      postReport: json['postReport'] is Map
          ? PostMatchReport.fromJson(asMap(json['postReport']))
          : null,
      teams: TeamPayload.fromJson(asMap(json['teams'])),
      createdAt: asInt(json['createdAt']) ?? 0,
      updatedAt: asInt(json['updatedAt']) ?? 0,
    );
  }

  static const empty = MatchSession(
    sessionId: '',
    platform: '',
    matchId: '',
    mapName: 'de_unknown',
    phase: 'ready',
    profileState: 'pending',
    demoState: 'pending',
    homeState: 'pending',
    homeCoverage: 0,
    aiState: 'pending',
    tacticsState: 'pending',
    createdAt: 0,
    updatedAt: 0,
  );
}

class PathPlayer {
  const PathPlayer({
    required this.steamId,
    required this.username,
    required this.nickname,
    required this.domain,
    required this.rounds,
    required this.bytes,
  });

  final String steamId;
  final String username;
  final String nickname;
  final String domain;
  final int rounds;
  final int bytes;

  String get displayName {
    if (nickname.isNotEmpty) return nickname;
    if (username.isNotEmpty) return username;
    return steamId;
  }

  factory PathPlayer.fromJson(Map<String, dynamic> json) {
    return PathPlayer(
      steamId: asString(json['steamId']) ?? '',
      username: asString(json['username']) ?? '',
      nickname: asString(json['nickname']) ?? '',
      domain: asString(json['domain']) ?? '',
      rounds: asInt(json['rounds']) ?? 0,
      bytes: asInt(json['bytes']) ?? 0,
    );
  }
}

class ArtifactIndex {
  const ArtifactIndex({
    required this.artifactId,
    required this.map,
    required this.players,
    required this.failed,
  });

  final String artifactId;
  final String map;
  final List<PathPlayer> players;
  final List<String> failed;

  factory ArtifactIndex.fromJson(Map<String, dynamic> json, {String artifactId = ''}) {
    return ArtifactIndex(
      artifactId: artifactId,
      map: asString(json['map']) ?? 'de_unknown',
      players: asMapList(json['players']).map(PathPlayer.fromJson).toList(),
      failed: asStringList(json['failed']),
    );
  }
}
