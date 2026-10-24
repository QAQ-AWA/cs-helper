import 'package:flutter/material.dart';

import '../../controllers/room_controller.dart';
import '../../core/format.dart';
import '../../core/theme.dart';
import '../../models/analysis.dart';
import '../../models/match.dart';
import '../../widgets/common.dart';
import '../../widgets/markdown_text.dart';

class AnalysisTab extends StatelessWidget {
  const AnalysisTab({super.key, required this.controller});

  final RoomController controller;

  static const _dimLabels = <String, String>{
    'strength': '整体实力',
    'aim': '枪法',
    'opening': '首杀',
    'utility': '道具',
    'clutch': '残局',
    'map': '地图',
    'form': '状态',
    'party': '组排',
  };

  @override
  Widget build(BuildContext context) {
    final match = controller.match;
    final result = match?.aiResult;
    final children = <Widget>[];

    if (result != null) {
      children.addAll(_analysisWidgets(result));
    } else {
      children.add(_fallbackCard());
    }

    if (match != null) {
      children.add(const SizedBox(height: 14));
      children.add(_tacticsCard(match));
      children.add(const SizedBox(height: 10));
      children.add(_rerunButton(context));
    }

    return RefreshIndicator(
      onRefresh: controller.refresh,
      child: ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 28),
        children: children,
      ),
    );
  }

  Widget _fallbackCard() {
    if (controller.aiError != null) {
      return EmptyCard(controller.aiError!, icon: Icons.error_outline);
    }
    if (controller.aiPreview != null) {
      return AppCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Text('AI 战术分析', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            MarkdownText(controller.aiPreview!),
          ],
        ),
      );
    }
    if (controller.match?.aiText != null) {
      return AppCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            const Text('AI 战术分析', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            MarkdownText(controller.match!.aiText!),
          ],
        ),
      );
    }
    if (controller.aiProgress != null) {
      return AppCard(
        child: Row(
          children: <Widget>[
            const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                controller.aiProgress!,
                style: const TextStyle(fontSize: 12.5, color: AppColors.muted),
              ),
            ),
          ],
        ),
      );
    }

    final match = controller.match;
    final wait = match?.aiWait ?? const <String>[];
    final label = match?.aiState == 'running'
        ? 'AI 正在分析这局…'
        : wait.isNotEmpty
            ? '${wait.join(' · ')}，到位后自动生成'
            : match?.aiState == 'waiting'
                ? '等地图确认，到位后自动生成'
                : '等待电脑端上报数据…';
    return EmptyCard(label, icon: Icons.auto_awesome);
  }

  List<Widget> _analysisWidgets(AnalysisResult result) {
    final widgets = <Widget>[_hero(result)];

    if (result.factors.isNotEmpty) {
      widgets.add(const SizedBox(height: 14));
      widgets.add(const SectionTitle('决定本局的因素'));
      for (final factor in result.factors) {
        widgets.add(Padding(padding: const EdgeInsets.only(top: 8), child: _factorCard(factor)));
      }
    }

    if (result.signals.isNotEmpty) {
      final positive = result.signals
          .where((signal) => const <String>['carry', 'anchor', 'specialist'].contains(signal.kind))
          .toList();
      final negative = result.signals.where((signal) => signal.kind == 'weakLink').toList();
      final volatile = result.signals
          .where((signal) => !const <String>['carry', 'anchor', 'specialist', 'weakLink'].contains(signal.kind))
          .toList();

      widgets.add(const SizedBox(height: 14));
      widgets.add(const SectionTitle('玩家信号'));
      for (final signal in <PlayerSignal>[...positive, ...negative, ...volatile]) {
        final tone = positive.contains(signal)
            ? _SignalTone.positive
            : negative.contains(signal)
                ? _SignalTone.negative
                : _SignalTone.neutral;
        widgets.add(Padding(padding: const EdgeInsets.only(top: 8), child: _signalCard(signal, tone)));
      }
    }

    final planA = result.planFor('A');
    final planB = result.planFor('B');
    if (!planA.isEmpty || !planB.isEmpty) {
      widgets.add(const SizedBox(height: 14));
      widgets.add(const SectionTitle('双方取胜路径'));
      if (!planA.isEmpty) {
        widgets.add(Padding(padding: const EdgeInsets.only(top: 8), child: _planCard('A', planA)));
      }
      if (!planB.isEmpty) {
        widgets.add(Padding(padding: const EdgeInsets.only(top: 8), child: _planCard('B', planB)));
      }
    }

    if (result.uncertainties.isNotEmpty) {
      widgets.add(const SizedBox(height: 14));
      widgets.add(const SectionTitle('数据边界'));
      widgets.add(
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: AppColors.warnSoft,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: const Color(0xFFFDE68A)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text(
                '这份结论的可信范围',
                style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: AppColors.warn),
              ),
              const SizedBox(height: 4),
              ...result.uncertainties.map(
                (text) => Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    '· ${persp(text, controller.mySide)}',
                    style: const TextStyle(fontSize: 12, height: 1.5, color: Color(0xFF78350F)),
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    return widgets;
  }

  Widget _hero(AnalysisResult result) {
    final mySide = controller.mySide;
    final winner = result.predictedWinner;
    final verdict = winner == 'Even'
        ? '双方势均力敌'
        : (winner == 'A' || winner == 'B')
            ? '${sideName(winner, mySide)}略占优势'
            : '暂难判断';
    final winA = result.winA.round().clamp(0, 100).toInt();
    final winB = result.winB.round().clamp(0, 100).toInt();

    return AppCard(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Wrap(
            spacing: 6,
            runSpacing: 6,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: <Widget>[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.accentSoft,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  verdict,
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.accent),
                ),
              ),
              Pill('可信度 ${result.confidence}'),
              Pill('覆盖 ${(result.dataCoverage * 100).round()}%'),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            persp(result.headline, mySide),
            style: const TextStyle(fontSize: 16, height: 1.45, fontWeight: FontWeight.w700, letterSpacing: -0.1),
          ),
          const SizedBox(height: 14),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: <Widget>[
              Text(
                sideName('A', mySide),
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.sideA),
              ),
              const SizedBox(width: 6),
              Text(
                '$winA%',
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, height: 1),
              ),
              const Spacer(),
              Text(
                '$winB%',
                style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, height: 1),
              ),
              const SizedBox(width: 6),
              Text(
                sideName('B', mySide),
                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppColors.sideB),
              ),
            ],
          ),
          const SizedBox(height: 6),
          SizedBox(
            height: 8,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(999),
              child: Row(
                children: <Widget>[
                  Expanded(
                    flex: winA == 0 ? 1 : winA,
                    child: Container(color: AppColors.sideA),
                  ),
                  Expanded(
                    flex: winB == 0 ? 1 : winB,
                    child: Container(color: AppColors.sideB),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _factorCard(DecisiveFactor factor) {
    final advantage = factor.advantage;
    final isA = advantage == 'A';
    final isB = advantage == 'B';
    final color = isA
        ? AppColors.sideA
        : isB
            ? AppColors.sideB
            : AppColors.muted;
    final background = isA
        ? AppColors.sideASoft
        : isB
            ? AppColors.sideBSoft
            : AppColors.elevated;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: <Widget>[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(
                  color: AppColors.elevated,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  _dimLabels[factor.dimension] ?? '综合',
                  style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700, color: AppColors.fgSecondary),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(4)),
                child: Text(
                  sideName(advantage, controller.mySide),
                  style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700, color: color),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            persp(factor.title, controller.mySide),
            style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w700, height: 1.4),
          ),
          const SizedBox(height: 2),
          Text(
            persp(factor.summary, controller.mySide),
            style: const TextStyle(fontSize: 12.5, height: 1.55, color: AppColors.fgSecondary),
          ),
        ],
      ),
    );
  }

  Widget _signalCard(PlayerSignal signal, _SignalTone tone) {
    final barColor = tone == _SignalTone.positive
        ? const Color(0xFF22C55E)
        : tone == _SignalTone.negative
            ? const Color(0xFFF87171)
            : AppColors.borderStrong;
    final sideColor = signal.side == 'A' ? AppColors.sideA : AppColors.sideB;

    return Container(
      decoration: cardDecoration(),
      padding: const EdgeInsets.all(12),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Container(
              width: 3,
              decoration: BoxDecoration(color: barColor, borderRadius: BorderRadius.circular(999)),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Wrap(
                    spacing: 6,
                    runSpacing: 3,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: <Widget>[
                      Text(
                        signal.nickname,
                        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
                      ),
                      Text(
                        sideName(signal.side, controller.mySide),
                        style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: sideColor),
                      ),
                      SignalTag(signal.kind),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(
                    '${persp(signal.title, controller.mySide)}：${persp(signal.summary, controller.mySide)}',
                    style: const TextStyle(fontSize: 12, height: 1.55, color: AppColors.fgSecondary),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _planCard(String side, TeamPlan plan) {
    final color = side == 'A' ? AppColors.sideA : AppColors.sideB;
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            sideName(side, controller.mySide),
            style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: color),
          ),
          if (plan.winConditions.isNotEmpty) ...<Widget>[
            const _PlanLabel('取胜条件'),
            ...plan.winConditions.map((item) => _bullet(item.text)),
          ],
          if (plan.risks.isNotEmpty) ...<Widget>[
            const _PlanLabel('主要隐患'),
            ...plan.risks.map((item) => _bullet(item.text)),
          ],
        ],
      ),
    );
  }

  Widget _bullet(String text) {
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text('·', style: TextStyle(fontSize: 12.5, color: AppColors.dim, height: 1.5)),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              persp(text, controller.mySide),
              style: const TextStyle(fontSize: 12.5, height: 1.5, color: AppColors.fgSecondary),
            ),
          ),
        ],
      ),
    );
  }

  Widget _tacticsCard(MatchSession match) {
    final text = match.tacticsText;
    final progress = controller.tacticsProgress;
    final running = progress != null || match.tacticsState == 'running';
    final hint = match.tacticsState == 'failed'
        ? '开局预判生成失败，可点下方「重新分析」再试一次'
        : match.demoState == 'waiting'
            ? '等地图确认后开始下载录像'
            : '轨迹就绪后自动生成';

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.route_outlined, size: 17, color: AppColors.accent),
              const SizedBox(width: 6),
              const Text('开局预判', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700)),
              const Spacer(),
              if (running)
                const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
            ],
          ),
          const SizedBox(height: 8),
          if (text != null && text.isNotEmpty)
            MarkdownText(text)
          else
            Text(
              progress ?? hint,
              style: const TextStyle(fontSize: 12, height: 1.55, color: AppColors.muted),
            ),
        ],
      ),
    );
  }

  Widget _rerunButton(BuildContext context) {
    final running = controller.aiProgress != null;
    return SizedBox(
      height: 44,
      child: OutlinedButton.icon(
        onPressed: running
            ? null
            : () async {
                final messenger = ScaffoldMessenger.of(context);
                try {
                  await controller.rerunAnalysis();
                  messenger.showSnackBar(const SnackBar(content: Text('已提交重新分析')));
                } catch (error) {
                  messenger.showSnackBar(SnackBar(content: Text('$error')));
                }
              },
        icon: const Icon(Icons.refresh, size: 18),
        label: Text(running ? '分析中…' : '重新分析'),
      ),
    );
  }
}

enum _SignalTone { positive, negative, neutral }

class _PlanLabel extends StatelessWidget {
  const _PlanLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text(
        text,
        style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700, color: AppColors.dim),
      ),
    );
  }
}
