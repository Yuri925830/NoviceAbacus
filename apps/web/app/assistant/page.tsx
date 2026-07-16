"use client";
import { Protected } from "@/components/app-shell";
import { usePrivacy } from "@/components/providers";
import { Badge, Button, Card, Field } from "@/components/ui";
import { api, errorMessage, money } from "@/lib/api";
import { actionItemPayload, type AgentRecommendation, type AgentReply } from "@/lib/agent";
import {
  ArrowUp,
  Bot,
  BookmarkCheck,
  CheckCircle2,
  CircleAlert,
  FlaskConical,
  Gauge,
  MessageCircleQuestion,
  Send,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import { FormEvent, useState } from "react";

const questions = [
  "我应该准备多少应急金才安心？",
  "用一个生活里的例子，讲讲复利是什么。",
  "如果我有资产数据，帮我看看哪里值得留意。",
  "怎样把一个大目标拆成每月能做到的小计划？",
];
function AssistantContent() {
  const [message, setMessage] = useState(""),
    [depth, setDepth] = useState("complex"),
    [provider, setProvider] = useState("auto"),
    [loading, setLoading] = useState(false),
    [reply, setReply] = useState<AgentReply | null>(null),
    [error, setError] = useState("");
  const [savedActions, setSavedActions] = useState<number[]>([]);
  const [stock, setStock] = useState("-20"),
    [krw, setKrw] = useState("-10"),
    [scenario, setScenario] = useState<{
      base_net_worth_cny: string;
      scenario_net_worth_cny: string;
      change_cny: string;
      change_pct: string;
      warning: string;
    } | null>(null),
    [scenarioLoading, setScenarioLoading] = useState(false);
  const { hidden } = usePrivacy();
  async function ask(e?: FormEvent, text?: string) {
    e?.preventDefault();
    const q = text || message;
    if (!q.trim()) return;
    setLoading(true);
    setError("");
    setReply(null);
    try {
      const r = await api<AgentReply>("/assistant", {
        method: "POST",
        body: JSON.stringify({ message: q, depth, provider }),
      });
      setReply(r);
      setSavedActions([]);
      setMessage("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  async function saveAction(item: AgentRecommendation, index: number) {
    try {
      await api("/intelligence/actions", {
        method: "POST",
        body: JSON.stringify(actionItemPayload(item, "ASSISTANT")),
      });
      setSavedActions((current) => [...current, index]);
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function runScenario() {
    setScenarioLoading(true);
    setError("");
    try {
      setScenario(
        await api("/scenario", {
          method: "POST",
          body: JSON.stringify({
            asset_type_shocks: { STOCK: Number(stock), FUND: Number(stock) },
            currency_shocks: { KRW: Number(krw) },
            liability_change_pct: 0,
          }),
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setScenarioLoading(false);
    }
  }
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">TALK WITH WHITE</div>
          <h1>和怀特聊聊</h1>
          <p>想看自己的资产、规划目标，或者只是有个理财问题，都可以直接问她。</p>
        </div>
        <div className="page-actions">
          <Badge tone="purple">
            <Sparkles />
            怀特理财顾问
          </Badge>
        </div>
      </div>
      <div className="assistant-layout">
        <Card className="assistant-main">
          <div className="assistant-hero">
            <div className="assistant-intro">
              <Badge tone="purple">怀特 · 理财顾问</Badge>
              <h2>
                有数字，我们一起看懂。
                <br />
                没有数据，也可以聊理财。
              </h2>
              <p>把你的困惑说出来就好，怀特会尽量讲得简单、踏实。</p>
            </div>
          </div>
          <div className="assistant-body">
            {!reply && !loading ? (
              <div className="question-starters">
                <span>可以这样问</span>
                <div>
                  {questions.map((q) => (
                    <button key={q} onClick={() => ask(undefined, q)}>
                      <MessageCircleQuestion />
                      {q}
                      <ArrowUp />
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {loading ? (
              <div className="thinking">
                <div className="thinking-orbit">
                  <Sparkles />
                </div>
                <div>
                  <strong>怀特正在认真想你的问题</strong>
                  <span>如果你已经记过资产或目标，她也会一起参考。</span>
                </div>
              </div>
            ) : null}
            {reply ? (
              <div className="agent-reply">
                <div className="reply-meta">
                  <Badge tone="purple">
                    {reply.provider} · {reply.model}
                  </Badge>
                  {reply.fallback_from ? (
                    <Badge tone="warning">
                      已换到 {reply.provider} 继续回答
                    </Badge>
                  ) : null}
                </div>
                {reply.fallback_reason ? (
                  <p className="fallback-note">
                    刚才那条线路有点忙，已经自动换好，不影响继续聊。
                  </p>
                ) : null}
                {reply.result.executive_summary ? (
                  <section className="executive-summary">
                    <Sparkles />
                    <div>
                      <span>怀特的结论</span>
                      <strong>{reply.result.executive_summary}</strong>
                    </div>
                  </section>
                ) : null}
                {reply.result.key_numbers.length ? (
                  <section className="agent-key-numbers">
                    {reply.result.key_numbers.map((item, index) => (
                      <div key={`${item.label}-${index}`}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                        <small>{item.meaning}</small>
                      </div>
                    ))}
                  </section>
                ) : null}
                <ReplySection
                  icon={<CheckCircle2 />}
                  title="先看看已经知道的"
                  items={reply.result.confirmed_facts}
                />
                <ReplySection
                  icon={<Gauge />}
                  title="怀特的理解"
                  items={reply.result.analysis}
                />
                {reply.result.recommendations.length ? (
                  <section className="recommendations">
                    <div className="reply-section-title">
                      <WandSparkles />
                      <strong>可以从这里开始</strong>
                    </div>
                    {reply.result.recommendations.map((r, i) => (
                      <div className="recommendation" key={i}>
                        <b>{String(i + 1).padStart(2, "0")}</b>
                        <div>
                          <div className="recommendation-head">
                            <strong>{r.action}</strong>
                            <Badge tone={r.priority === "HIGH" ? "warning" : "purple"}>
                              {r.priority === "HIGH" ? "优先" : r.priority === "MEDIUM" ? "随后" : "可选"}
                            </Badge>
                          </div>
                          <p>{r.reason}</p>
                          {r.expected_impact ? <small>预期影响：{r.expected_impact}</small> : null}
                          {r.risk ? <span><CircleAlert />留意：{r.risk}</span> : null}
                          {r.review_trigger ? <small>复盘触发：{r.review_trigger}</small> : null}
                          <Button
                            variant="ghost"
                            disabled={savedActions.includes(i)}
                            onClick={() => saveAction(r, i)}
                          >
                            <BookmarkCheck /> {savedActions.includes(i) ? "已加入行动账本" : "加入行动账本"}
                          </Button>
                        </div>
                      </div>
                    ))}
                  </section>
                ) : null}
                <ReplySection icon={<FlaskConical />} title="其他可选路径" items={reply.result.alternatives} />
                <ReplySection icon={<Gauge />} title="这次判断基于" items={reply.result.assumptions} subdued />
                <ReplySection
                  icon={<CircleAlert />}
                  title="还想提醒你"
                  items={reply.result.limitations}
                  subdued
                />
                <ReplySection
                  icon={<MessageCircleQuestion />}
                  title="如果愿意，可以再补充"
                  items={reply.result.follow_up_questions}
                  subdued
                />
              </div>
            ) : null}
            {error ? (
              <div className="inline-error">
                <CircleAlert />
                <span>{error}</span>
              </div>
            ) : null}
          </div>
          <form className="assistant-composer" onSubmit={ask}>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="比如：我该怎么准备应急金？也可以直接问自己的资产和目标…"
              rows={2}
            />
            <div>
              <div className="composer-options">
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  aria-label="模型线路"
                >
                  <option value="auto">自动线路</option>
                  <option value="qwen">千问北京</option>
                  <option value="openai">OpenAI 海外</option>
                </select>
                <select
                  value={depth}
                  onChange={(e) => setDepth(e.target.value)}
                  aria-label="分析深度"
                >
                  <option value="ordinary">普通分析</option>
                  <option value="complex">深度分析</option>
                </select>
              </div>
              <Button
                loading={loading}
                disabled={!message.trim()}
                aria-label="发送"
              >
                <Send />
              </Button>
            </div>
          </form>
        </Card>
        <aside className="assistant-side">
          <Card className="card-pad scenario-card">
            <div className="card-head">
              <div className="card-title-row">
                <div className="card-icon">
                  <FlaskConical />
                </div>
                <div>
                  <h2>压力测试</h2>
                  <p>选几个变化幅度，看看自己的资产会怎样波动。</p>
                </div>
              </div>
            </div>
            <div className="scenario-fields">
              <Field label={`股票 / 基金 ${stock}%`}>
                <input
                  type="range"
                  min="-60"
                  max="40"
                  value={stock}
                  onChange={(e) => setStock(e.target.value)}
                />
              </Field>
              <Field label={`韩元汇率 ${krw}%`}>
                <input
                  type="range"
                  min="-30"
                  max="30"
                  value={krw}
                  onChange={(e) => setKrw(e.target.value)}
                />
              </Field>
            </div>
            <Button
              variant="secondary"
              className="full-button"
              loading={scenarioLoading}
              onClick={runScenario}
            >
              <FlaskConical />
              运行情景
            </Button>
            {scenario ? (
              <div className="scenario-result">
                <span>情景后净资产</span>
                <strong>
                  {money(scenario.scenario_net_worth_cny, hidden)}
                </strong>
                <div
                  className={Number(scenario.change_cny) < 0 ? "negative" : ""}
                >
                  {money(scenario.change_cny, hidden)} ·{" "}
                  {Number(scenario.change_pct).toFixed(1)}%
                </div>
                <small>{scenario.warning}</small>
              </div>
            ) : null}
          </Card>
          <Card className="agent-boundaries">
            <Bot />
            <h3>你可以和她聊</h3>
            <ul>
              <li>任何和理财有关的问题</li>
              <li>已经记录的资产、趋势和目标</li>
              <li>预算、应急金和长期计划</li>
            </ul>
            <h3>这些事仍由你决定</h3>
            <ul>
              <li>资产记录的修改与删除</li>
              <li>任何真实交易</li>
              <li>密码、验证码和密钥都不用告诉她</li>
            </ul>
          </Card>
        </aside>
      </div>
    </>
  );
}
function ReplySection({
  icon,
  title,
  items,
  subdued = false,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
  subdued?: boolean;
}) {
  if (!items.length) return null;
  return (
    <section className={`reply-section ${subdued ? "subdued" : ""}`}>
      <div className="reply-section-title">
        {icon}
        <strong>{title}</strong>
      </div>
      <ul>
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </section>
  );
}
export default function AssistantPage() {
  return (
    <Protected>
      <AssistantContent />
    </Protected>
  );
}
