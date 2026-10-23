/**
 * 历史里的 AI 报告是「读出来的旧数据」，不是现场推理的结果。
 *
 * 客户端不再调用模型（AI 在服务端跑），所以这里只做结构校验：形状不对就当没有，
 * 形状对就原样交给展示组件。不要再往这里塞归一化/校准逻辑——那是服务端的事。
 */
import type { AiAnalysisResult } from './types';

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function normalizeAiAnalysisResult(raw: unknown): AiAnalysisResult | null {
  const obj = asRecord(raw);
  if (!obj) return null;
  // v1/v2 是更早的 schema，客户端已经没有渲染它们的组件了。
  if (obj.schemaVersion !== 3) return null;
  if (typeof obj.headline !== 'string' || !obj.headline.trim()) return null;
  if (!Array.isArray(obj.decisiveFactors)) return null;
  if (!Array.isArray(obj.playerSignals)) return null;
  if (!asRecord(obj.winProbability)) return null;
  return obj as unknown as AiAnalysisResult;
}
