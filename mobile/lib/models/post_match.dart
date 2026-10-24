import '../core/format.dart';

class HalfScores {
  const HalfScores({this.fhA = 0, this.fhB = 0, this.shA = 0, this.shB = 0});

  final int fhA;
  final int fhB;
  final int shA;
  final int shB;

  factory HalfScores.fromJson(Map<String, dynamic> json) {
    return HalfScores(
      fhA: asInt(json['fhA']) ?? 0,
      fhB: asInt(json['fhB']) ?? 0,
      shA: asInt(json['shA']) ?? 0,
      shB: asInt(json['shB']) ?? 0,
    );
  }
}

class PostPlayer {
  const PostPlayer({
    required this.nickname,
    required this.kill,
    required this.death,
    required this.assist,
    required this.rating,
    required this.adr,
    required this.teamSide,
    required this.isMvp,
    required this.isSvp,
  });

  final String nickname;
  final int kill;
  final int death;
  final int assist;
  final double? rating;
  final double? adr;

  /// 1 = A 队，2 = B 队
  final int teamSide;
  final bool isMvp;
  final bool isSvp;

  factory PostPlayer.fromJson(Map<String, dynamic> json) {
    return PostPlayer(
      nickname: asString(json['nickname']) ?? '',
      kill: asInt(json['kill']) ?? 0,
      death: asInt(json['death']) ?? 0,
      assist: asInt(json['assist']) ?? 0,
      rating: asDouble(json['rating']),
      adr: asDouble(json['adr']),
      teamSide: asInt(json['teamSide']) ?? 0,
      isMvp: asBool(json['isMvp']),
      isSvp: asBool(json['isSvp']),
    );
  }
}

class PredictionComparison {
  const PredictionComparison({this.isCorrect, this.headline});

  final bool? isCorrect;
  final String? headline;

  factory PredictionComparison.fromJson(Map<String, dynamic> json) {
    return PredictionComparison(
      isCorrect: json['isCorrect'] is bool ? json['isCorrect'] as bool : null,
      headline: asString(json['headline']),
    );
  }
}

class PostMatchReport {
  const PostMatchReport({
    required this.matchCode,
    required this.mapName,
    required this.roundTotal,
    required this.scoreA,
    required this.scoreB,
    this.winnerSide,
    this.halfScores,
    required this.players,
    this.comparison,
    required this.isFinished,
  });

  final String matchCode;
  final String mapName;
  final int roundTotal;
  final int scoreA;
  final int scoreB;
  final String? winnerSide;
  final HalfScores? halfScores;
  final List<PostPlayer> players;
  final PredictionComparison? comparison;
  final bool isFinished;

  List<PostPlayer> playersFor(int side) {
    final rows = players.where((player) => player.teamSide == side).toList();
    rows.sort((a, b) => (b.rating ?? 0).compareTo(a.rating ?? 0));
    return rows;
  }

  factory PostMatchReport.fromJson(Map<String, dynamic> json) {
    return PostMatchReport(
      matchCode: asString(json['matchCode']) ?? '',
      mapName: asString(json['mapName']) ?? '',
      roundTotal: asInt(json['roundTotal']) ?? 0,
      scoreA: asInt(json['scoreA']) ?? 0,
      scoreB: asInt(json['scoreB']) ?? 0,
      winnerSide: asString(json['winnerSide']),
      halfScores: json['halfScores'] is Map
          ? HalfScores.fromJson(asMap(json['halfScores']))
          : null,
      players: asMapList(json['players']).map(PostPlayer.fromJson).toList(),
      comparison: json['comparison'] is Map
          ? PredictionComparison.fromJson(asMap(json['comparison']))
          : null,
      isFinished: json['isFinished'] != false,
    );
  }
}
