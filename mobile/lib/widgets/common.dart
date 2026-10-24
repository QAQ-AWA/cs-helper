import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/theme.dart';

class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(14),
    this.color,
    this.borderColor,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? color;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: cardDecoration(color: color, borderColor: borderColor),
      child: child,
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 2, left: 2),
      child: Text(
        text,
        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.fg),
      ),
    );
  }
}

class Pill extends StatelessWidget {
  const Pill(
    this.text, {
    super.key,
    this.color = AppColors.fgSecondary,
    this.background = AppColors.elevated,
  });

  final String text;
  final Color color;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: color,
          fontFeatures: const [FontFeature.tabularFigures()],
        ),
      ),
    );
  }
}

class EmptyCard extends StatelessWidget {
  const EmptyCard(this.text, {super.key, this.icon});

  final String text;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 30),
      child: Column(
        children: <Widget>[
          if (icon != null) ...<Widget>[
            Icon(icon, size: 26, color: AppColors.dim),
            const SizedBox(height: 8),
          ],
          Text(
            text,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 12.5, color: AppColors.muted, height: 1.6),
          ),
        ],
      ),
    );
  }
}

class PlayerAvatar extends StatelessWidget {
  const PlayerAvatar({
    super.key,
    required this.name,
    this.url,
    this.size = 28,
  });

  final String name;
  final String? url;
  final double size;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(size * 0.27);
    final fallback = Container(
      color: AppColors.elevated,
      alignment: Alignment.center,
      child: Text(
        initialOf(name),
        style: TextStyle(
          fontSize: size * 0.4,
          fontWeight: FontWeight.w700,
          color: AppColors.muted,
        ),
      ),
    );
    return SizedBox(
      width: size,
      height: size,
      child: ClipRRect(
        borderRadius: radius,
        child: url == null || url!.isEmpty
            ? fallback
            : Image.network(
                url!,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => fallback,
                loadingBuilder: (context, child, progress) =>
                    progress == null ? child : fallback,
              ),
      ),
    );
  }
}

class ResultChips extends StatelessWidget {
  const ResultChips(this.raw, {super.key});

  final String? raw;

  @override
  Widget build(BuildContext context) {
    final flags = recentFlags(raw);
    if (flags.isEmpty) return const SizedBox.shrink();
    Color colorFor(String flag) {
      if (flag == 'W') return const Color(0xFF22C55E);
      if (flag == 'L') return const Color(0xFFF87171);
      return AppColors.dim;
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: flags
          .map(
            (flag) => Container(
              width: 12,
              height: 12,
              margin: const EdgeInsets.only(left: 2),
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: colorFor(flag),
                borderRadius: BorderRadius.circular(3),
              ),
              child: Text(
                flag,
                style: const TextStyle(
                  fontSize: 8,
                  height: 1,
                  fontWeight: FontWeight.w700,
                  color: Colors.white,
                ),
              ),
            ),
          )
          .toList(),
    );
  }
}

const signalLabels = <String, String>{
  'carry': '强点',
  'anchor': '支点',
  'specialist': '专长',
  'weakLink': '短板',
  'volatile': '变量',
  'watch': '关注',
};

class SignalTag extends StatelessWidget {
  const SignalTag(this.kind, {super.key});

  final String kind;

  static const _palette = <String, List<Color>>{
    'carry': <Color>[Color(0xFFB91C1C), Color(0xFFFEF2F2)],
    'anchor': <Color>[Color(0xFF1D4ED8), Color(0xFFEFF6FF)],
    'specialist': <Color>[Color(0xFF7C3AED), Color(0xFFF5F3FF)],
    'weakLink': <Color>[Color(0xFF0369A1), Color(0xFFF0F9FF)],
    'volatile': <Color>[Color(0xFFB45309), Color(0xFFFFFBEB)],
  };

  @override
  Widget build(BuildContext context) {
    final colors = _palette[kind] ?? <Color>[AppColors.muted, AppColors.elevated];
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 0.5),
      decoration: BoxDecoration(
        color: colors[1],
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        signalLabels[kind] ?? '关注',
        style: TextStyle(fontSize: 9, fontWeight: FontWeight.w700, color: colors[0]),
      ),
    );
  }
}

class RatingText extends StatelessWidget {
  const RatingText(this.value, {super.key, this.fontSize = 14});

  final double? value;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final color = value == null
        ? AppColors.muted
        : value! >= 1.1
            ? AppColors.ok
            : value! < 0.95
                ? AppColors.bad
                : AppColors.fg;
    return Text(
      fmt(value),
      style: TextStyle(
        fontSize: fontSize,
        fontWeight: FontWeight.w700,
        color: color,
        fontFeatures: const [FontFeature.tabularFigures()],
      ),
    );
  }
}

class NoticeCard extends StatelessWidget {
  const NoticeCard(this.text, {super.key, this.tone = NoticeTone.warn});

  final String text;
  final NoticeTone tone;

  @override
  Widget build(BuildContext context) {
    final warn = tone == NoticeTone.warn;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: warn ? AppColors.warnSoft : AppColors.accentSoft,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: warn ? const Color(0xFFFDE68A) : const Color(0xFFE0E7FF)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            warn ? Icons.info_outline : Icons.auto_awesome,
            size: 15,
            color: warn ? AppColors.warn : AppColors.accent,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                fontSize: 11.5,
                height: 1.5,
                color: warn ? const Color(0xFF78350F) : AppColors.fgSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

enum NoticeTone { warn, info }
