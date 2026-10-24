import 'dart:math' as math;

/// 服务端返回的数字可能是 int / double / 字符串，统一收敛成 double。
double? asDouble(Object? value) {
  if (value is num) {
    final result = value.toDouble();
    return result.isFinite ? result : null;
  }
  if (value is String) {
    final parsed = double.tryParse(value);
    return parsed != null && parsed.isFinite ? parsed : null;
  }
  return null;
}

int? asInt(Object? value) {
  if (value is num) return value.toInt();
  if (value is String) return int.tryParse(value);
  return null;
}

bool asBool(Object? value) => value == true;

String? asString(Object? value) {
  if (value is String && value.trim().isNotEmpty) return value;
  return null;
}

Map<String, dynamic> asMap(Object? value) {
  if (value is Map) return value.cast<String, dynamic>();
  return const <String, dynamic>{};
}

List<Map<String, dynamic>> asMapList(Object? value) {
  if (value is List) {
    return value.whereType<Map>().map((item) => item.cast<String, dynamic>()).toList();
  }
  return const <Map<String, dynamic>>[];
}

List<String> asStringList(Object? value) {
  if (value is List) {
    return value.whereType<String>().toList();
  }
  return const <String>[];
}

/// 保留两位小数；没有数据时统一显示破折号，不要显示 0 或 null。
String fmt(Object? value, [int digits = 2]) {
  final number = asDouble(value);
  if (number == null) return '—';
  return number.toStringAsFixed(digits);
}

/// 服务端有的字段是百分数（46.0），有的是 0-1 小数（0.46）。
double? fraction(Object? value) {
  final raw = asDouble(value);
  if (raw == null) return null;
  return raw > 1 ? raw / 100 : raw;
}

String pct(Object? value) {
  final raw = fraction(value);
  if (raw == null) return '—';
  return '${(raw * 100).round()}%';
}

/// 近 5 场：'WWLWL' → ['W', 'W', 'L', 'W', 'L']
List<String> recentFlags(Object? raw) {
  if (raw is! String) return const <String>[];
  final flags = raw
      .toUpperCase()
      .split('')
      .where((char) => char == 'W' || char == 'L' || char == 'D')
      .toList();
  if (flags.length <= 5) return flags;
  return flags.sublist(flags.length - 5);
}

/// 服务端约定：认出我方时 A = 我方，否则 A = CT。
String teamToken(String side, String? mySide) {
  if (mySide == null || mySide.isEmpty) return side == 'ct' ? 'A' : 'B';
  return side == mySide ? 'A' : 'B';
}

String teamTitle(String side, String? mySide) {
  final token = teamToken(side, mySide);
  if (mySide == null || mySide.isEmpty) return token == 'A' ? 'A 队' : 'B 队';
  return token == 'A' ? '我方' : '对方';
}

/// 分析结果里的 A/B 视角。
String sideName(String token, String? mySide) {
  if (token == 'Even' || token == 'even') return '持平';
  if (mySide == null || mySide.isEmpty) return token == 'A' ? 'A 队' : 'B 队';
  return token == 'A' ? '我方' : '对方';
}

/// 模型正文写的是「A 队 / B 队」，界面上要按我方视角说。
String persp(String text, String? mySide) {
  if (text.isEmpty || mySide == null || mySide.isEmpty) return text;
  return text
      .replaceAll(RegExp(r'A\s*队'), '我方')
      .replaceAll(RegExp(r'B\s*队'), '对方')
      .replaceAll(RegExp(r'Team\s*A\b', caseSensitive: false), '我方')
      .replaceAll(RegExp(r'Team\s*B\b', caseSensitive: false), '对方');
}

String mapLabel(String? mapName) {
  if (mapName == null || mapName.isEmpty || mapName == 'de_unknown' || mapName == 'unknown') {
    return '等待地图确认…';
  }
  return mapName;
}

String initialOf(String name) {
  final trimmed = name.trim();
  if (trimmed.isEmpty) return '?';
  return trimmed.substring(0, 1).toUpperCase();
}

int clampInt(int value, int min, int max) => math.min(math.max(value, min), max);
