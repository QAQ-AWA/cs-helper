# CS Helper · Android 客户端

CS2 开黑辅助的原生 Android 客户端，用 Flutter 重写网页端（`server/static/`）的全部功能。
不是 WebView 套壳：雷达回放用 `CustomPainter` 直接绘制，WebSocket 自己管重连与 token 失效。

## 为什么要有它

网页端已经能用，但手机上一直有三个绕不开的问题：

| 网页端 | 原生端 |
| --- | --- |
| Service Worker / 浏览器缓存导致「只有无痕能看到新数据」 | 没有缓存层，每次启动都是新代码 |
| 切到后台再回来，WS 可能已经断了且不会立刻恢复 | `WebSocket` 自己重连，回前台自动补快照 |
| 雷达回放靠 Canvas + rAF，低端机掉帧 | `Ticker` + `CustomPainter`，只重绘雷达层 |

## 功能

- **进房**：服务端地址 + 房间码 + 昵称；token 按「地址 + 房间」分别保存，换房不会串号。
- **阵容**：CT/T 两列卡片，赛季 Rating / ADR / RWS / K/D / 爆头率 / 近 5 场；服务端画像优先。
- **我方阵营**：CT / T / 都看；选完只下载对面 5 人的录像，可把 5 个 ID 记进 ID 库。
- **分析**：v3 结构化结果（胜率条、决定因素、玩家信号、双方取胜路径、数据边界）；老会话回退 Markdown；支持「重新分析」。
- **开局预判**：轨迹就绪后自动生成的第二段 AI，单独卡片展示。
- **轨迹**：选手列表 → 雷达回放；20 秒窗口、1x/2x/4x、CT/T 筛选、进度拖动、道具弧线与落点。
- **赛后**：比分、半场、AI 命中、双方 K/D/A + Rating + ADR，MVP/SVP 标记。
- **连接**：顶栏状态点（已连接 / 连接中 / 已断开），点一下立即重连；`4401` 或连续握手失败自动退回登录页。

## 环境

实测：Flutter **3.47.8**（Dart 3.13.7）、JDK 17、Android SDK 36、AGP 9.1.0、Gradle 9.3.1。
`shared_preferences_android` 会带一个 `jni` 原生插件，因此还需要 **NDK 28.2.13676358** 与 **CMake 3.22.1**
（Android Studio 的 SDK Manager 里勾选即可）。
最低支持 Flutter 3.24 / Dart 3.5（`pubspec.yaml` 的约束）。

```bash
cd mobile
flutter pub get
flutter analyze          # 0 issue
flutter test             # 17 passed
flutter run              # 连真机或模拟器
flutter build apk --release                    # universal ≈ 50MB
flutter build apk --release --split-per-abi    # arm64 17.7MB / v7a 15.2MB / x86_64 19.1MB
```

产物：`build/app/outputs/flutter-apk/`。仓库根 `dist/` 里放了 0.1.0 的 arm64 / armeabi-v7a / universal
三个 APK 与 `SHA256SUMS.txt`（`dist/` 已 gitignore，不随仓库分发）。

### 首次构建的坑

- **必须用 JDK 17+**：AGP 9.x 不再支持 JDK 8/11。
- **国内网络**：`android/settings.gradle.kts` 与 `android/build.gradle.kts` 已把阿里云 Maven 镜像放在 `google()` 前面，
  否则 `dl.google.com` 可能 TLS 握手失败。Flutter SDK 自带的 `packages/flutter_tools/gradle/settings.gradle.kts`
  也会拉 AGP，如果它报同样的 TLS 错误，给那个文件加同样两行镜像即可（只影响本机构建工具，不影响项目）。
- **NDK / CMake**：模板写了 `ndkVersion = flutter.ndkVersion`（28.2.13676358），
  `shared_preferences_android` 的 `jni` 插件还要 CMake 3.22.1。首次构建若本机没有，
  AGP 会尝试调用 `sdkmanager` 自动安装；国内网络下这一步会失败，先在 SDK Manager 里装好即可。
- **Windows 的 Kotlin 增量缓存**：偶发 `Could not close incremental caches`（杀软/索引器锁文件）。
  已在 `android/gradle.properties` 设 `kotlin.incremental=false`，构建慢一点但可重复。
- **`local.properties` 不入库**：`flutter pub get` / `flutter build` 会写入 `flutter.sdk`，Android Studio 会写 `sdk.dir`。
- 如果 Android 工程被改坏，可以用 `flutter create --platforms=android --org com.qaqawa --project-name cs_helper_mobile .`
  重新生成平台目录，再按本文件的包名 / 权限改回去。
- **release 目前用 debug 签名**（Flutter 模板默认），可以装到自己手机；要正式分发需要配置自己的 keystore。

## 连服务端

手机和电脑必须在同一个 Wi-Fi，地址填电脑的局域网 IP：

```
http://192.168.3.46:8787
```

不要填 `127.0.0.1`。Android 9+ 默认禁止明文 HTTP，本项目在 `AndroidManifest.xml` 里显式开了
`android:usesCleartextTraffic="true"`（局域网只读接口，没有账号密码）。

服务端默认单房间模式，房间码可以留空；多房间模式填电脑端创建的房间码。

## 目录

```
lib/
├─ main.dart / app.dart          入口、主题、登录态路由
├─ controllers/room_controller.dart   连接、快照、事件、轨迹缓存（唯一状态源）
├─ services/
│  ├─ api_client.dart            REST 信封解析 + WS URL
│  └─ settings_store.dart        地址 / 房间 / 昵称 / token
├─ models/                       Player / Match / Analysis / Replay / PostMatch
├─ pages/
│  ├─ join_page.dart             进房
│  ├─ room_page.dart             顶栏 + 四页签
│  ├─ replay_page.dart           雷达回放（Ticker + CustomPainter）
│  └─ tabs/                      阵容 / 分析 / 轨迹 / 赛后
├─ widgets/                      卡片、头像、信号标签、Markdown、底部弹层
└─ core/                         主题 token、格式化（百分比、A/B 视角）
```

## 协议要点（与网页端一致）

- REST 统一信封：`{code, message, data}`；`code != 0` 抛错，401/403 视为 token 失效。
- WS：`/ws?token=...&lastSeq=...`，信封 `{protocolVersion, seq, ts, action, payload}`。
- 重连先补 `seq > lastSeq` 的事件，最后发 `ROOM_STATE_SYNC`（服务端行为）；客户端把快照当权威状态。
- `MATCH_DETECTED` 是新对局，整份替换；`AI_*` / `PROFILE_READY` 是增量，按字段合并。
- `4401` = 服务端重启后 token 验签过但成员不存在；必须清 token 回登录页，不能无限重连。

## 已知限制

- 只做 Android；iOS 没有构建目标（协议层可直接复用）。
- 没有历史对局列表（服务端 `/api/v1/history/sessions` 已就绪，客户端还没做入口）。
- 轨迹不落盘，退出 App 后重进需要重新拉取；单次会话内有内存缓存。
- 雷达图依赖服务端 `/maps/<map>/radar.png`；缺图时显示网格与「缺少雷达图资源」，不会白屏。
- 签名网关失效、AI 未配置等仍由服务端降级提示，客户端只负责展示。

## 测试

```bash
flutter test
```

覆盖：v3 分析结果解析与兜底、画像合并、赛季/近期 Rating 去重、会话与阵容、轨迹坐标换算与插值、
赛后战报、百分比与 A/B 视角替换。
