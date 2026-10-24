import 'package:flutter/material.dart';

import '../../controllers/room_controller.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../models/player.dart';
import '../../widgets/common.dart';
import '../../widgets/sheets.dart';

class RosterTab extends StatelessWidget {
  const RosterTab({super.key, required this.controller});

  final RoomController controller;

  @override
  Widget build(BuildContext context) {
    final rows = controller.rosterRows;
    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
        children: <Widget>[
          _sideBar(context),
          if (controller.demoMessage != null)
            Padding(
              padding: const EdgeInsets.only(left: 2, top: 2),
              child: Text(
                controller.demoMessage!,
                style: const TextStyle(fontSize: 11, color: AppColors.muted),
              ),
            ),
          _seasonNotice(),
          const SizedBox(height: 12),
          if (rows.isEmpty)
            const EmptyCard('等待电脑端上报阵容…', icon: Icons.groups_2_outlined)
          else ...<Widget>[
            _teamBlock(rows, 'ct'),
            const SizedBox(height: 12),
            _teamBlock(rows, 't'),
          ],
          const SizedBox(height: 14),
          _membersCard(),
          if (controller.profiles.isNotEmpty)
            const Padding(
              padding: EdgeInsets.only(top: 10),
              child: Text(
                '数据来自队友电脑端上报 · 赛季值由服务端补全',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 10.5, color: AppColors.dim),
              ),
            ),
        ],
      ),
    );
  }

  Widget _sideBar(BuildContext context) {
    final canRemember =
        controller.mySide.isNotEmpty && controller.match?.mySideSource != 'library';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                controller.sideText,
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: controller.mySide.isEmpty ? AppColors.warn : AppColors.fgSecondary,
                ),
              ),
            ),
            TextButton(
              onPressed: () => showSideSheet(context, controller),
              child: const Text('选择阵营'),
            ),
          ],
        ),
        if (canRemember)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () async {
                final messenger = ScaffoldMessenger.of(context);
                try {
                  final count = await controller.rememberSide();
                  messenger.showSnackBar(
                    SnackBar(content: Text('已记住 $count 个 ID，下一局自动判断')),
                  );
                } catch (error) {
                  messenger.showSnackBar(SnackBar(content: Text('$error')));
                }
              },
              icon: const Icon(Icons.bookmark_add_outlined, size: 16),
              label: const Text('把我方这 5 人记进 ID 库'),
              style: TextButton.styleFrom(
                padding: EdgeInsets.zero,
                minimumSize: const Size(0, 30),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
          ),
        if (controller.identityMessage != null)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              controller.identityMessage!,
              style: const TextStyle(fontSize: 11, color: AppColors.ok),
            ),
          ),
      ],
    );
  }

  Widget _seasonNotice() {
    final match = controller.match;
    if (match == null) return const SizedBox.shrink();
    final warning = controller.seasonError;
    if (warning != null) return NoticeCard(warning);
    switch (match.homeState) {
      case 'signature':
        return NoticeCard(match.homeError ?? '5E 签名失效，赛季数据这次没拿到');
      case 'failed':
        return NoticeCard(match.homeError ?? '赛季数据拉取失败，仅用本场数据');
      case 'partial':
        return NoticeCard(
          '赛季数据补全 ${match.homeCoverage} 人，其余用本场数据',
          tone: NoticeTone.info,
        );
      case 'running':
        return const NoticeCard('正在拉取 5E 赛季数据…', tone: NoticeTone.info);
      case 'ready':
        if (match.homeCoverage > 0) {
          return NoticeCard('赛季数据已补全（${match.homeCoverage} 人）', tone: NoticeTone.info);
        }
        return const SizedBox.shrink();
      default:
        return const SizedBox.shrink();
    }
  }

  Widget _teamBlock(List<RosterRow> all, String side) {
    final rows = all.where((row) => row.side == side).toList()
      ..sort((a, b) => (b.seasonRating ?? 0).compareTo(a.seasonRating ?? 0));
    final ratings = rows.map((row) => row.seasonRating).whereType<double>().toList();
    final average = ratings.isEmpty
        ? null
        : ratings.reduce((a, b) => a + b) / ratings.length;
    final token = teamToken(side, controller.mySide);
    final title = teamTitle(side, controller.mySide);
    final color = token == 'A' ? AppColors.sideA : AppColors.sideB;

    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: cardDecoration(),
      child: Column(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            color: AppColors.elevated,
            child: Row(
              children: <Widget>[
                Text(
                  '${side.toUpperCase()} · $title',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color),
                ),
                const Spacer(),
                Text(
                  '${rows.length} 人${average == null ? '' : ' · 均 ${average.toStringAsFixed(2)}'}',
                  style: const TextStyle(fontSize: 11, color: AppColors.muted),
                ),
              ],
            ),
          ),
          if (rows.isEmpty)
            const Padding(
              padding: EdgeInsets.all(14),
              child: Text('暂无数据', style: TextStyle(fontSize: 12, color: AppColors.muted)),
            )
          else
            ...rows.asMap().entries.map(
                  (entry) => Column(
                    children: <Widget>[
                      if (entry.key > 0)
                        const Divider(height: 1, thickness: 1, color: Color(0xFFF1F5F9)),
                      _playerRow(entry.value),
                    ],
                  ),
                ),
        ],
      ),
    );
  }

  Widget _playerRow(RosterRow row) {
    final signal = controller.signalsBySteam[row.steamId];
    final stats = row.stats;
    final adr = stats.seasonAdr;
    final bits = <String>[
      'ADR ${adr == null ? '—' : adr.round()}',
      if (stats.seasonRws != null) 'RWS ${fmt(stats.seasonRws, 1)}',
      'K/D ${fmt(stats.kd)}',
      '爆头 ${pct(stats.headshotRate)}',
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      child: Row(
        children: <Widget>[
          PlayerAvatar(name: row.nickname, url: row.avatarUrl),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Flexible(
                      child: Text(
                        row.nickname,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                      ),
                    ),
                    if (row.isSelf) ...<Widget>[
                      const SizedBox(width: 4),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 0.5),
                        decoration: BoxDecoration(
                          color: AppColors.accentSoft,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: const Text(
                          '我',
                          style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: AppColors.accent),
                        ),
                      ),
                    ],
                    if (signal != null) ...<Widget>[
                      const SizedBox(width: 4),
                      SignalTag(signal.kind),
                    ],
                    const Spacer(),
                    RatingText(row.seasonRating),
                  ],
                ),
                const SizedBox(height: 2),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        bits.join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 11, color: AppColors.muted),
                      ),
                    ),
                    if (row.recentRating != null)
                      Padding(
                        padding: const EdgeInsets.only(left: 6),
                        child: Text(
                          '近期 ${fmt(row.recentRating)}',
                          style: const TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: AppColors.fgSecondary,
                          ),
                        ),
                      ),
                    ResultChips(stats.recentResults),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _membersCard() {
    final members = controller.members;
    Member? host;
    for (final member in members) {
      if (member.isPc) {
        host = member;
        break;
      }
    }
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text('房间成员', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          if (members.isEmpty)
            const Text('暂无成员', style: TextStyle(fontSize: 12, color: AppColors.muted))
          else
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: members.map((member) {
                final isHost = host != null && member.id == host.id;
                final suffix = isHost
                    ? ' · 房主'
                    : member.isPc
                        ? ' · 电脑'
                        : '';
                return Container(
                  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(color: AppColors.border),
                  ),
                  child: Text(
                    '${member.nickname}$suffix',
                    style: TextStyle(
                      fontSize: 11,
                      color: member.isOnline ? AppColors.fgSecondary : AppColors.dim,
                    ),
                  ),
                );
              }).toList(),
            ),
        ],
      ),
    );
  }
}
