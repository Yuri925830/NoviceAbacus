export type AgentRecommendation = {
  priority: "HIGH" | "MEDIUM" | "LOW";
  action: string;
  reason: string;
  expected_impact: string;
  risk: string;
  review_trigger: string;
};

export type AgentResult = {
  executive_summary: string;
  confirmed_facts: string[];
  key_numbers: Array<{ label: string; value: string; meaning: string }>;
  analysis: string[];
  recommendations: AgentRecommendation[];
  alternatives: string[];
  assumptions: string[];
  limitations: string[];
  follow_up_questions: string[];
  requires_owner_confirmation: boolean;
};

export type AgentReply = {
  provider: string;
  model: string;
  fallback_from?: string;
  fallback_reason?: string;
  result: AgentResult;
};

export function actionItemPayload(item: AgentRecommendation, source: string) {
  return {
    title: item.action,
    reason: item.reason,
    expected_impact: item.expected_impact,
    risk: item.risk,
    review_trigger: item.review_trigger,
    priority: item.priority,
    source,
  };
}

export const emptyAgentResult = (): AgentResult => ({
  executive_summary: "",
  confirmed_facts: [],
  key_numbers: [],
  analysis: [],
  recommendations: [],
  alternatives: [],
  assumptions: [],
  limitations: [],
  follow_up_questions: [],
  requires_owner_confirmation: false,
});
