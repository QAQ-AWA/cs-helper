import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../core/format.dart';
import '../models/match.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.code, this.status});

  final String message;
  final int? code;
  final int? status;

  bool get isAuth => status == 401 || status == 403;

  @override
  String toString() => message;
}

/// 允许用户只填 `192.168.3.46:8787`。
String normalizeServer(String raw) {
  var value = raw.trim();
  if (value.isEmpty) return '';
  if (!value.startsWith('http://') && !value.startsWith('https://')) {
    value = 'http://$value';
  }
  while (value.endsWith('/')) {
    value = value.substring(0, value.length - 1);
  }
  return value;
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  void dispose() => _client.close();

  Uri _uri(String server, String path, [Map<String, String>? query]) {
    final base = Uri.parse(normalizeServer(server));
    final prefix = base.path.endsWith('/')
        ? base.path.substring(0, base.path.length - 1)
        : base.path;
    return base.replace(path: '$prefix$path', queryParameters: query);
  }

  Future<Map<String, dynamic>> _send(
    String method,
    String server,
    String path, {
    Map<String, String>? query,
    Object? body,
    String? token,
  }) async {
    final uri = _uri(server, path, query);
    final headers = <String, String>{'Accept': 'application/json'};
    if (body != null) headers['Content-Type'] = 'application/json';
    if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';

    http.Response response;
    try {
      final request = http.Request(method, uri)..headers.addAll(headers);
      if (body != null) request.body = jsonEncode(body);
      final streamed = await _client.send(request).timeout(const Duration(seconds: 20));
      response = await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw ApiException('连接服务端超时，检查地址与 Wi-Fi');
    } on SocketException {
      throw ApiException('连不上服务端，检查地址与 Wi-Fi');
    } on http.ClientException catch (error) {
      throw ApiException('网络请求失败：${error.message}');
    }

    Map<String, dynamic>? json;
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map) json = decoded.cast<String, dynamic>();
    } catch (_) {
      // 反向代理的 502 页面不是 JSON，下面统一报错。
    }

    if (response.statusCode == 401 || response.statusCode == 403) {
      throw ApiException(
        asString(json?['message']) ?? '登录状态已失效',
        code: asInt(json?['code']),
        status: response.statusCode,
      );
    }
    if (json == null) {
      throw ApiException('服务端返回异常（HTTP ${response.statusCode}）', status: response.statusCode);
    }
    if (asInt(json['code']) != 0) {
      throw ApiException(
        asString(json['message']) ?? '请求失败',
        code: asInt(json['code']),
        status: response.statusCode,
      );
    }
    final data = json['data'];
    return data is Map ? data.cast<String, dynamic>() : <String, dynamic>{};
  }

  Future<ServerConfig> fetchConfig(String server) async {
    final data = await _send('GET', server, '/api/v1/config');
    return ServerConfig.fromJson(data);
  }

  Future<JoinResult> join(
    String server, {
    required String roomCode,
    required String nickname,
  }) async {
    final data = await _send(
      'POST',
      server,
      '/api/v1/room/join',
      body: <String, dynamic>{
        'roomCode': roomCode,
        'nickname': nickname,
        'deviceType': 'mobile',
      },
    );
    return JoinResult.fromJson(data);
  }

  Future<Map<String, dynamic>> snapshot(String server, String roomCode, String token) {
    return _send(
      'GET',
      server,
      '/api/v1/room/${Uri.encodeComponent(roomCode)}/snapshot',
      token: token,
    );
  }

  Future<Map<String, dynamic>> artifactIndex(
    String server,
    String artifactId,
    String token,
  ) {
    return _send(
      'GET',
      server,
      '/api/v1/artifacts/${Uri.encodeComponent(artifactId)}',
      token: token,
    );
  }

  Future<Map<String, dynamic>> artifactPlayer(
    String server,
    String artifactId,
    String steamId,
    String token,
  ) {
    return _send(
      'GET',
      server,
      '/api/v1/artifacts/${Uri.encodeComponent(artifactId)}/players/${Uri.encodeComponent(steamId)}',
      token: token,
    );
  }

  Future<Map<String, dynamic>> setAnalysisSide(
    String server,
    String roomCode,
    String token, {
    required String? mySide,
    required bool all,
  }) {
    return _send(
      'POST',
      server,
      '/api/v1/room/${Uri.encodeComponent(roomCode)}/analysis-side',
      token: token,
      body: <String, dynamic>{'mySide': mySide, 'all': all},
    );
  }

  Future<Map<String, dynamic>> learnIdentity(
    String server,
    String roomCode,
    String token, {
    required String side,
  }) {
    return _send(
      'POST',
      server,
      '/api/v1/identity/learn',
      token: token,
      query: <String, String>{'roomCode': roomCode},
      body: <String, dynamic>{'side': side},
    );
  }

  Future<Map<String, dynamic>> rerunAnalysis(
    String server,
    String roomCode,
    String token,
  ) {
    return _send(
      'POST',
      server,
      '/api/v1/room/${Uri.encodeComponent(roomCode)}/analysis/rerun',
      token: token,
    );
  }

  String wsUrl(String server, String token, int lastSeq) {
    final base = Uri.parse(normalizeServer(server));
    final prefix = base.path.endsWith('/')
        ? base.path.substring(0, base.path.length - 1)
        : base.path;
    return Uri(
      scheme: base.scheme == 'https' ? 'wss' : 'ws',
      host: base.host,
      port: base.hasPort ? base.port : null,
      path: '$prefix/ws',
      queryParameters: <String, String>{'token': token, 'lastSeq': '$lastSeq'},
    ).toString();
  }

  /// 服务端给的是 `/maps/de_dust2/radar.png` 这种根相对路径。
  String absoluteUrl(String server, String path) {
    if (path.isEmpty) return '';
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    final base = normalizeServer(server);
    return path.startsWith('/') ? '$base$path' : '$base/$path';
  }
}
