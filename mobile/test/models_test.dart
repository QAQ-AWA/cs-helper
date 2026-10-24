import 'package:cs_helper_mobile/core/format.dart';
import 'package:cs_helper_mobile/models/analysis.dart';
import 'package:cs_helper_mobile/models/match.dart';
import 'package:cs_helper_mobile/models/player.dart';
import 'package:cs_helper_mobile/models/post_match.dart';
import 'package:cs_helper_mobile/models/replay.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AnalysisResult', () {
    test('解析 v3 结构化结果', () {
      final result = AnalysisResult.fromJson(<String, dynamic>{
        'schemaVersion': 3,
        'predictedWinner': 'A',
        'modelWinProbability': <String, dynamic>{'A': 62.0, 'B': 38.0},
        'confidence': 68,
        'dataCoverage': 0.67,
        'headline': 'A队火力更厚，B队双核需重点盯防',
        'decisiveFactors': <dynamic>[
          <String, dynamic>{
            'dimension': 'strength',
            'advantage': 'A',
            'impact': 3,
            'title': 'A队整体Rating占优',
            'summary': 'A队平均Rating 1.11高于B队0.97',
          },
        ],
        'playerSignals': <dynamic>[
          <String, dynamic>{
            'steamId': '76561199496030298',
            'nickname': 'ez爱ly',
            'side': 'A',
            'kind': 'carry',
            'impact': 3,
            'title': 'ez爱ly火力爆表',
            'summary': 'Rating 1.54',
          },
        ],
        'teamPlans': <String, dynamic>{
          'A': <String, dynamic>{
            'winConditions': <dynamic>[
              <String, dynamic>{'text': '围绕双核打默认'},
            ],
            'risks': <dynamic>[
              <String, dynamic>{'text': '样本偏小'},
            ],
          },
        },
        'uncertainties': <dynamic>['双方KAST缺失'],
      });

      expect(result.predictedWinner, 'A');
      expect(result.winA, 62);
      expect(result.winB, 38);
      expect(result.confidence, 68);
      expect(result.dataCoverage, closeTo(0.67, 0.001));
      expect(result.factors.single.dimension, 'strength');
      expect(result.signals.single.kind, 'carry');
      expect(result.planFor('A').winConditions.single.text, '围绕双核打默认');
      expect(result.planFor('B').isEmpty, isTrue);
      expect(result.uncertainties.single, '双方KAST缺失');
    });

    test('缺字段时退回安全默认值', () {
      final result = AnalysisResult.fromJson(<String, dynamic>{});
      expect(result.winA, 50);
      expect(result.winB, 50);
      expect(result.predictedWinner, 'Even');
      expect(result.factors, isEmpty);
      expect(result.dataCoverage, 0);
    });
  });

  group('PlayerStats / RosterRow', () {
    test('画像覆盖上报名单，且只在有值时覆盖', () {
      const reported = PlayerStats(rating: 0.97, kd: 0.92);
      const profile = PlayerStats(seasonRating: 1.065, seasonAdr: 84.1);
      final merged = reported.mergedWith(profile);
      expect(merged.rating, 0.97);
      expect(merged.seasonRating, 1.065);
      expect(merged.seasonAdr, 84.1);
      expect(merged.kd, 0.92);
    });

    test('赛季 Rating 与近期 Rating 相同时不重复展示', () {
      const player = PlayerInfo(
        steamId: '76561199798646630',
        platformUserId: '1216lukkyepi',
        nickname: '下一次转角',
        stats: PlayerStats(rating: 0.97, seasonRating: 0.97),
      );
      const row = RosterRow(
        side: 'ct',
        player: player,
        profile: null,
        stats: PlayerStats(rating: 0.97, seasonRating: 0.97),
      );
      expect(row.seasonRating, 0.97);
      expect(row.recentRating, isNull);

      const row2 = RosterRow(
        side: 'ct',
        player: player,
        profile: null,
        stats: PlayerStats(rating: 0.97, seasonRating: 1.065),
      );
      expect(row2.recentRating, 0.97);
    });
  });

  group('MatchSession', () {
    test('解析快照里的会话与阵容', () {
      final session = MatchSession.fromJson(<String, dynamic>{
        'sessionId': '9f5d9ac2',
        'platform': '5e',
        'matchId': 'g161-20261024110743296316621',
        'mapName': 'de_dust2',
        'mySide': 'ct',
        'mySideSource': 'explicit',
        'profileState': 'ready',
        'demoState': 'running',
        'homeState': 'ready',
        'homeCoverage': 10,
        'artifactId': '84bf934d',
        'aiState': 'ready',
        'tacticsState': 'ready',
        'aiWait': <dynamic>['等地图'],
        'teams': <String, dynamic>{
          'ct': <dynamic>[
            <String, dynamic>{
              'steamId': '76561199798646630',
              'nickname': '下一次转角',
              'stats': <String, dynamic>{'seasonRating': 0.97},
            },
          ],
          't': <dynamic>[],
        },
      });

      expect(session.mySide, 'ct');
      expect(session.teams.ct.single.nickname, '下一次转角');
      expect(session.teams.ct.single.stats.seasonRating, 0.97);
      expect(session.aiWait.single, '等地图');
      expect(session.artifactId, '84bf934d');
    });
  });

  group('ReplayBundle', () {
    final payload = <String, dynamic>{
      'map': 'de_dust2',
      'radar': '/maps/de_dust2/radar.png',
      'transform': <String, dynamic>{'pos_x': -2476.0, 'pos_y': 3239.0, 'scale': 4.4},
      'combat_stats': <String, dynamic>{'kd': 0.75, 'awp_rate': 0.0},
      'round_count': 1,
      'rounds': <dynamic>[
        <String, dynamic>{
          'side': 'CT',
          'rtype': 'full',
          'round_id': 0,
          'path': <dynamic>[
            <dynamic>[0.0, -2476.0, 3239.0],
            <dynamic>[0.5, -2454.0, 3239.0],
          ],
          'grenades': <dynamic>[
            <String, dynamic>{
              'type': 'smoke',
              'throw_t': 1.2,
              'arc': <dynamic>[
                <dynamic>[1.2, -2476.0, 3239.0],
                <dynamic>[1.5, -2400.0, 3200.0],
              ],
              'land': <dynamic>[-2400.0, 3200.0],
              'land_t': 1.5,
              'expire_t': 19.5,
            },
          ],
          'plant': <String, dynamic>{'site': 'A', 'x': 987.9, 'y': 2490.1, 't': 39.33},
          'match_code': 'm1',
        },
      ],
    };

    test('坐标换算与网页端一致', () {
      final replay = ReplayBundle.fromJson(payload);
      final pixel = replay.transform.toPixel(-2476, 3239);
      expect(pixel.dx, closeTo(0, 0.001));
      expect(pixel.dy, closeTo(0, 0.001));
      final second = replay.transform.toPixel(-2454, 3239);
      expect(second.dx, closeTo(5, 0.001));
    });

    test('解析路径、道具与下包点', () {
      final replay = ReplayBundle.fromJson(payload);
      final round = replay.rounds.single;
      expect(round.side, 'CT');
      expect(round.path.length, 2);
      expect(round.grenades.single.type, 'smoke');
      expect(round.grenades.single.land!.dx, -2400);
      expect(round.plant!.site, 'A');
      expect(replay.combatKd, 0.75);
      expect(replay.durationFor(), 1);
    });

    test('线性插值取位置', () {
      final replay = ReplayBundle.fromJson(payload);
      final point = sampleReplayPoint(replay.rounds.single.path, 0.25)!;
      expect(point.x, closeTo(-2465, 0.001));
      expect(point.y, 3239);
    });
  });

  group('PostMatchReport', () {
    test('解析比分、半场与选手行', () {
      final report = PostMatchReport.fromJson(<String, dynamic>{
        'matchCode': 'g161-1',
        'mapName': 'de_dust2',
        'roundTotal': 22,
        'scoreA': 13,
        'scoreB': 9,
        'winnerSide': 'A',
        'halfScores': <String, dynamic>{'fhA': 8, 'fhB': 4, 'shA': 5, 'shB': 5},
        'players': <dynamic>[
          <String, dynamic>{
            'nickname': '半团空气',
            'teamSide': 1,
            'kill': 24,
            'death': 16,
            'assist': 5,
            'rating': 1.32,
            'adr': 96,
            'isMvp': true,
          },
          <String, dynamic>{
            'nickname': 'Z大爷',
            'teamSide': 2,
            'kill': 26,
            'death': 17,
            'assist': 3,
            'rating': 1.28,
            'adr': 104,
            'isSvp': true,
          },
        ],
        'comparison': <String, dynamic>{'isCorrect': true, 'headline': 'AI 预测命中'},
      });

      expect(report.scoreA, 13);
      expect(report.halfScores!.fhA, 8);
      expect(report.playersFor(1).single.nickname, '半团空气');
      expect(report.playersFor(1).single.isMvp, isTrue);
      expect(report.playersFor(2).single.isSvp, isTrue);
      expect(report.comparison!.isCorrect, isTrue);
    });
  });

  group('format helpers', () {
    test('百分比只转换一次', () {
      expect(pct(46.0), '46%');
      expect(pct(0.46), '46%');
      expect(pct(null), '—');
    });

    test('A/B 视角按我方替换', () {
      expect(persp('A队火力更厚，B队双核', null), 'A队火力更厚，B队双核');
      expect(persp('A队火力更厚，B队双核', 'ct'), '我方火力更厚，对方双核');
      expect(sideName('A', 'ct'), '我方');
      expect(sideName('B', 'ct'), '对方');
      expect(sideName('A', null), 'A 队');
    });

    test('近期战绩只取最近 5 场', () {
      expect(recentFlags('LLWWW'), <String>['L', 'L', 'W', 'W', 'W']);
      expect(recentFlags('WWLWLW'), <String>['W', 'L', 'W', 'L', 'W']);
      expect(recentFlags(null), isEmpty);
    });

    test('CT/T 与我方/对方的映射', () {
      expect(teamTitle('ct', 'ct'), '我方');
      expect(teamTitle('t', 'ct'), '对方');
      expect(teamTitle('ct', null), 'A 队');
      expect(teamTitle('t', 't'), '我方');
    });
  });
}
