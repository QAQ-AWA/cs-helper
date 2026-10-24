import '../core/format.dart';

class DecisiveFactor {
  const DecisiveFactor({
    required this.dimension,
    required this.advantage,
    required this.impact,
    required this.title,
    required this.summary,
  });

  final String dimension;
  final String advantage;
  final int impact;
  final String title;
  final String summary;

  factory DecisiveFactor.fromJson(Map<String, dynamic> json) {
    return DecisiveFactor(
      dimension: asString(json['dimension']) ?? 'strength',
      advantage: asString(json['advantage']) ?? 'Even',
      impact: asInt(json['impact']) ?? 0,
      title: asString(json['title']) ?? '',
      summary: asString(json['summary']) ?? '',
    );
  }
}

class PlayerSignal {
  const PlayerSignal({
    required this.steamId,
    required this.nickname,
    required this.side,
    required this.kind,
    required this.impact,
    required this.title,
    required this.summary,
  });

  final String steamId;
  final String nickname;
  final String side;
  final String kind;
  final int impact;
  final String title;
  final String summary;

  factory PlayerSignal.fromJson(Map<String, dynamic> json) {
    return PlayerSignal(
      steamId: asString(json['steamId']) ?? '',
      nickname: asString(json['nickname']) ?? '',
      side: asString(json['side']) ?? 'A',
      kind: asString(json['kind']) ?? 'watch',
      impact: asInt(json['impact']) ?? 0,
      title: asString(json['title']) ?? '',
      summary: asString(json['summary']) ?? '',
    );
  }
}

class PlanItem {
  const PlanItem(this.text);

  final String text;
}

class TeamPlan {
  const TeamPlan({this.winConditions = const <PlanItem>[], this.risks = const <PlanItem>[]});

  final List<PlanItem> winConditions;
  final List<PlanItem> risks;

  bool get isEmpty => winConditions.isEmpty && risks.isEmpty;

  factory TeamPlan.fromJson(Map<String, dynamic> json) {
    List<PlanItem> parse(String key) => asMapList(json[key])
        .map((item) => PlanItem(asString(item['text']) ?? ''))
        .where((item) => item.text.isNotEmpty)
        .toList();
    return TeamPlan(winConditions: parse('winConditions'), risks: parse('risks'));
  }

  static const empty = TeamPlan();
}

/// 服务端 v3 结构化分析结果（`app/analysis_result.py`）。
class AnalysisResult {
  const AnalysisResult({
    required this.schemaVersion,
    required this.predictedWinner,
    required this.winA,
    required this.winB,
    required this.confidence,
    required this.dataCoverage,
    required this.headline,
    required this.factors,
    required this.signals,
    required this.plans,
    required this.uncertainties,
  });

  final int schemaVersion;
  final String predictedWinner;
  final double winA;
  final double winB;
  final int confidence;
  final double dataCoverage;
  final String headline;
  final List<DecisiveFactor> factors;
  final List<PlayerSignal> signals;
  final Map<String, TeamPlan> plans;
  final List<String> uncertainties;

  TeamPlan planFor(String side) => plans[side] ?? TeamPlan.empty;

  factory AnalysisResult.fromJson(Map<String, dynamic> json) {
    final probability = asMap(json['modelWinProbability']).isNotEmpty
        ? asMap(json['modelWinProbability'])
        : asMap(json['winProbability']);
    var winA = asDouble(probability['A']) ?? 50;
    var winB = asDouble(probability['B']) ?? (100 - winA);
    winA = winA.clamp(0, 100).toDouble();
    winB = winB.clamp(0, 100).toDouble();

    var coverage = asDouble(json['dataCoverage']) ?? 0;
    if (coverage > 1) coverage = coverage / 100;
    coverage = coverage.clamp(0, 1).toDouble();

    final plans = <String, TeamPlan>{};
    final rawPlans = asMap(json['teamPlans']);
    for (final side in const <String>['A', 'B']) {
      final plan = asMap(rawPlans[side]);
      if (plan.isNotEmpty) plans[side] = TeamPlan.fromJson(plan);
    }

    return AnalysisResult(
      schemaVersion: asInt(json['schemaVersion']) ?? 3,
      predictedWinner: asString(json['predictedWinner']) ?? 'Even',
      winA: winA,
      winB: winB,
      confidence: (asInt(json['confidence']) ?? 0).clamp(0, 100),
      dataCoverage: coverage,
      headline: asString(json['headline']) ?? '',
      factors: asMapList(json['decisiveFactors']).map(DecisiveFactor.fromJson).toList(),
      signals: asMapList(json['playerSignals']).map(PlayerSignal.fromJson).toList(),
      plans: plans,
      uncertainties: asStringList(json['uncertainties']),
    );
  }
}
