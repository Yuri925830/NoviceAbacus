"use client";

import { Protected } from "@/components/app-shell";
import { Badge, Button, Card, Empty, Skeleton } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { AgentRecommendation } from "@/lib/agent";
import { BookOpenCheck, Check, CircleAlert, Edit3, Focus, Pause, Save, ShieldCheck, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";

type Rule = { id: string; rule_type: string; title: string; parameters: Record<string, number>; enabled: boolean; status: string; measured: string; detail: string; verification: Record<string, unknown> };
type Constitution = { rules: Rule[]; counts: Record<string, number>; snapshot_id?: string; checked_at: string; active_focus?: { id: string; verification: Record<string, unknown>; action: { id: string; title: string; reason: string; expected_impact: string; risk: string; review_trigger: string; status: string } } | null };
type FocusDraft = { recommendation: AgentRecommendation; verification: Record<string, unknown>; issue: { title?: string; detail?: string }; provider: string; model: string };

const statusLabels: Record<string, string> = { PASS: "符合", WARNING: "接近警戒线", VIOLATION: "已越过规则", UNVERIFIABLE: "需要确认", DISABLED: "已暂停" };

function ConstitutionContent() {
  const [data, setData] = useState<Constitution | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [focusLoading, setFocusLoading] = useState(false);
  const [focus, setFocus] = useState<FocusDraft | null>(null);
  const [error, setError] = useState("");
  async function load() { try { const result = await api<Constitution>("/constitution"); setData(result); setRules(result.rules); } catch (e) { setError(errorMessage(e)); } finally { setLoading(false); } }
  useEffect(() => { load(); }, []);
  async function saveRules() { setSaving(true); setError(""); try { await api("/constitution", { method: "PUT", body: JSON.stringify({ rules: rules.map((rule) => ({ rule_type: rule.rule_type, title: rule.title, parameters: rule.parameters, enabled: rule.enabled })) }) }); setEditing(false); await load(); } catch (e) { setError(errorMessage(e)); } finally { setSaving(false); } }
  async function generateFocus() { setFocusLoading(true); setError(""); try { setFocus(await api<FocusDraft>("/constitution/focus", { method: "POST", body: JSON.stringify({ message: "请选出本期最值得做的一件事", provider: "auto", depth: "complex" }) })); } catch (e) { setError(errorMessage(e)); } finally { setFocusLoading(false); } }
  async function acceptFocus() { if (!focus) return; setSaving(true); try { await api("/constitution/focus/accept", { method: "POST", body: JSON.stringify({ recommendation: focus.recommendation, verification: focus.verification }) }); setFocus(null); await load(); } catch (e) { setError(errorMessage(e)); } finally { setSaving(false); } }
  async function setFocusStatus(status: string) { if (!data?.active_focus) return; await api(`/intelligence/actions/${data.active_focus.action.id}`, { method: "PATCH", body: JSON.stringify({ status }) }); await load(); }
  function updateParameter(index: number, key: string, value: string) { setRules((current) => current.map((rule, i) => i === index ? { ...rule, parameters: { ...rule.parameters, [key]: Number(value) } } : rule)); }
  if (loading) return <><div className="page-head"><div><div className="eyebrow">MY FINANCIAL CONSTITUTION</div><h1>我的理财宪法</h1></div></div><Skeleton height={520} /></>;
  return <>
    <div className="page-head constitution-head"><div><div className="eyebrow">MY FINANCIAL CONSTITUTION</div><h1>我的理财宪法</h1><p>先和怀特定下长期规则，以后的建议就有稳定边界，不会今天一个说法、明天又变一套。</p></div><Button variant={editing ? "secondary" : "primary"} onClick={() => editing ? saveRules() : setEditing(true)} loading={saving}>{editing ? <><Save /> 保存宪法</> : <><Edit3 /> 调整规则</>}</Button></div>
    {error ? <div className="inline-error"><CircleAlert />{error}</div> : null}
    <section className="constitution-scoreboard"><Card><Check /><strong>{data?.counts.PASS || 0}</strong><span>符合规则</span></Card><Card><CircleAlert /><strong>{data?.counts.WARNING || 0}</strong><span>接近警戒线</span></Card><Card><X /><strong>{data?.counts.VIOLATION || 0}</strong><span>已经越线</span></Card><Card><BookOpenCheck /><strong>{rules.filter((rule) => rule.enabled).length}</strong><span>生效中的长期规则</span></Card></section>
    <div className="constitution-grid">
      <Card className="card-pad constitution-rules"><div className="card-head"><div><h2>长期规则</h2><p>每次清算后，系统都会用最新确认数据重新检查。</p></div><Badge tone="purple">自动检查</Badge></div><div className="rule-list">{rules.map((rule, index) => <div className={`rule-row rule-${rule.status.toLowerCase()}`} key={rule.id}><div className="rule-state"><ShieldCheck /><Badge tone={rule.status === "VIOLATION" ? "warning" : rule.status === "PASS" ? "purple" : "neutral"}>{statusLabels[rule.status] || rule.status}</Badge></div><div className="rule-copy">{editing ? <input value={rule.title} onChange={(e) => setRules((current) => current.map((item, i) => i === index ? { ...item, title: e.target.value } : item))} /> : <strong>{rule.title}</strong>}<span>{rule.measured}</span><p>{rule.detail}</p>{editing ? <div className="rule-parameters">{Object.entries(rule.parameters).map(([key, value]) => <label key={key}><span>{key === "months" ? "月数" : key === "max_pct" ? "上限 %" : key === "min_pct" ? "下限 %" : key === "amount_cny" ? "金额门槛" : key}</span><input inputMode="decimal" value={value} onChange={(e) => updateParameter(index, key, e.target.value)} /></label>)}</div> : null}</div>{editing ? <label className="rule-toggle"><input type="checkbox" checked={rule.enabled} onChange={(e) => setRules((current) => current.map((item, i) => i === index ? { ...item, enabled: e.target.checked } : item))} /><span>{rule.enabled ? "生效" : "暂停"}</span></label> : null}</div>)}</div></Card>
      <aside className="constitution-focus-column">
        <Card className="focus-card"><div className="focus-orbit"><Focus /></div><Badge tone="purple">本期只做一件事</Badge>{data?.active_focus ? <><h2>{data.active_focus.action.title}</h2><p>{data.active_focus.action.reason}</p><div className="focus-impact"><strong>完成后</strong><span>{data.active_focus.action.expected_impact}</span></div><small>下次验证：{data.active_focus.action.review_trigger}</small><div className="focus-buttons"><Button onClick={() => setFocusStatus("DOING")}><Check /> 开始执行</Button><Button variant="ghost" onClick={() => setFocusStatus("SNOOZED")}><Pause /> 稍后处理</Button></div></> : <><h2>让怀特只挑最重要的一项</h2><p>她会先看越线规则和现金流，不会一次扔给你十几条建议。</p><Button loading={focusLoading} onClick={generateFocus}><Sparkles /> 生成本期重点</Button></>}</Card>
        {focus ? <Card className="card-pad focus-proposal"><Badge tone="warning">候选重点 · {focus.provider}</Badge><h3>{focus.recommendation.action}</h3><p>{focus.recommendation.reason}</p><dl><div><dt>预期影响</dt><dd>{focus.recommendation.expected_impact}</dd></div><div><dt>可能阻力</dt><dd>{focus.recommendation.risk}</dd></div><div><dt>下次验证</dt><dd>{focus.recommendation.review_trigger}</dd></div></dl><div className="focus-buttons"><Button loading={saving} onClick={acceptFocus}><Check /> 接受这一项</Button><Button variant="ghost" onClick={() => setFocus(null)}>不适合我</Button></div></Card> : null}
      </aside>
    </div>
  </>;
}
export default function ConstitutionPage() { return <Protected><ConstitutionContent /></Protected>; }
