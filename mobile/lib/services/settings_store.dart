import 'package:shared_preferences/shared_preferences.dart';

class SavedSettings {
  const SavedSettings({
    required this.serverUrl,
    required this.roomCode,
    required this.nickname,
  });

  final String serverUrl;
  final String roomCode;
  final String nickname;
}

/// 本地只存三件事：服务端地址、房间码、昵称，以及每个房间的 token。
class SettingsStore {
  static const _serverKey = 'cs.server';
  static const _roomKey = 'cs.room';
  static const _nicknameKey = 'cs.nickname';

  String _tokenKey(String server, String room) => 'cs.token::$server::$room';

  Future<SavedSettings> load() async {
    final prefs = await SharedPreferences.getInstance();
    return SavedSettings(
      serverUrl: prefs.getString(_serverKey) ?? '',
      roomCode: prefs.getString(_roomKey) ?? '',
      nickname: prefs.getString(_nicknameKey) ?? '',
    );
  }

  Future<void> saveConnection({
    required String serverUrl,
    required String roomCode,
    required String nickname,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_serverKey, serverUrl);
    await prefs.setString(_roomKey, roomCode);
    await prefs.setString(_nicknameKey, nickname);
  }

  Future<String?> tokenFor(String server, String room) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_tokenKey(server, room));
  }

  Future<void> saveToken(String server, String room, String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey(server, room), token);
  }

  Future<void> clearToken(String server, String room) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey(server, room));
  }
}
