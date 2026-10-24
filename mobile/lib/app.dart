import 'package:flutter/material.dart';

import 'controllers/room_controller.dart';
import 'core/theme.dart';
import 'pages/join_page.dart';
import 'pages/room_page.dart';
import 'services/api_client.dart';
import 'services/settings_store.dart';

class CsHelperApp extends StatefulWidget {
  const CsHelperApp({super.key});

  @override
  State<CsHelperApp> createState() => _CsHelperAppState();
}

class _CsHelperAppState extends State<CsHelperApp> {
  late final ApiClient _api = ApiClient();
  late final SettingsStore _store = SettingsStore();
  late final RoomController _controller = RoomController(api: _api, store: _store);

  @override
  void initState() {
    super.initState();
    _controller.boot();
  }

  @override
  void dispose() {
    _controller.dispose();
    _api.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'CS Helper',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          if (_controller.booting) return const _SplashPage();
          if (!_controller.hasToken) return JoinPage(controller: _controller);
          return RoomPage(controller: _controller);
        },
      ),
    );
  }
}

class _SplashPage extends StatelessWidget {
  const _SplashPage();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(Icons.gps_fixed, size: 38, color: AppColors.accent),
            SizedBox(height: 12),
            Text(
              'CS Helper',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            SizedBox(height: 16),
            SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          ],
        ),
      ),
    );
  }
}
