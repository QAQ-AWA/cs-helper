# 给手机端（Flutter）的提示词

下面整段可以直接粘给写 Flutter 的 agent，服务端已经上线，它只需要做客户端。

---

## 背景

CS Helper 的手机端是 Flutter（仓库里 `mobile/`），连的是同一个 relay。
服务端刚上线了一个新能力：**对手开局走位解读**——根据解析出来的 demo 轨迹，
用 AI 产出「每个人怎么走、开局 20 秒大概率在哪、我方怎么针对」。

现在手机端「轨迹」页只有一条条路径和选手列表，看不到结论。你要把这个解读卡片加上。

**不要改服务端**，数据已经在推了。

## 协议契约（已上线，无需协商）

两个入口，同一份数据：

1. `ROOM_STATE_SYNC` / `MATCH_DETECTED` 的 `payload.match.pathReport`
2. 新事件 `PATHS_REPORT_READY`，`payload.report`

字段（可能为空字符串或 null，全部按可选处理）：

```json
{
  "summary": "CT 普遍重 A 轻 B，多数人开局离点游走",
  "tempo": "中性，平均 48.4 秒",
  "sitePreference": "A 54% / B 46%（用 teamPlants：A 21 / B 18）",
  "players": [
    {
      "nickname": "叁仟三百叄",
      "steamId": "7656119xxxxxxxxxx",
      "side": "CT",
      "habit": "CT 12 回合中 5 次守 A、1 次守 B；T 侧 8 次压 A、4 次压 B，平均 58.4 秒下包",
      "likely": "开局 20 秒内从 A 小或 A 大附近压出，倾向离点游走",
      "counter": "A 大第一身位开局 15 秒内给 A 大过点烟，第二人架 A 小"
    }
  ],
  "counters": ["开局 15 秒内封 A 大过点烟", "A 大第一身位提前架枪", "B 区只留一人看"]
}
```

约束（服务端已经保证，客户端按此假设即可）：

- `players` 最多 5 人，`counters` 最多 3 条
- `nickname` 一定在名单里（服务端过滤过），`steamId` 可用于和名单关联
- 任何字段都可能缺省；`pathReport` 整个为 null 表示「还没有」

## 要改的三个文件

### 1. `lib/models/match.dart`

加两个模型 + `MatchSession` 上一个字段：

```dart
class PathReportPlayer {
  const PathReportPlayer({
    required this.nickname,
    this.steamId,
    this.side,
    this.habit,
    this.likely,
    this.counter,
  });

  final String nickname;
  final String? steamId;
  final String? side;      // 'CT' / 'T'，可能为空
  final String? habit;
  final String? likely;
  final String? counter;
}

class PathReport {
  const PathReport({
    this.summary,
    this.tempo,
    this.sitePreference,
    this.players = const <PathReportPlayer>[],
    this.counters = const <String>[],
  });

  final String? summary;
  final String? tempo;
  final String? sitePreference;
  final List<PathReportPlayer> players;
  final List<String> counters;

  bool get isEmpty =>
      (summary == null || summary!.isEmpty) && players.isEmpty;
}
```

`MatchSession` 加 `final PathReport? pathReport;`，在 `fromJson` 里：

```dart
pathReport: json['pathReport'] is Map
    ? PathReport.fromJson(asMap(json['pathReport']))
    : null,
```

`fromJson` 用现有的 `asString` / `asMapList` / `asStringList` 辅助函数，别引入新依赖。

### 2. `lib/controllers/room_controller.dart`

- `ROOM_STATE_SYNC` / `MATCH_DETECTED` 走的是 `_applyMatchPayload`，只要 `MatchSession.fromJson`
  加了字段就自动带上，不用额外写
- 新增事件分支（放在 `AI_TACTICS_READY` 旁边）：

```dart
case 'PATHS_REPORT_READY':
  final report = payload['report'];
  if (report is Map) {
    _applyMatchPayload(<String, dynamic>{'pathReport': report});
  }
  break;
```

### 3. `lib/pages/tabs/paths_tab.dart`

在 `ListView` 的 `children` 最前面（**`_statusCard()` 之前**）插入：

```dart
if (controller.match?.pathReport != null &&
    !controller.match!.pathReport!.isEmpty) ...<Widget>[
  _pathReportCard(controller.match!.pathReport!),
  const SizedBox(height: 10),
],
```

卡片布局（用现有的 `AppCard` / `AppColors`，和「分析」页的卡片保持同一套视觉）：

```
┌─────────────────────────────────────────────┐
│ [开局走位解读] 中性，平均 48.4 秒  A 54% / B 46% │   ← 三个 chip，缺省就不显示
│                                             │
│ CT 普遍重 A 轻 B，多数人开局离点游走          │   ← summary，15sp 加粗
│                                             │
│ ┌ 叁仟三百叄  [CT] ──────────────────────┐   │   ← 每人一个小块
│ │ 习惯：CT 12 回合中 5 次守 A、1 次守 B…    │   │
│ │ 大概率：开局 20 秒内从 A 小或 A 大附近压出  │   │
│ │ 针对：A 大第一身位 15 秒内给过点烟…        │   │   ← 用 accent 色
│ └───────────────────────────────────────┘   │
│                                             │
│ 整队对策                                     │
│ · 开局 15 秒内封 A 大过点烟                   │
│ · A 大第一身位提前架枪                        │
└─────────────────────────────────────────────┘
```

细节要求：

- **位置**：必须在「习惯轨迹」选手列表**上方**，让人先看结论再点人
- **层级**：队头 chip 行（`11sp`）→ summary（`15sp`、`w600`）→ 每人一块（`12sp`）→ 对策列表
- **每人一块**：名字 + 阵营 chip 一行；下面三行，行首标签用 `AppColors.muted`，内容用
  `AppColors.fgSecondary`，「针对」那行用 `AppColors.accent`
- **长文本**：不截断、不加省略号，允许换行（`softWrap: true`）
- **缺省**：`habit` / `likely` / `counter` 为空就不渲染那一行，不要留空行
- **空态**：`pathReport == null` 时**整张卡不出现**（不要占位、不要写「生成中」）；
  轨迹列表和状态卡保持原样
- **刷新**：`RefreshIndicator` 不用动，`controller.refresh()` 会重新拉快照，字段自动带上

## 验收标准

用真实服务器验（房间码 `V9LSAH`，地址 `http://129.146.178.13:8787`）：

1. 进入「轨迹」页，最上方出现「开局走位解读」卡片，能读到 summary 和至少 3 个人的三段内容
2. 卡片里的名字和下面「习惯轨迹」列表里的名字能对上
3. 换一场还没解析完 demo 的对局（`pathReport` 为 null）→ 卡片完全不出现，页面和现在一样
4. 长昵称 / 长文案不溢出、不裁切
5. `flutter analyze` 无新增告警

## 不要做的事

- 不要改服务端、不要改协议
- 不要加新的第三方依赖
- 不要把这张卡做成可折叠/可关闭（信息是赛前要用的，默认展开）
- 不要在卡片里重复「开局预判」的内容——那是分析页的 markdown，这里是结构化的走位结论
