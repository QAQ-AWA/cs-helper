import '../core/format.dart';

class Member {
  const Member({
    required this.id,
    required this.nickname,
    required this.deviceType,
    required this.isOnline,
  });

  final String id;
  final String nickname;
  final String deviceType;
  final bool isOnline;

  bool get isPc => deviceType == 'pc';

  factory Member.fromJson(Map<String, dynamic> json) {
    return Member(
      id: asString(json['id']) ?? '',
      nickname: asString(json['nickname']) ?? '队友',
      deviceType: asString(json['deviceType']) ?? 'mobile',
      isOnline: json['isOnline'] != false,
    );
  }
}

/// 客户端上报 / 服务端补齐后的选手数据。字段很多，缺什么就留空。
class PlayerStats {
  const PlayerStats({
    this.rating,
    this.kd,
    this.headshotRate,
    this.winRate,
    this.matchesPlayed,
    this.rankLevel,
    this.seasonRating,
    this.seasonAdr,
    this.seasonRws,
    this.seasonKast,
    this.recentResults,
    this.elo,
    this.rankNum,
    this.rankDesc,
    this.kills,
    this.deaths,
    this.assists,
    this.mvpCount,
    this.firstKillRate,
    this.clutchWinRate,
    this.entryKillRatio,
    this.tradeFragRate,
    this.recentWinRate,
    this.mapWinRate,
    this.mapMatches,
    this.mapSampleLow,
  });

  final double? rating;
  final double? kd;
  final double? headshotRate;
  final double? winRate;
  final int? matchesPlayed;
  final String? rankLevel;
  final double? seasonRating;
  final double? seasonAdr;
  final double? seasonRws;
  final double? seasonKast;
  final String? recentResults;
  final double? elo;
  final int? rankNum;
  final String? rankDesc;
  final int? kills;
  final int? deaths;
  final int? assists;
  final int? mvpCount;
  final double? firstKillRate;
  final double? clutchWinRate;
  final double? entryKillRatio;
  final double? tradeFragRate;
  final double? recentWinRate;
  final double? mapWinRate;
  final int? mapMatches;
  final bool? mapSampleLow;

  static const empty = PlayerStats();

  factory PlayerStats.fromJson(Map<String, dynamic> json) {
    return PlayerStats(
      rating: asDouble(json['rating']),
      kd: asDouble(json['kd']),
      headshotRate: asDouble(json['headshotRate']),
      winRate: asDouble(json['winRate']),
      matchesPlayed: asInt(json['matchesPlayed']),
      rankLevel: json['rankLevel']?.toString(),
      seasonRating: asDouble(json['seasonRating']),
      seasonAdr: asDouble(json['seasonAdr']),
      seasonRws: asDouble(json['seasonRws']),
      seasonKast: asDouble(json['seasonKast']),
      recentResults: asString(json['recentResults']),
      elo: asDouble(json['elo']),
      rankNum: asInt(json['rankNum']),
      rankDesc: asString(json['rankDesc']),
      kills: asInt(json['kills']),
      deaths: asInt(json['deaths']),
      assists: asInt(json['assists']),
      mvpCount: asInt(json['mvpCount']),
      firstKillRate: asDouble(json['firstKillRate']),
      clutchWinRate: asDouble(json['clutchWinRate']),
      entryKillRatio: asDouble(json['entryKillRatio']),
      tradeFragRate: asDouble(json['tradeFragRate']),
      recentWinRate: asDouble(json['recentWinRate']),
      mapWinRate: asDouble(json['mapWinRate']),
      mapMatches: asInt(json['mapMatches']),
      mapSampleLow: json['mapSampleLow'] is bool ? json['mapSampleLow'] as bool : null,
    );
  }

