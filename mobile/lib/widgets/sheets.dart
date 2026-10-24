import 'package:flutter/material.dart';

import '../controllers/room_controller.dart';
import '../core/theme.dart';
import '../services/api_client.dart';

Future<void> showSettingsSheet(BuildContext context, RoomController controller) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (_) => _SettingsSheet(controller: controller),
  );
}

class _SettingsSheet extends StatefulWidget {
  const _SettingsSheet({required this.controller});

  final RoomController controller;

  @override
  State<_SettingsSheet> createState() => _SettingsSheetState();
}

class _SettingsSheetState extends State<_SettingsSheet> {
  late final TextEditingController _server;
  late final TextEditingController _room;
  late final TextEditingController _nickname;
  String? _error;

  @override
  void initState() {
    super.initState();
    final controller = widget.controller;
    _server = TextEditingController(text: controller.serverUrl);
    _room = TextEditingController(text: controller.roomCode);
    _nickname = TextEditingController(text: controller.nickname);
  }

  @override
  void dispose() {
    _server.dispose();
    _room.dispose();
    _nickname.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (_server.text.trim().isEmpty) {
      setState(() => _error = '服务端地址不能为空');
      return;
    }
    final navigator = Navigator.of(context);
    final controller = widget.controller;
    navigator.pop();
    await controller.updateConnection(
      server: _server.text,
      room: _room.text,
      nick: _nickname.text,
    );
  }

  Future<void> _leave() async {
    final navigator = Navigator.of(context);
    final controller = widget.controller;
    navigator.pop();
    await controller.leaveRoom();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 18,
        right: 18,
        top: 18,
        bottom: 18 + MediaQuery.of(context).viewInsets.bottom,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            const Text('连接设置', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 4),
            const Text(
              '换地址或房间后会重新加入，旧 token 会被丢弃。',
              style: TextStyle(fontSize: 11.5, color: AppColors.muted, height: 1.5),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _server,
              keyboardType: TextInputType.url,
              autocorrect: false,
              decoration: fieldDecoration(labelText: '服务端地址', hintText: 'http://192.168.3.46:8787'),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _room,
              textCapitalization: TextCapitalization.characters,
              decoration: fieldDecoration(labelText: '房间码', hintText: 'MAIN'),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _nickname,
              decoration: fieldDecoration(labelText: '昵称', hintText: '队友'),
            ),
            if (_error != null) ...<Widget>[
              const SizedBox(height: 8),
              Text(_error!, style: const TextStyle(fontSize: 12, color: AppColors.bad)),
            ],
            const SizedBox(height: 16),
            SizedBox(
              height: 46,
              child: FilledButton(onPressed: _save, child: const Text('保存并重新加入')),
            ),
            const SizedBox(height: 6),
            TextButton(
              onPressed: _leave,
              style: TextButton.styleFrom(foregroundColor: AppColors.bad),
              child: const Text('退出房间'),
            ),
          ],
        ),
      ),
    );
  }
}

Future<void> showSideSheet(BuildContext context, RoomController controller) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.surface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
    ),
    builder: (_) => _SideSheet(controller: controller),
  );
}

class _SideSheet extends StatefulWidget {
  const _SideSheet({required this.controller});

  final RoomController controller;

  @override
  State<_SideSheet> createState() => _SideSheetState();
}

class _SideSheetState extends State<_SideSheet> {
  bool _busy = false;
  String? _error;

  String _names(String side) {
    final teams = widget.controller.match?.teams;
    if (teams == null) return '名单还没到';
    final names = teams
        .forSide(side)
        .map((player) => player.nickname)
        .where((name) => name.isNotEmpty)
        .take(5)
        .toList();
    return names.isEmpty ? '名单还没到' : names.join('、');
  }

  Future<void> _choose(String? side) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.controller.chooseSide(side);
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = error.message;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = '$error';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final match = widget.controller.match;
    final side = widget.controller.mySide;
    return Padding(
      padding: EdgeInsets.only(
        left: 18,
        right: 18,
        top: 18,
        bottom: 18 + MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const Text('我们在哪边？', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text(
            '只下载对面的历史录像，能省掉一半等待时间。认不出来就先选「都看」。',
            style: TextStyle(fontSize: 11.5, color: AppColors.muted, height: 1.55),
          ),
          const SizedBox(height: 14),
          _option(
            title: '我方是 CT',
            subtitle: _names('ct'),
            color: AppColors.sideA,
            selected: side == 'ct',
            onTap: () => _choose('ct'),
          ),
          const SizedBox(height: 8),
          _option(
            title: '我方是 T',
            subtitle: _names('t'),
            color: AppColors.sideB,
            selected: side == 't',
            onTap: () => _choose('t'),
          ),
          const SizedBox(height: 8),
          _option(
            title: '都看（十人）',
            subtitle: '十个人都下载录像，首次会慢一倍',
            color: AppColors.muted,
            selected: side.isEmpty,
            onTap: () => _choose(null),
          ),
          if (match == null)
            const Padding(
              padding: EdgeInsets.only(top: 10),
              child: Text(
                '对局还没上报，先等电脑端识别到比赛。',
                style: TextStyle(fontSize: 11.5, color: AppColors.warn),
              ),
            ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text(_error!, style: const TextStyle(fontSize: 12, color: AppColors.bad)),
            ),
          if (_busy)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Center(
                child: SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
              ),
            ),
        ],
      ),
    );
  }

  Widget _option({
    required String title,
    required String subtitle,
    required Color color,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: _busy ? null : onTap,
      borderRadius: BorderRadius.circular(10),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: selected ? AppColors.accentSoft : AppColors.elevated,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: selected ? AppColors.accent : AppColors.border),
        ),
        child: Row(
          children: <Widget>[
            Container(
              width: 3,
              height: 28,
              decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(999)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 11.5, color: AppColors.muted),
                  ),
                ],
              ),
            ),
            if (selected) const Icon(Icons.check_circle, size: 18, color: AppColors.accent),
          ],
        ),
      ),
    );
  }
}

/// 让调用方在设置面板里也能拿到格式化后的房间码。
String roomLabel(String code) => code.isEmpty ? '----' : code.toUpperCase();
