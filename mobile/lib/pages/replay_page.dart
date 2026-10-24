import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart' show Ticker;

import '../controllers/room_controller.dart';
import '../core/format.dart';
import '../core/theme.dart';
import '../models/match.dart';
import '../models/replay.dart';
import '../widgets/common.dart';

class ReplayPage extends StatefulWidget {
  const ReplayPage({super.key, required this.controller, required this.player});

  final RoomController controller;
  final PathPlayer player;

  @override
  State<ReplayPage> createState() => _ReplayPageState();
}

class _ReplayPageState extends State<ReplayPage> {
  late Future<ReplayBundle> _future = widget.controller.loadReplay(widget.player.steamId);

  void _retry() {
    setState(() {
      _future = widget.controller.loadReplay(widget.player.steamId);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        titleSpacing: 0,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              widget.player.displayName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
            ),
            const Text(
              '开局 20 秒走位',
              style: TextStyle(fontSize: 10.5, color: AppColors.muted, fontWeight: FontWeight.w400),
            ),
          ],
        ),
        actions: <Widget>[
          IconButton(
            tooltip: '重新加载',
            onPressed: _retry,
            icon: const Icon(Icons.refresh, size: 20),
          ),
        ],
      ),
      body: SafeArea(
        bottom: true,
        child: FutureBuilder<ReplayBundle>(
          future: _future,
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2)),
                    SizedBox(height: 10),
                    Text('正在加载轨迹…', style: TextStyle(fontSize: 12, color: AppColors.muted)),
                  ],
                ),
              );
            }
            if (snapshot.hasError) {
              return Center(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      EmptyCard('${snapshot.error}', icon: Icons.route_outlined),
                      const SizedBox(height: 12),
                      OutlinedButton(onPressed: _retry, child: const Text('重试')),
                    ],
                  ),
                ),
              );
            }
            final replay = snapshot.data!;
            return ReplayView(
              replay: replay,
              radarUrl: widget.controller.resolveAsset(replay.radar),
            );
          },
        ),
      ),
    );
  }
}

class ReplayView extends StatefulWidget {
  const ReplayView({super.key, required this.replay, required this.radarUrl});

  final ReplayBundle replay;
  final String radarUrl;

  @override
  State<ReplayView> createState() => _ReplayViewState();
}

