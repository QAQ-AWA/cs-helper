import 'package:flutter/material.dart';

import '../controllers/room_controller.dart';
import '../core/format.dart';
import '../core/theme.dart';
import '../widgets/sheets.dart';
import 'tabs/analysis_tab.dart';
import 'tabs/paths_tab.dart';
import 'tabs/post_tab.dart';
import 'tabs/roster_tab.dart';

class RoomPage extends StatelessWidget {
  const RoomPage({super.key, required this.controller});

  final RoomController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return Scaffold(
          body: SafeArea(
            bottom: false,
            child: Column(
              children: <Widget>[
                _TopBar(controller: controller),
                _TabBar(controller: controller),
                Expanded(
                  child: IndexedStack(
                    index: controller.activeTab,
                    children: <Widget>[
                      RosterTab(controller: controller),
                      AnalysisTab(controller: controller),
                      PathsTab(controller: controller),
                      PostTab(controller: controller),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.controller});

  final RoomController controller;

  @override
  Widget build(BuildContext context) {
    final match = controller.match;
    final seconds = match?.countdownSeconds ?? 0;

    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 4, 10),
      decoration: const BoxDecoration(
        color: AppColors.bg,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Text(
                      roomLabel(controller.roomCode),
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 1.1,
                      ),
                    ),
                    if (seconds > 0) ...<Widget>[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
                        decoration: BoxDecoration(
                          color: AppColors.accentSoft,
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          '准备 ${seconds}s',
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: AppColors.accent,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  mapLabel(match?.mapName),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppColors.fgSecondary,
                  ),
                ),
              ],
            ),
          ),
          _ConnectionBadge(controller: controller),
          PopupMenuButton<String>(
            icon: const Icon(Icons.more_horiz, size: 21),
            tooltip: '更多',
            onSelected: (value) async {
              if (value == 'refresh') {
                await controller.refresh();
              } else if (value == 'settings') {
                await showSettingsSheet(context, controller);
              } else if (value == 'leave') {
                await controller.leaveRoom();
              }
            },
            itemBuilder: (context) => const <PopupMenuEntry<String>>[
              PopupMenuItem<String>(value: 'refresh', child: Text('刷新快照')),
              PopupMenuItem<String>(value: 'settings', child: Text('连接设置')),
              PopupMenuItem<String>(
                value: 'leave',
                child: Text('退出房间', style: TextStyle(color: AppColors.bad)),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ConnectionBadge extends StatelessWidget {
  const _ConnectionBadge({required this.controller});

  final RoomController controller;

  @override
  Widget build(BuildContext context) {
    final color = switch (controller.conn) {
      ConnState.connected => AppColors.ok,
      ConnState.connecting => AppColors.warn,
      ConnState.disconnected => AppColors.warn,
      ConnState.idle => AppColors.dim,
    };
    return Tooltip(
      message: '点一下重连',
      child: InkWell(
        onTap: controller.connect,
        borderRadius: BorderRadius.circular(999),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Container(
                width: 7,
                height: 7,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: color,
                  boxShadow: controller.conn == ConnState.connected
                      ? const <BoxShadow>[BoxShadow(color: AppColors.okSoft, spreadRadius: 3)]
                      : null,
                ),
              ),
              const SizedBox(width: 5),
              Text(
                controller.connHint,
                style: const TextStyle(fontSize: 11, color: AppColors.muted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TabBar extends StatelessWidget {
  const _TabBar({required this.controller});

  final RoomController controller;

  static const _labels = <String>['阵容', '分析', '轨迹', '赛后'];

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      decoration: const BoxDecoration(
        color: AppColors.bg,
        border: Border(bottom: BorderSide(color: AppColors.border)),
      ),
      child: Row(
        children: List<Widget>.generate(_labels.length, (index) {
          final on = controller.activeTab == index;
          final fresh = controller.freshTabs.contains(index);
          return Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: Material(
                color: on ? AppColors.surface : Colors.transparent,
                borderRadius: BorderRadius.circular(999),
                child: InkWell(
                  borderRadius: BorderRadius.circular(999),
                  onTap: () => controller.selectTab(index),
                  child: Container(
                    padding: const EdgeInsets.symmetric(vertical: 7),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: on ? AppColors.border : Colors.transparent,
                      ),
                      boxShadow: on ? appShadow : null,
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: <Widget>[
                        Text(
                          _labels[index],
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            color: on ? AppColors.fg : AppColors.muted,
                          ),
                        ),
                        if (fresh) ...<Widget>[
                          const SizedBox(width: 4),
                          Container(
                            width: 5,
                            height: 5,
                            decoration: const BoxDecoration(
                              color: AppColors.accent,
                              shape: BoxShape.circle,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ),
          );
        }),
      ),
    );
  }
}
