import 'package:cs_helper_mobile/controllers/room_controller.dart';
import 'package:cs_helper_mobile/core/theme.dart';
import 'package:cs_helper_mobile/models/match.dart';
import 'package:cs_helper_mobile/models/player.dart';
import 'package:cs_helper_mobile/pages/join_page.dart';
import 'package:cs_helper_mobile/pages/room_page.dart';
import 'package:cs_helper_mobile/services/api_client.dart';
import 'package:cs_helper_mobile/services/settings_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

RoomController _controller() {
  return RoomController(api: ApiClient(), store: SettingsStore());
}

Map<String, dynamic> _player(int index, String side) {
  return <String, dynamic>{
    'steamId': '7656119${(8000000000 + index).toString()}',
    'platformUserId': 'domain$index',
    'nickname': '选手$index',
    'isSelf': index == 0,
    'stats': <String, dynamic>{
      'rating': 0.9 + index * 0.02,
      'seasonRating': 1.0 + index * 0.01,
      'seasonAdr': 70 + index,
      'seasonRws': 9 + index * 0.4,
      'kd': 0.9 + index * 0.03,
      'headshotRate': 42 + index,
      'recentResults': 'WWLWL',
    },
  };
}

MatchSession _match({bool withAnalysis = false, bool withPost = false}) {
  final ct = List<Map<String, dynamic>>.generate(5, (index) => _player(index, 'ct'));
  final t = List<Map<String, dynamic>>.generate(5, (index) => _player(index + 5, 't'));
  return MatchSession.fromJson(<String, dynamic>{
    'sessionId': 'session-1',
    'platform': '5e',
    'matchId': 'g161-20261024110743296316621',
    'mapName': 'de_dust2',
    'mySide': 'ct',
    'mySideSource': 'explicit',
    'profileState': 'ready',
    'demoState': 'ready',
    'homeState': 'ready',
    'homeCoverage': 10,
    'artifactId': 'artifact-1',
    'aiState': withAnalysis ? 'ready' : 'pending',
    'tacticsState': withAnalysis ? 'ready' : 'pending',
    'tacticsText': withAnalysis ? '## 开局选点预判\n地面真相：A 13 / B 7。' : null,
    'aiResult': withAnalysis
        ? <String, dynamic>{
            'schemaVersion': 3,
            'predictedWinner': 'A',
            'modelWinProbability': <String, dynamic>{'A': 62, 'B': 38},
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
                'steamId': '76561198000000000',
                'nickname': '选手0',
                'side': 'A',
                'kind': 'carry',
                'title': '选手0火力爆表',
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
          }
        : null,
    'postReport': withPost
        ? <String, dynamic>{
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
          }
        : null,
    'teams': <String, dynamic>{'ct': ct, 't': t},
  });
}

void main() {
  testWidgets('进房页在 360x640 下渲染且不溢出', (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller();
    addTearDown(controller.dispose);

    await tester.pumpWidget(
      MaterialApp(theme: buildTheme(), home: JoinPage(controller: controller)),
    );
    await tester.pump();

    expect(find.text('进入房间'), findsOneWidget);
    expect(find.text('CS Helper'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('阵容页十人卡片不溢出', (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller();
    addTearDown(controller.dispose);
    controller.match = _match();
    controller.mySide = 'ct';
    controller.members = const <Member>[
      Member(id: '1', nickname: '房主', deviceType: 'pc', isOnline: true),
      Member(id: '2', nickname: '队友', deviceType: 'mobile', isOnline: true),
    ];

    await tester.pumpWidget(
      MaterialApp(theme: buildTheme(), home: RoomPage(controller: controller)),
    );
    await tester.pump();

    expect(find.text('选手0'), findsOneWidget);
    expect(find.text('选手9'), findsOneWidget);
    expect(find.text('我方 CT · 手动'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('分析页渲染结构化卡片', (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller();
    addTearDown(controller.dispose);
    controller.match = _match(withAnalysis: true);
    controller.mySide = 'ct';
    controller.activeTab = 1;

    await tester.pumpWidget(
      MaterialApp(theme: buildTheme(), home: RoomPage(controller: controller)),
    );
    await tester.pump();

    expect(find.text('决定本局的因素'), findsOneWidget);
    expect(find.text('玩家信号'), findsOneWidget);
    expect(find.text('双方取胜路径'), findsOneWidget);
    expect(find.textContaining('我方火力更厚'), findsOneWidget);
    // 「数据边界」在长列表底部，ListView 懒加载不会立刻构建；这里只验证首屏结构。
    expect(tester.takeException(), isNull);
  });

  testWidgets('赛后页渲染比分与两队表格', (tester) async {
    tester.view.physicalSize = const Size(1080, 1920);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller();
    addTearDown(controller.dispose);
    controller.match = _match(withPost: true);
    controller.activeTab = 3;

    await tester.pumpWidget(
      MaterialApp(theme: buildTheme(), home: RoomPage(controller: controller)),
    );
    await tester.pump();

    expect(find.text('13 : 9'), findsOneWidget);
    expect(find.text('半团空气'), findsOneWidget);
    expect(find.text('Z大爷'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