  /// 服务端画像优先：只在它有值的时候覆盖客户端上报值。
  PlayerStats mergedWith(PlayerStats? other) {
    if (other == null) return this;
    return PlayerStats(
      rating: other.rating ?? rating,
      kd: other.kd ?? kd,
      headshotRate: other.headshotRate ?? headshotRate,
      winRate: other.winRate ?? winRate,
      matchesPlayed: other.matchesPlayed ?? matchesPlayed,
      rankLevel: other.rankLevel ?? rankLevel,
      seasonRating: other.seasonRating ?? seasonRating,
      seasonAdr: other.seasonAdr ?? seasonAdr,
      seasonRws: other.seasonRws ?? seasonRws,
      seasonKast: other.seasonKast ?? seasonKast,
      recentResults: other.recentResults ?? recentResults,
      elo: other.elo ?? elo,
      rankNum: other.rankNum ?? rankNum,
      rankDesc: other.rankDesc ?? rankDesc,
      kills: other.kills ?? kills,
      deaths: other.deaths ?? deaths,
      assists: other.assists ?? assists,
      mvpCount: other.mvpCount ?? mvpCount,
      firstKillRate: other.firstKillRate ?? firstKillRate,
      clutchWinRate: other.clutchWinRate ?? clutchWinRate,
      entryKillRatio: other.entryKillRatio ?? entryKillRatio,
      tradeFragRate: other.tradeFragRate ?? tradeFragRate,
      recentWinRate: other.recentWinRate ?? recentWinRate,
      mapWinRate: other.mapWinRate ?? mapWinRate,
      mapMatches: other.mapMatches ?? mapMatches,
      mapSampleLow: other.mapSampleLow ?? mapSampleLow,
    );
  }
}

class PlayerInfo {
  const PlayerInfo({
    required this.steamId,
    required this.platformUserId,
    required this.nickname,
    this.avatarUrl,
    this.isSelf = false,
    this.partyTag,
    this.team,
    this.stats = PlayerStats.empty,
  });

  final String steamId;
  final String platformUserId;
  final String nickname;
  final String? avatarUrl;
  final bool isSelf;
  final String? partyTag;

  /// 'ct' | 't' | null（画像接口会带 team）
  final String? team;
  final PlayerStats stats;

  factory PlayerInfo.fromJson(Map<String, dynamic> json, {String? fallbackTeam}) {
    return PlayerInfo(
      steamId: asString(json['steamId']) ?? '',
      platformUserId: asString(json['platformUserId']) ?? asString(json['domain']) ?? '',
      nickname: asString(json['nickname']) ?? asString(json['username']) ?? 'Unknown',
      avatarUrl: asString(json['avatarUrl']),
      isSelf: asBool(json['isSelf']),
      partyTag: asString(json['partyTag']),
      team: asString(json['team']) ?? fallbackTeam,
      stats: PlayerStats.fromJson(asMap(json['stats'])),
    );
  }
}

class TeamPayload {
  const TeamPayload({this.ct = const <PlayerInfo>[], this.t = const <PlayerInfo>[]});

  final List<PlayerInfo> ct;
  final List<PlayerInfo> t;

  List<PlayerInfo> get all => <PlayerInfo>[...ct, ...t];

  List<PlayerInfo> forSide(String side) => side == 't' ? t : ct;

  factory TeamPayload.fromJson(Map<String, dynamic> json) {
    List<PlayerInfo> parse(String key) => asMapList(json[key])
        .map((item) => PlayerInfo.fromJson(item, fallbackTeam: key))
        .toList();
    return TeamPayload(ct: parse('ct'), t: parse('t'));
  }

  static const empty = TeamPayload();
}

/// 阵容页的一行：上报名单 + 服务端画像合并后的结果。
class RosterRow {
  const RosterRow({
    required this.side,
    required this.player,
    required this.profile,
    required this.stats,
  });

  final String side;
  final PlayerInfo player;
  final PlayerInfo? profile;
  final PlayerStats stats;

  String get nickname => player.nickname.isNotEmpty ? player.nickname : (profile?.nickname ?? 'Unknown');

  String get steamId {
    if (player.steamId.isNotEmpty) return player.steamId;
    return profile?.steamId ?? '';
  }

  String? get avatarUrl => profile?.avatarUrl ?? player.avatarUrl;

  bool get isSelf => profile?.isSelf == true || player.isSelf;

  /// 赛季场均优先；没有赛季数据就退回近期 Rating。
  double? get seasonRating => stats.seasonRating ?? stats.rating;

  /// 两个来源相同时不重复展示：说明没拿到真正的赛季场均。
  double? get recentRating {
    final value = stats.rating;
    if (value == null) return null;
    if (seasonRating != null && value == seasonRating) return null;
    return value;
  }
}
