/** 界面内的 Agent 接入管理：令牌状态、生成（一次性明文）与吊销。
 *
 * 安全约定：明文只在生成响应中出现一次，由用户手动复制；不写入浏览器存储，也不在任何
 * 后续读取中返回。掩码规则与后端保持一致。
 */
import { localRequest } from "./local-edition";

export type AgentTokenState = {
  configured: boolean;
  masked_token: string;
  created_at: string;
  updated_at: string;
  rotations: number;
  path_configured: boolean;
  restart_required?: boolean;
  api_base?: string;
};
export type AgentTokenGenerated = AgentTokenState & { plaintext: string; notice: string };

export const AGENT_DEFAULT_EXAMPLE = "scripts/or sources";

export function maskAgentToken(token: string): string {
  if (!token) return "";
  if (token.length <= 18) return `${token.slice(0, 9)}***`;
  return `${token.slice(0, 10)}***${token.slice(-4)}`;
}

export function agentTokenStatusText(state: AgentTokenState | null): string {
  if (!state || !state.configured) return "未配置：生成后 agent 才能调用本机接口。";
  const created = state.created_at ? `创建于 ${state.created_at}` : "创建时间未知";
  return `已配置（${state.masked_token}）· ${created} · 轮换 ${state.rotations} 次 · 热加载生效，无需重启`;
}

export async function fetchAgentToken(): Promise<AgentTokenState> {
  return localRequest<AgentTokenState>("/api/local/agent-token");
}

export async function generateAgentToken(): Promise<AgentTokenGenerated> {
  return localRequest<AgentTokenGenerated>("/api/local/agent-token", { method: "POST", body: "{}" });
}

export async function revokeAgentToken(): Promise<AgentTokenState> {
  return localRequest<AgentTokenState>("/api/local/agent-token", { method: "DELETE" });
}
