import 'package:flutter/material.dart';

import '../core/theme.dart';

/// 极简 Markdown：模型只输出 ## 标题、**粗体** 和 - 列表。
class MarkdownText extends StatelessWidget {
  const MarkdownText(this.text, {super.key, this.fontSize = 13});

  final String text;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final base = TextStyle(fontSize: fontSize, height: 1.6, color: AppColors.fgSecondary);
    final heading = TextStyle(
      fontSize: fontSize + 0.5,
      height: 1.5,
      fontWeight: FontWeight.w700,
      color: AppColors.fg,
    );
    final blocks = <Widget>[];
    final lines = text.replaceAll('\r\n', '\n').split('\n');

    for (final rawLine in lines) {
      final line = rawLine.trimRight();
      if (line.trim().isEmpty) {
        blocks.add(const SizedBox(height: 6));
        continue;
      }

      final headingMatch = RegExp(r'^#{1,4}\s*(.+)$').firstMatch(line);
      if (headingMatch != null) {
        blocks.add(
          Padding(
            padding: EdgeInsets.only(top: blocks.isEmpty ? 0 : 6, bottom: 2),
            child: _rich(headingMatch.group(1)!, heading, heading),
          ),
        );
        continue;
      }

      final bulletMatch = RegExp(r'^[-*]\s+(.+)$').firstMatch(line);
      if (bulletMatch != null) {
        blocks.add(
          Padding(
            padding: const EdgeInsets.only(left: 2, top: 1, bottom: 1),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Text('·', style: TextStyle(color: AppColors.dim, fontSize: 13)),
                const SizedBox(width: 7),
                Expanded(child: _rich(bulletMatch.group(1)!, base, heading)),
              ],
            ),
          ),
        );
        continue;
      }

      blocks.add(
        Padding(
          padding: const EdgeInsets.only(top: 1, bottom: 1),
          child: _rich(line, base, heading),
        ),
      );
    }

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: blocks);
  }

  Widget _rich(String content, TextStyle base, TextStyle bold) {
    final spans = <InlineSpan>[];
    final pattern = RegExp(r'\*\*([^*]+)\*\*');
    var cursor = 0;
    for (final match in pattern.allMatches(content)) {
      if (match.start > cursor) {
        spans.add(TextSpan(text: content.substring(cursor, match.start)));
      }
      spans.add(TextSpan(text: match.group(1), style: bold));
      cursor = match.end;
    }
    if (cursor < content.length) {
      spans.add(TextSpan(text: content.substring(cursor)));
    }
    return Text.rich(TextSpan(style: base, children: spans));
  }
}