class _ReplayViewState extends State<ReplayView> with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  final ValueNotifier<double> _time = ValueNotifier<double>(0);
  late double _duration = widget.replay.durationFor();

  ui.Image? _radar;
  bool _radarFailed = false;
  ImageStream? _stream;
  ImageStreamListener? _listener;

  bool _playing = true;
  double _speed = 2;
  String? _side;

  Duration _lastElapsed = Duration.zero;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_onTick)..start();
    _loadRadar();
  }

  @override
  void dispose() {
    _ticker.dispose();
    _time.dispose();
    final stream = _stream;
    final listener = _listener;
    if (stream != null && listener != null) stream.removeListener(listener);
    _radar?.dispose();
    super.dispose();
  }

  void _onTick(Duration elapsed) {
    final delta = (elapsed - _lastElapsed).inMicroseconds / 1000000;
    _lastElapsed = elapsed;
    if (!_playing || _duration <= 0) return;
    var next = _time.value + delta * _speed;
    if (next >= _duration) next = 0;
    _time.value = next;
  }

  void _loadRadar() {
    final url = widget.radarUrl;
    if (url.isEmpty) {
      _radarFailed = true;
      return;
    }
    final stream = NetworkImage(url).resolve(ImageConfiguration.empty);
    _stream = stream;
    final listener = ImageStreamListener(
      (info, _) {
        // ImageInfo 可能在回调结束后被回收，克隆一份自己持有。
        final image = info.image.clone();
        if (!mounted) {
          image.dispose();
          return;
        }
        setState(() {
          _radar?.dispose();
          _radar = image;
        });
      },
      onError: (Object error, StackTrace? stack) {
        if (mounted) setState(() => _radarFailed = true);
      },
    );
    _listener = listener;
    stream.addListener(listener);
  }

  void _changeSide(String? side) {
    setState(() {
      _side = side;
      _duration = widget.replay.durationFor(side: _side);
      if (_time.value > _duration) _time.value = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    final replay = widget.replay;
    final rounds = replay.filtered(side: _side);
    final awp = replay.awpRate == null ? '—' : '${replay.awpRate!.round()}%';

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 6, 12, 12),
      child: Column(
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.insights_outlined, size: 15, color: AppColors.muted),
              const SizedBox(width: 5),
              Expanded(
                child: Text(
                  '该场 K/D ${fmt(replay.combatKd)} · AWP $awp · ${replay.roundCount} 回合',
                  style: const TextStyle(fontSize: 11.5, color: AppColors.muted),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Expanded(
            child: Center(
              child: AspectRatio(
                aspectRatio: 1,
                child: Container(
                  clipBehavior: Clip.antiAlias,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: AppColors.border),
                    color: const Color(0xFF141821),
                    boxShadow: appShadow,
                  ),
                  child: Stack(
                    fit: StackFit.expand,
                    children: <Widget>[
                      CustomPaint(
                        painter: ReplayPainter(
                          time: _time,
                          radar: _radar,
                          radarFailed: _radarFailed,
                          transform: replay.transform,
                          rounds: rounds,
                        ),
                      ),
                      if (rounds.isEmpty)
                        const Center(
                          child: Text(
                            '当前筛选没有回合',
                            style: TextStyle(fontSize: 12, color: Color(0x8CFFFFFF)),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 10),
          ValueListenableBuilder<double>(
            valueListenable: _time,
            builder: (context, value, _) {
              final clamped = value.clamp(0.0, _duration).toDouble();
              return Column(
                children: <Widget>[
                  Slider(
                    value: clamped,
                    max: _duration,
                    onChanged: (next) => _time.value = next,
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4),
                    child: Row(
                      children: <Widget>[
                        Text(
                          '${clamped.toStringAsFixed(1)}s',
                          style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
                        ),
                        const Spacer(),
                        Text(
                          '${_duration.toStringAsFixed(1)}s',
                          style: const TextStyle(fontSize: 10.5, color: AppColors.muted),
                        ),
                      ],
                    ),
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 4),
          Row(
            children: <Widget>[
              SizedBox(
                height: 38,
                child: FilledButton.icon(
                  onPressed: () => setState(() => _playing = !_playing),
                  icon: Icon(_playing ? Icons.pause : Icons.play_arrow, size: 18),
                  label: Text(_playing ? '暂停' : '播放'),
                ),
              ),
              const Spacer(),
              _Segmented<double>(
                values: const <double>[1, 2, 4],
                selected: _speed,
                label: (value) => '${value.toInt()}x',
                onChanged: (value) => setState(() => _speed = value),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: <Widget>[
              _Segmented<String?>(
                values: const <String?>[null, 'CT', 'T'],
                selected: _side,
                label: (value) => value ?? '全部',
                onChanged: _changeSide,
              ),
              const Spacer(),
              Text(
                '${rounds.length} 段路径',
                style: const TextStyle(fontSize: 11, color: AppColors.muted),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Segmented<T> extends StatelessWidget {
  const _Segmented({
    required this.values,
    required this.selected,
    required this.label,
    required this.onChanged,
  });

  final List<T> values;
  final T selected;
  final String Function(T value) label;
  final ValueChanged<T> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(9),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: values.map((value) {
          final on = value == selected;
          return InkWell(
            onTap: () => onChanged(value),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              color: on ? AppColors.accentSoft : Colors.transparent,
              child: Text(
                label(value),
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: on ? AppColors.accent : AppColors.muted,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class ReplayPainter extends CustomPainter {
  ReplayPainter({
    required this.time,
    required this.radar,
    required this.radarFailed,
    required this.transform,
    required this.rounds,
  }) : super(repaint: time);

  final ValueNotifier<double> time;
  final ui.Image? radar;
  final bool radarFailed;
  final ReplayTransform transform;
  final List<ReplayRound> rounds;

  static const _ctColor = Color(0xFF5B9CF8);
  static const _tColor = Color(0xFFE0A44A);
  static const _grenadeColors = <String, Color>{
    'smoke': Color(0xFF9AA4B2),
    'flash': Color(0xFFF0D264),
    'he': Color(0xFFD98C5F),
    'molotov': Color(0xFFE2593F),
    'decoy': Color(0xFF7FB3A8),
  };

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || size.height <= 0) return;
    final scale = size.width / replayRadarSize;
    canvas.save();
    canvas.scale(scale, scale);
    _drawBackground(canvas);
    final now = time.value;
    for (final round in rounds) {
      _drawRound(canvas, round, now);
    }
    canvas.restore();
  }

  void _drawBackground(Canvas canvas) {
    const rect = Rect.fromLTWH(0, 0, replayRadarSize, replayRadarSize);
    final image = radar;
    if (image != null) {
      paintImage(
        canvas: canvas,
        rect: rect,
        image: image,
        fit: BoxFit.fill,
        opacity: 0.92,
      );
      return;
    }

    canvas.drawRect(rect, Paint()..color = const Color(0xFF141821));
    final grid = Paint()
      ..color = const Color(0x0FFFFFFF)
      ..strokeWidth = 1;
    for (double i = 0; i <= replayRadarSize; i += 128) {
      canvas.drawLine(Offset(i, 0), Offset(i, replayRadarSize), grid);
      canvas.drawLine(Offset(0, i), Offset(replayRadarSize, i), grid);
    }
    if (radarFailed) {
      final painter = TextPainter(
        text: const TextSpan(
          text: '缺少雷达图资源',
          style: TextStyle(color: Color(0x59FFFFFF), fontSize: 28),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      painter.paint(
        canvas,
        Offset(
          (replayRadarSize - painter.width) / 2,
          (replayRadarSize - painter.height) / 2,
        ),
      );
    }
  }

  void _drawRound(Canvas canvas, ReplayRound round, double now) {
    if (round.path.isEmpty) return;
    final color = round.side == 'CT' ? _ctColor : _tColor;

    final linePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2
      ..strokeJoin = StrokeJoin.round
      ..color = color.withAlpha(87);
    final path = Path();
    var started = false;
    for (final point in round.path) {
      if (point.t > now) break;
      final pixel = transform.toPixel(point.x, point.y);
      if (!started) {
        path.moveTo(pixel.dx, pixel.dy);
        started = true;
      } else {
        path.lineTo(pixel.dx, pixel.dy);
      }
    }
    if (started) canvas.drawPath(path, linePaint);

    _drawGrenades(canvas, round, now, color);

    final position = sampleReplayPoint(round.path, now);
    if (position == null) return;
    final pixel = transform.toPixel(position.x, position.y);
    canvas.drawCircle(pixel, 7, Paint()..color = color);
    canvas.drawCircle(
      pixel,
      7,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..color = const Color(0xD9080A0E),
    );
  }

  void _drawGrenades(Canvas canvas, ReplayRound round, double now, Color sideColor) {
    for (final grenade in round.grenades) {
      if (grenade.throwT > now) continue;
      final color = _grenadeColors[grenade.type] ?? sideColor;

      if (grenade.arc.length > 1) {
        final paint = Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5
          ..color = color.withAlpha(191);
        final path = Path();
        var started = false;
        for (final point in grenade.arc) {
          if (point.t > now) break;
          final pixel = transform.toPixel(point.x, point.y);
          if (!started) {
            path.moveTo(pixel.dx, pixel.dy);
            started = true;
          } else {
            path.lineTo(pixel.dx, pixel.dy);
          }
        }
        if (started) canvas.drawPath(path, paint);
      }

      final land = grenade.land;
      if (land == null) continue;
      if ((grenade.landT ?? 0) > now) continue;
      final pixel = transform.toPixel(land.dx, land.dy);
      final active = grenade.expireT == null || grenade.expireT! >= now;
      canvas.drawCircle(
        pixel,
        9,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2
          ..color = color.withAlpha(active ? 217 : 64),
      );
    }
  }

  @override
  bool shouldRepaint(covariant ReplayPainter oldDelegate) {
    return oldDelegate.radar != radar ||
        oldDelegate.radarFailed != radarFailed ||
        oldDelegate.rounds != rounds ||
        oldDelegate.transform != transform;
  }
}
