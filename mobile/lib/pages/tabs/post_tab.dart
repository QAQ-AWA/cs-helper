import 'package:flutter/material.dart';

import '../../controllers/room_controller.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../models/post_match.dart';
import '../../widgets/common.dart';

class PostTab extends StatelessWidget {
  const PostTab({super.key, required this.controller});

  final RoomController controller;

  @override
  Widget build(BuildContext context) {
    final report = controller.match?.postReport;
    if (report == null) {
      return RefreshIndicator(
        onRefresh: controller.refresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
          children: const <Widget>[
            EmptyCard('这局还没有赛后数据', icon: Icons.scoreboard_outlined),
            SizedBox(height: 10),
            Text(
              '赛后战报由电脑端从 5E 拉取后上报，手机只负责展示。打完一局回到电脑端点「拉取战报」即可。',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 11, height: 1.6, color: AppColors.dim),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
        children: <Widget>[
          _scoreCard(report),
          const SizedBox(height: 12),
          _teamCard('A', report.playersFor(1)),
          const SizedBox(height: 12),
          _teamCard('B', report.playersFor(2)),
          if (!report.isFinished) ...<Widget>[
            const SizedBox(height: 12),
            const NoticeCard('对局还没结束，比分与数据会继续更新。'),
          ],
        ],
      ),
    );
  }

  Widget _scoreCard(PostMatchReport report) {
    final winner = report.winnerSide;
    final winnerText = winner == 'Draw'
        ? '平局'
        : winner == 'A'
            ? 'A 队胜'
            : winner == 'B'
                ? 'B 队胜'
                : '';
    final half = report.halfScores;
    final headline = report.comparison?.headline;

    return AppCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              Text(
                '${report.scoreA} : ${report.scoreB}',
                style: const TextStyle(
                  fontSize: 28,
                  height: 1,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.6,
                ),
              ),
              const SizedBox(width: 10),
              if (winnerText.isNotEmpty) Pill(winnerText, color: AppColors.fgSecondary),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            half != null
                ? '半场 ${half.fhA}:${half.fhB} · ${half.shA}:${half.shB}'
                : '${report.roundTotal} 回合',
            style: const TextStyle(fontSize: 11.5, color: AppColors.muted),
          ),
          if (headline != null && headline.isNotEmpty) ...<Widget>[
            const SizedBox(height: 6),
            Text(
              headline,
              style: const TextStyle(fontSize: 12, height: 1.5, color: AppColors.fgSecondary),
            ),
          ],
        ],
      ),
    );
  }

  Widget _teamCard(String side, List<PostPlayer> players) {
    final color = side == 'A' ? AppColors.sideA : AppColors.sideB;
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: cardDecoration(),
      child: Column(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            color: AppColors.elevated,
            child: Row(
              children: <Widget>[
                Text(
                  '$side 队',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: color),
                ),
                const Spacer(),
                const SizedBox(
                  width: 64,
                  child: Text(
                    'K/D/A',
                    textAlign: TextAlign.right,
                    style: TextStyle(fontSize: 10, color: AppColors.dim),
                  ),
                ),
                const SizedBox(
                  width: 44,
                  child: Text(
                    'Rating',
                    textAlign: TextAlign.right,
                    style: TextStyle(fontSize: 10, color: AppColors.dim),
                  ),
                ),
                const SizedBox(
                  width: 40,
                  child: Text(
                    'ADR',
                    textAlign: TextAlign.right,
                    style: TextStyle(fontSize: 10, color: AppColors.dim),
                  ),
                ),
              ],
            ),
          ),
          if (players.isEmpty)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Text('—', style: TextStyle(fontSize: 12, color: AppColors.muted)),
            )
          else
            ...players.asMap().entries.map(
                  (entry) => Column(
                    children: <Widget>[
                      if (entry.key > 0)
                        const Divider(height: 1, thickness: 1, color: Color(0xFFF1F5F9)),
                      _row(entry.value),
                    ],
                  ),
                ),
        ],
      ),
    );
  }

  Widget _row(PostPlayer player) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Wrap(
              spacing: 4,
              runSpacing: 2,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: <Widget>[
                Text(
                  player.nickname,
                  style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
                ),
                if (player.isMvp) const _Badge('MVP', Color(0xFFB45309), Color(0xFFFFFBEB)),
                if (player.isSvp) const _Badge('SVP', Color(0xFF0369A1), Color(0xFFF0F9FF)),
              ],
            ),
          ),
          SizedBox(
            width: 64,
            child: Text(
              '${player.kill}/${player.death}/${player.assist}',
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 12, color: AppColors.fgSecondary),
            ),
          ),
          SizedBox(
            width: 44,
            child: Text(
              fmt(player.rating),
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.fgSecondary),
            ),
          ),
          SizedBox(
            width: 40,
            child: Text(
              player.adr == null ? '—' : '${player.adr!.round()}',
              textAlign: TextAlign.right,
              style: const TextStyle(fontSize: 12, color: AppColors.fgSecondary),
            ),
          ),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge(this.text, this.color, this.background);

  final String text;
  final Color color;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 0.5),
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(3)),
      child: Text(
        text,
        style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }
}
