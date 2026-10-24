import 'package:flutter/material.dart';

import '../../controllers/room_controller.dart';
import '../../core/theme.dart';
import '../../models/match.dart';
import '../../models/player.dart';
import '../../widgets/common.dart';
import '../replay_page.dart';

class PathsTab extends StatelessWidget {
  const PathsTab({super.key, required this.controller});

  final RoomController controller;

  @override
  Widget build(BuildContext context) {
    final players = controller.pathPlayers;
    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
        children: <Widget>[
          _statusCard(),
          if (controller.pathsLoading) ...<Widget>[
            const SizedBox(height: 10),
            const AppCard(
              child: Row(
                children: <Widget>[
                  SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                  SizedBox(width: 10),
                  Text('正在拉取轨迹索引…', style: TextStyle(fontSize: 12.5, color: AppColors.muted)),
                ],
              ),
            ),
          ],
          if (controller.pathsError != null) ...<Widget>[
            const SizedBox(height: 10),
            AppCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    controller.pathsError!,
                    style: const TextStyle(fontSize: 12.5, color: AppColors.bad, height: 1.5),
                  ),
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton(
                      onPressed: () {
                        final artifact = controller.artifactId;
                        if (artifact != null) controller.loadPaths(artifact);
                      },
                      child: const Text('重试'),
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (!controller.pathsLoading && controller.pathsError == null && players.isEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 10),
              child: EmptyCard(
                '轨迹还没出来。首次下载并解析对手录像需要 1–3 分钟，缓存命中约 20 秒。',
                icon: Icons.route_outlined,
              ),
            ),
          ...players.map((player) => Padding(
                padding: const EdgeInsets.only(top: 8),
                child: _playerRow(context, player),
              )),
        ],
      ),
    );
  }

  Widget _statusCard() {
    final match = controller.match;
    final count = controller.pathPlayers.length;
    String subtitle;
    if (controller.pathsLoading) {
      subtitle = '正在拉取轨迹索引…';
    } else if (count > 0) {
      subtitle = '已解析 $count 人，点一个看他的开局走位';
    } else if (match?.demoState == 'waiting') {
      subtitle = '等地图确认，确认后开始下载录像';
    } else if (match?.demoState == 'running') {
      subtitle = '正在下载并解析录像，首次 1–3 分钟';
    } else if (match?.demoState == 'failed') {
      subtitle = '录像解析失败，可以换一局或稍后重试';
    } else {
      subtitle = '这批对手没有可用的历史录像。';
    }

    return AppCard(
      child: Row(
        children: <Widget>[
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: AppColors.accentSoft,
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Icon(Icons.map_outlined, size: 19, color: AppColors.accent),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Text('对手开局走位', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(fontSize: 11.5, height: 1.5, color: AppColors.muted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  PlayerInfo? _mateFor(PathPlayer player) {
    for (final profile in controller.profiles) {
      if (player.steamId.isNotEmpty && profile.steamId == player.steamId) return profile;
      if (player.domain.isNotEmpty && profile.platformUserId == player.domain) return profile;
    }
    return null;
  }

  Widget _playerRow(BuildContext context, PathPlayer player) {
    final mate = _mateFor(player);
    final name = player.displayName;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => ReplayPage(controller: controller, player: player),
            ),
          );
        },
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: cardDecoration(),
          child: Row(
            children: <Widget>[
              PlayerAvatar(name: name, url: mate?.avatarUrl, size: 30),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 1),
                    Text(
                      '${player.rounds} 回合',
                      style: const TextStyle(fontSize: 11, color: AppColors.muted),
                    ),
                  ],
                ),
              ),
              const Text(
                '查看 ›',
                style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.accent),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
