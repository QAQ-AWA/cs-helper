// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref } from 'vue';
import ServerAnalysisPanel from './ServerAnalysisPanel.vue';

/**
 * The panel only reads refs off the sync composable, so a plain object with
 * refs is enough — no relay, no Tauri, no network.
 */
function fakeSync(match: Record<string, unknown> | null) {
  return {
    serverMatch: ref(match),
    serverProfiles: ref([]),
    aiStreamChunk: ref(''),
    tacticsStream: ref(''),
    sideBusy: ref(false),
    sideError: ref<string | null>(null),
    setAnalysisSide: async () => {},
  } as never;
}

const READY_MATCH = {
  matchId: '2603231600001',
  mapName: 'de_mirage',
  mySide: 'ct',
  mySideSource: 'explicit',
  profileState: 'ready',
  homeState: 'ready',
  demoState: 'ready',
  aiState: 'ready',
  aiText: '## 结论\nCT 更被看好\n- 依据：ADR 更高',
  tacticsState: 'ready',
  tacticsText: '## 开局选点预判\n11 个下包回合里 7 次打 A',
};

describe('ServerAnalysisPanel', () => {
  it('renders the server report and the opening prediction', () => {
    const wrapper = mount(ServerAnalysisPanel, { props: { sync: fakeSync(READY_MATCH) } });
    const text = wrapper.text();

    expect(text).toContain('服务端分析');
    expect(text).toContain('战术分析');
    expect(text).toContain('CT 更被看好');
    expect(text).toContain('7 次打 A');
    // Markdown headings become blocks, not literal "##".
    expect(text).not.toContain('## 结论');
  });

  it('shows the state chips for every pipeline stage', () => {
    const wrapper = mount(ServerAnalysisPanel, { props: { sync: fakeSync(READY_MATCH) } });
    const text = wrapper.text();
    for (const label of ['画像', '赛季', '轨迹', '战术', '开局']) {
      expect(text).toContain(label);
    }
  });

  it('explains a skipped AI instead of pretending it is loading', () => {
    const wrapper = mount(ServerAnalysisPanel, {
      props: {
        sync: fakeSync({
          ...READY_MATCH,
          aiState: 'skipped',
          aiText: null,
          tacticsState: 'skipped',
          tacticsText: null,
        }),
      },
    });
    const text = wrapper.text();
    expect(text).toContain('未配置 AI key');
    expect(text).not.toContain('等待服务端生成');
  });

  it('waits quietly when the relay has no match yet', () => {
    const wrapper = mount(ServerAnalysisPanel, { props: { sync: fakeSync(null) } });
    expect(wrapper.text()).toContain('等待电脑端上报对局');
  });

  it('marks the chosen side and its source', () => {
    const wrapper = mount(ServerAnalysisPanel, { props: { sync: fakeSync(READY_MATCH) } });
    expect(wrapper.text()).toContain('手动选择');
  });
});
