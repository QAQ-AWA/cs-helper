import 'dart:math' as math;
import 'dart:ui' show Offset;

import '../core/format.dart';

const double replayRadarSize = 1024;
const double replayWindowSeconds = 20;

/// 世界坐标 → 雷达图像素坐标。公式与 `engine/maps.py`、`replay-core.js` 一致，别写反。
class ReplayTransform {
  const ReplayTransform({required this.posX, required this.posY, required this.scale});

  final double posX;
  final double posY;
  final double scale;

  Offset toPixel(double gx, double gy) {
    final divisor = scale == 0 ? 1.0 : scale;
    return Offset((gx - posX) / divisor, (posY - gy) / divisor);
  }

  factory ReplayTransform.fromJson(Map<String, dynamic> json) {
    return ReplayTransform(
      posX: asDouble(json['pos_x']) ?? 0,
      posY: asDouble(json['pos_y']) ?? 0,
      scale: asDouble(json['scale']) ?? 1,
    );
  }

  static const identity = ReplayTransform(posX: 0, posY: 0, scale: 1);
}

class ReplayPoint {
  const ReplayPoint(this.t, this.x, this.y);

  final double t;
  final double x;
  final double y;

  factory ReplayPoint.fromList(List<dynamic> raw) {
    return ReplayPoint(
      raw.isNotEmpty ? (asDouble(raw[0]) ?? 0) : 0,
      raw.length > 1 ? (asDouble(raw[1]) ?? 0) : 0,
      raw.length > 2 ? (asDouble(raw[2]) ?? 0) : 0,
    );
  }
}

class Grenade {
  const Grenade({
    required this.type,
    required this.throwT,
    this.arc = const <ReplayPoint>[],
    this.land,
    this.landT,
    this.expireT,
  });

  final String type;
  final double throwT;
  final List<ReplayPoint> arc;
  final Offset? land;
  final double? landT;
  final double? expireT;

  factory Grenade.fromJson(Map<String, dynamic> json) {
    final arcRaw = json['arc'];
    final arc = <ReplayPoint>[];
    if (arcRaw is List) {
      for (final point in arcRaw) {
        if (point is List) arc.add(ReplayPoint.fromList(point));
      }
    }
    final landRaw = json['land'];
    Offset? land;
    if (landRaw is List && landRaw.length >= 2) {
      final x = asDouble(landRaw[0]);
      final y = asDouble(landRaw[1]);
      if (x != null && y != null) land = Offset(x, y);
    }
    return Grenade(
      type: asString(json['type']) ?? 'smoke',
      throwT: asDouble(json['throw_t']) ?? 0,
      arc: arc,
      land: land,
      landT: asDouble(json['land_t']),
      expireT: asDouble(json['expire_t']),
    );
  }
}

class Plant {
  const Plant({
    required this.site,
    required this.x,
    required this.y,
    required this.t,
    required this.by,
  });

  final String site;
  final double x;
  final double y;
  final double t;
  final String by;

  factory Plant.fromJson(Map<String, dynamic> json) {
    return Plant(
      site: asString(json['site']) ?? 'unknown',
      x: asDouble(json['x']) ?? 0,
      y: asDouble(json['y']) ?? 0,
      t: asDouble(json['t']) ?? 0,
      by: asString(json['by']) ?? '',
    );
  }
}

class ReplayRound {
  const ReplayRound({
    required this.side,
    required this.rtype,
    required this.roundId,
    required this.path,
    this.grenades = const <Grenade>[],
    this.deathT,
    this.plant,
    this.matchCode = '',
  });

  final String side;
  final String rtype;
  final int roundId;
  final List<ReplayPoint> path;
  final List<Grenade> grenades;
  final double? deathT;
  final Plant? plant;
  final String matchCode;

  double get endTime => path.isEmpty ? replayWindowSeconds : path.last.t;

  factory ReplayRound.fromJson(Map<String, dynamic> json) {
    final path = <ReplayPoint>[];
    final rawPath = json['path'];
    if (rawPath is List) {
      for (final point in rawPath) {
        if (point is List) path.add(ReplayPoint.fromList(point));
      }
    }
    return ReplayRound(
      side: asString(json['side']) ?? 'CT',
      rtype: asString(json['rtype']) ?? 'full',
      roundId: asInt(json['round_id']) ?? 0,
      path: path,
      grenades: asMapList(json['grenades']).map(Grenade.fromJson).toList(),
      deathT: asDouble(json['death_t']),
      plant: json['plant'] is Map ? Plant.fromJson(asMap(json['plant'])) : null,
      matchCode: asString(json['match_code']) ?? '',
    );
  }
}

class ReplayBundle {
  const ReplayBundle({
    required this.username,
    required this.map,
    required this.radar,
    required this.transform,
    this.combatKd,
    this.awpRate,
    required this.demosFound,
    required this.roundCount,
    required this.rounds,
  });

  final String username;
  final String map;
  final String radar;
  final ReplayTransform transform;
  final double? combatKd;
  final double? awpRate;
  final int demosFound;
  final int roundCount;
  final List<ReplayRound> rounds;

  factory ReplayBundle.fromJson(Map<String, dynamic> json) {
    final combat = asMap(json['combat_stats']);
    return ReplayBundle(
      username: asString(json['username']) ?? '',
      map: asString(json['map']) ?? 'de_unknown',
      radar: asString(json['radar']) ?? '',
      transform: ReplayTransform.fromJson(asMap(json['transform'])),
      combatKd: asDouble(combat['kd']),
      awpRate: asDouble(combat['awp_rate']),
      demosFound: asInt(json['demos_found']) ?? 0,
      roundCount: asInt(json['round_count']) ?? 0,
      rounds: asMapList(json['rounds']).map(ReplayRound.fromJson).toList(),
    );
  }

  bool _matches(ReplayRound round, String? side, String? rtype) {
    if (side != null && side.isNotEmpty && round.side != side) return false;
    if (rtype != null && rtype.isNotEmpty && round.rtype != rtype) return false;
    return true;
  }

  List<ReplayRound> filtered({String? side, String? rtype}) {
    return rounds.where((round) => _matches(round, side, rtype)).toList();
  }

  double durationFor({String? side, String? rtype}) {
    var end = 1.0;
    for (final round in rounds) {
      if (!_matches(round, side, rtype)) continue;
      end = math.max(end, round.endTime);
    }
    return end.clamp(1.0, replayWindowSeconds);
  }
}

/// 线性插值取 t 时刻的位置（与网页端 `sampleAt` 相同）。
ReplayPoint? sampleReplayPoint(List<ReplayPoint> path, double t) {
  if (path.isEmpty) return null;
  if (t <= path.first.t) return path.first;
  final last = path.last;
  if (t >= last.t) return last;
  var low = 0;
  var high = path.length - 1;
  while (high - low > 1) {
    final mid = (low + high) >> 1;
    if (path[mid].t <= t) {
      low = mid;
    } else {
      high = mid;
    }
  }
  final a = path[low];
  final b = path[high];
  final span = b.t - a.t;
  final ratio = span == 0 ? 0.0 : (t - a.t) / span;
  return ReplayPoint(t, a.x + (b.x - a.x) * ratio, a.y + (b.y - a.y) * ratio);
}
