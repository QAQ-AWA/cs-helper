import 'package:flutter/material.dart';

import '../controllers/room_controller.dart';
import '../core/theme.dart';
import '../services/api_client.dart';
import '../widgets/common.dart';

class JoinPage extends StatefulWidget {
  const JoinPage({super.key, required this.controller});

  final RoomController controller;

  @override
  State<JoinPage> createState() => _JoinPageState();
}

class _JoinPageState extends State<JoinPage> {
  late final TextEditingController _server;
  late final TextEditingController _room;
  late final TextEditingController _nickname;
  String? _localError;
  String? _probeResult;
  bool _probing = false;

  @override
  void initState() {
    super.initState();
    final controller = widget.controller;
    _server = TextEditingController(text: controller.serverUrl);
    _room = TextEditingController(text: controller.roomCode);
    _nickname = TextEditingController(
      text: controller.nickname.isEmpty ? '队友' : controller.nickname,
    );
  }

  @override
  void dispose() {
    _server.dispose();
    _room.dispose();
    _nickname.dispose();
    super.dispose();
  }

  Future<void> _probe() async {
    FocusScope.of(context).unfocus();
    setState(() {
      _probing = true;
      _probeResult = null;
      _localError = null;
    });
    try {
      final message = await widget.controller.probeServer(_server.text);
      if (!mounted) return;
      setState(() => _probeResult = message);
    } on ApiException catch (error) {
      if (!mounted) return;
      setState(() => _localError = error.message);
    } catch (error) {
      if (!mounted) return;
      setState(() => _localError = '检测失败：$error');
    } finally {
      if (mounted) setState(() => _probing = false);
    }
  }

  Future<void> _join() async {
    FocusScope.of(context).unfocus();
    setState(() {
      _localError = null;
      _probeResult = null;
    });
    if (_server.text.trim().isEmpty) {
      setState(() => _localError = '请填写电脑端的服务端地址');
      return;
    }
    await widget.controller.joinRoom(
      server: _server.text,
      room: _room.text,
      nick: _nickname.text,
    );
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final error = _localError ?? controller.joinError;
    final busy = controller.joining;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 28),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Container(
                        width: 46,
                        height: 46,
                        decoration: BoxDecoration(
                          color: AppColors.accent,
                          borderRadius: BorderRadius.circular(13),
                          boxShadow: appShadow,
                        ),
                        child: const Icon(Icons.gps_fixed, color: Colors.white, size: 26),
                      ),
                      const SizedBox(width: 12),
                      const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            'CS Helper',
                            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -0.4),
                          ),
                          SizedBox(height: 1),
                          Text(
                            'CS2 开黑辅助 · 赛前情报',
                            style: TextStyle(fontSize: 12, color: AppColors.muted),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const SizedBox(height: 26),
                  AppCard(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        const Text(
                          '连接电脑端',
                          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          '手机与电脑要在同一个 Wi-Fi。地址在电脑端「设置 → 同步」里。',
                          style: TextStyle(fontSize: 11.5, height: 1.55, color: AppColors.muted),
                        ),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _server,
                          keyboardType: TextInputType.url,
                          textInputAction: TextInputAction.next,
                          autocorrect: false,
                          decoration: fieldDecoration(
                            hintText: 'http://192.168.3.46:8787',
                            labelText: '服务端地址',
                            suffixIcon: const Icon(Icons.dns_outlined, size: 19, color: AppColors.dim),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Expanded(
                              child: TextField(
                                controller: _room,
                                textCapitalization: TextCapitalization.characters,
                                textInputAction: TextInputAction.next,
                                decoration: fieldDecoration(
                                  hintText: '例如 MAIN',
                                  labelText: '房间码（单房间可留空）',
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            SizedBox(
                              height: 50,
                              child: OutlinedButton(
                                onPressed: _probing ? null : _probe,
                                child: _probing
                                    ? const SizedBox(
                                        width: 14,
                                        height: 14,
                                        child: CircularProgressIndicator(strokeWidth: 2),
                                      )
                                    : const Text('检测'),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        TextField(
                          controller: _nickname,
                          textInputAction: TextInputAction.done,
                          onSubmitted: (_) {
                            if (!busy) _join();
                          },
                          decoration: fieldDecoration(
                            hintText: '队友',
                            labelText: '昵称',
                          ),
                        ),
                        if (_probeResult != null) ...<Widget>[
                          const SizedBox(height: 10),
                          Text(
                            _probeResult!,
                            style: const TextStyle(fontSize: 11.5, color: AppColors.ok, height: 1.5),
                          ),
                        ],
                        if (error != null && error.isNotEmpty) ...<Widget>[
                          const SizedBox(height: 10),
                          Text(
                            error,
                            style: const TextStyle(fontSize: 12, color: AppColors.bad, height: 1.5),
                          ),
                        ],
                        const SizedBox(height: 16),
                        SizedBox(
                          height: 48,
                          child: FilledButton(
                            onPressed: busy ? null : _join,
                            child: busy
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                    ),
                                  )
                                : const Text('进入房间'),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  const Text(
                    '房间码由电脑端创建；进入后阵容、分析、轨迹会自动同步。',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 11, color: AppColors.dim, height: 1.6),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
