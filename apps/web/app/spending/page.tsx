"use client";

import { Protected } from "@/components/app-shell";
import { usePrivacy } from "@/components/providers";
import { Badge, Button, Card, Field, Skeleton } from "@/components/ui";
import { api, errorMessage, formatDate, money } from "@/lib/api";
import type { SpendingProfile, SpendingRuling, SpendingSnapshot } from "@/lib/types";
import {
  AlertTriangle,
  ArrowRight,
  BatteryCharging,
  CalendarDays,
  CheckCircle2,
  Coins,
  Gauge,
  Lightbulb,
  PencilLine,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  WalletCards,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

type HistoryRow = {id:string;decision:string;amount_cny:string;verdict:string;result:SpendingSnapshot;provider:string;model:string;created_at:string};

const emptyProfile: SpendingProfile = {
  configured: false,
  source: "MISSING",
  monthly_income_cny: "0",
  monthly_essential_expenses_cny: "0",
  monthly_current_expenses_cny: "0",
  emergency_months: "6",
};

const verdictClass: Record<string, string> = {
  DO_IT: "spend-verdict-do",
  ADJUST: "spend-verdict-adjust",
  WAIT: "spend-verdict-wait",
};

function decimal(value: string) {
  return value.replace(/[，,\s]/g, "");
}

function months(value: string | null | undefined) {
  if (value === null || value === undefined) return "等你补充开销";
  return `${Number(value).toFixed(1)} 个月`;
}

function batteryTone(value: number) {
  if (value >= 80) return "high";
  if (value >= 60) return "steady";
  if (value >= 40) return "careful";
  return "low";
}

function SpendingContent() {
  const { hidden } = usePrivacy();
  const [snapshot, setSnapshot] = useState<SpendingSnapshot | null>(null);
  const [preview, setPreview] = useState<SpendingSnapshot | null>(null);
  const [ruling, setRuling] = useState<SpendingRuling | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [profile, setProfile] = useState<SpendingProfile>(emptyProfile);
  const [editingProfile, setEditingProfile] = useState(false);
  const [decision, setDecision] = useState("我想买一台电脑");
  const [amount, setAmount] = useState("15000");
  const [category, setCategory] = useState("ELECTRONICS");
  const [plannedDate, setPlannedDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [judging, setJudging] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [next, rows] = await Promise.all([
        api<SpendingSnapshot>("/spending/safe-to-spend"),
        api<HistoryRow[]>("/spending/decisions"),
      ]);
      setSnapshot(next);
      setProfile(next.profile || emptyProfile);
      setHistory(rows);
      setEditingProfile(!next.profile?.configured);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    const value = Number(decimal(amount));
    if (!snapshot?.ready || !decision.trim() || !Number.isFinite(value) || value <= 0) {
      setPreview(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api<SpendingSnapshot>("/spending/preview", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({
          decision: decision.trim(),
          amount_cny: decimal(amount),
          category,
          planned_date: plannedDate || null,
        }),
      }).then(setPreview).catch((e) => {
        if (e instanceof DOMException && e.name === "AbortError") return;
        setError(errorMessage(e));
      });
    }, 320);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [amount, category, decision, plannedDate, snapshot?.ready]);

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api("/spending/profile", {
        method: "PUT",
        body: JSON.stringify({
          monthly_income_cny: decimal(profile.monthly_income_cny),
          monthly_essential_expenses_cny: decimal(profile.monthly_essential_expenses_cny),
          monthly_current_expenses_cny: decimal(profile.monthly_current_expenses_cny),
          emergency_months: decimal(profile.emergency_months),
        }),
      });
      setEditingProfile(false);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function judge() {
    const parsedAmount = Number(decimal(amount));
    if (!decision.trim() || !Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError("告诉怀特你想做什么、准备花多少钱，就能开始裁决。");
      return;
    }
    setJudging(true);
    setError("");
    try {
      const next = await api<SpendingRuling>("/spending/ruling", {
        method: "POST",
        body: JSON.stringify({
          decision: decision.trim(),
          amount_cny: decimal(amount),
          category,
          planned_date: plannedDate || null,
          provider: "auto",
          depth: "complex",
        }),
      });
      setRuling(next);
      setPreview(next.result);
      setHistory((rows) => [{
        id: next.id,
        decision: next.decision,
        amount_cny: next.result.simulation?.amount_cny || decimal(amount),
        verdict: next.result.verdict || "WAIT",
        result: next.result,
        provider: next.agent.provider,
        model: next.agent.model,
        created_at: next.created_at,
      }, ...rows].slice(0, 20));
      window.setTimeout(() => document.getElementById("spending-ruling")?.scrollIntoView({behavior:"smooth", block:"start"}), 50);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setJudging(false);
    }
  }

  const shown = preview || snapshot;
  const battery = Number(shown?.battery?.after_pct ?? shown?.battery?.before_pct ?? 0);
  const batteryBefore = Number(shown?.battery?.before_pct ?? 0);
  const isSimulating = Boolean(preview);
  const plainReason = useMemo(() => {
    if (!snapshot?.ready) return snapshot?.reason;
    if (Number(snapshot.safe_to_spend_cny) <= 0) {
      return "现在的可用现金还没有盖住应急资金、近期支出和已经答应给目标的钱，所以怀特先把放心花额度守在 0。不是不能花，而是每一笔都值得先裁决一下。";
    }
    return `在不碰应急资金、近期支出和目标资金的前提下，本月这部分钱可以更安心地自由安排。`;
  }, [snapshot]);

  if (loading) return <><div className="page-head"><div><div className="eyebrow">SPEND WITH CONFIDENCE</div><h1>放心花</h1></div></div><Skeleton height={430} /></>;

  return (
    <>
      <div className="page-head spending-page-head">
        <div>
          <div className="eyebrow">SPEND WITH CONFIDENCE</div>
          <h1>放心花</h1>
          <p>先把日子和目标安顿好，再告诉你今天能不能安心花。</p>
        </div>
        <Button variant="secondary" onClick={() => void load()}><RefreshCw size={16}/>重新计算</Button>
      </div>

      {error ? <div className="inline-error"><AlertTriangle size={17}/><span>{error}</span></div> : null}

      <Card className="spending-hero">
        <div className="spending-hero-art" aria-hidden="true" />
        <div className="spending-hero-copy">
          <Badge tone="purple">怀特已替你留好底线</Badge>
          <span>本月可放心花</span>
          <strong>{snapshot?.ready ? money(snapshot.safe_to_spend_cny, hidden) : "还差一点信息"}</strong>
          <p>{plainReason}</p>
          <div className="spending-hero-actions">
            <a href="#money-ruling" className="button button-primary">裁决一笔开销 <ArrowRight size={17}/></a>
            <button className="button button-ghost" onClick={() => setEditingProfile((value) => !value)}><PencilLine size={16}/>更新收入与开销</button>
          </div>
        </div>
        {snapshot?.ready && snapshot.battery ? (
          <div className={`battery-orb battery-${batteryTone(Number(snapshot.battery.before_pct))}`}>
            <div className="battery-orb-ring"><i style={{"--battery": `${snapshot.battery.before_pct}%`} as React.CSSProperties}/></div>
            <BatteryCharging />
            <strong>{Number(snapshot.battery.before_pct).toFixed(0)}%</strong>
            <span>财务电量 · {snapshot.battery.before_label}</span>
          </div>
        ) : null}
      </Card>

      {editingProfile ? (
        <Card className="card-pad spending-profile-card">
          <div className="card-head"><div><h2>先告诉怀特你的日常节奏</h2><p>只要四个数字。以后收入或生活变化了，随时回来改。</p></div></div>
          <form className="spending-profile-grid" onSubmit={saveProfile}>
            <Field label="每月固定收入"><input inputMode="decimal" value={profile.monthly_income_cny} onChange={(e)=>setProfile({...profile,monthly_income_cny:e.target.value})}/></Field>
            <Field label="每月必要生活费" hint="房租、吃饭、交通等不能轻易停掉的开销"><input inputMode="decimal" required value={profile.monthly_essential_expenses_cny} onChange={(e)=>setProfile({...profile,monthly_essential_expenses_cny:e.target.value})}/></Field>
            <Field label="维持现在生活的总开销" hint="应当不低于必要生活费"><input inputMode="decimal" required value={profile.monthly_current_expenses_cny} onChange={(e)=>setProfile({...profile,monthly_current_expenses_cny:e.target.value})}/></Field>
            <Field label="希望留几个月应急金"><input type="number" min="1" max="24" step="0.5" value={profile.emergency_months} onChange={(e)=>setProfile({...profile,emergency_months:e.target.value})}/></Field>
            <div className="spending-profile-submit"><Button type="submit" loading={saving}>保存并重新计算</Button>{profile.source === "LATEST_GOAL_PLAN" ? <span>已先带入你在财务目标里填写的收支，可以直接修改。</span> : null}</div>
          </form>
        </Card>
      ) : null}

      {snapshot?.ready && snapshot.battery ? (
        <section className="runway-grid" aria-label="生活续航">
          <Card className="runway-card"><Gauge/><span>维持现在的生活</span><strong>{months(snapshot.battery.current_lifestyle_months_before)}</strong><small>按目前总开销估算</small></Card>
          <Card className="runway-card"><ShieldCheck/><span>只保留必要开销</span><strong>{months(snapshot.battery.essential_only_months_before)}</strong><small>把可暂停支出先放一放</small></Card>
          <Card className="runway-card"><WalletCards/><span>不卖股票和黄金</span><strong>{months(snapshot.battery.without_selling_investments_months_before)}</strong><small>只使用现金和存款</small></Card>
        </section>
      ) : null}

      <Card id="money-ruling" className="money-ruling-card">
        <div className="ruling-intro">
          <Badge tone="purple">钱事裁决</Badge>
          <h2>这笔钱，花得安心吗？</h2>
          <p>写下想做的事和预算。你改动金额时，右边的财务电量会跟着实时变化。</p>
        </div>
        <div className="ruling-workbench">
          <div className="ruling-form">
            <Field label="我想做的事"><textarea rows={3} value={decision} onChange={(e)=>setDecision(e.target.value)} placeholder="例如：我想买一台电脑"/></Field>
            <div className="ruling-form-row">
              <Field label="准备花多少钱"><input inputMode="decimal" value={amount} onChange={(e)=>setAmount(e.target.value)} placeholder="15000"/></Field>
              <Field label="大概属于"><select value={category} onChange={(e)=>setCategory(e.target.value)}><option value="ELECTRONICS">数码家电</option><option value="TRAVEL">旅行</option><option value="EDUCATION">学习成长</option><option value="HOME">住房家居</option><option value="VEHICLE">买车用车</option><option value="MEDICAL">医疗健康</option><option value="GIFT">人情赠礼</option><option value="OTHER">其他</option></select></Field>
            </div>
            <Field label="打算什么时候花（可不填）"><input type="date" value={plannedDate} onChange={(e)=>setPlannedDate(e.target.value)}/></Field>
            <Button className="ruling-button" onClick={judge} loading={judging} disabled={!snapshot?.ready}><Sparkles size={17}/>请怀特裁决</Button>
            {!snapshot?.ready ? <small className="muted">{snapshot?.reason}</small> : null}
          </div>
          <div className={`live-battery-panel battery-${batteryTone(battery)}`}>
            <span>{isSimulating ? "花完以后" : "现在"}</span>
            <div className="live-battery-number"><BatteryCharging/><strong>{battery.toFixed(0)}%</strong></div>
            <b>{shown?.battery?.after_label || shown?.battery?.before_label || "等待计算"}</b>
            {isSimulating && shown?.simulation ? <><div className="battery-shift"><span>{batteryBefore.toFixed(0)}%</span><i/><ArrowRight/><i/><span>{battery.toFixed(0)}%</span></div><p>可用现金 {money(shown.simulation.cash_before_cny, hidden)} → {money(shown.simulation.cash_after_cny, hidden)}</p></> : <p>输入金额后，这里会先给你看变化。</p>}
          </div>
        </div>
      </Card>

      {shown?.ready && shown.verdict && isSimulating ? (
        <Card id="spending-ruling" className={`spending-result ${verdictClass[shown.verdict]}`}>
          <div className="spending-result-main">
            <div className="verdict-mark">{shown.verdict === "DO_IT" ? <CheckCircle2/> : shown.verdict === "ADJUST" ? <Lightbulb/> : <TrendingDown/>}</div>
            <div><span>结论</span><h2>{shown.verdict_label}</h2><p>{ruling?.agent.result.executive_summary || shown.calculation_note}</p></div>
          </div>
          <div className="ruling-facts">
            <div><span>建议最高预算</span><strong>{money(shown.suggested_max_budget_cny, hidden)}</strong></div>
            <div><span>买完可用现金</span><strong>{money(shown.simulation?.cash_after_cny, hidden)}</strong></div>
            <div><span>财务电量</span><strong>{Number(shown.battery?.before_pct).toFixed(0)}% → {Number(shown.battery?.after_pct).toFixed(0)}%</strong></div>
            <div><span>对攒钱目标</span><strong>{shown.goal_delay_days === null ? "需要重新排期" : shown.goal_delay_days ? `约推迟 ${shown.goal_delay_days} 天` : "基本不影响"}</strong></div>
            <div><span>需要卖投资吗</span><strong>{shown.needs_investment_sale ? "可能需要" : "不需要"}</strong></div>
          </div>
        </Card>
      ) : null}

      {shown?.ready && shown.verdict && isSimulating ? (
        <div className="decision-detail-grid">
          <Card className="card-pad before-after-card">
            <div className="card-head"><div><h2>花钱前后，一眼对比</h2><p>不是只看“买不买得起”，还看买完以后舒不舒服。</p></div></div>
            <div className="before-after">
              <div><span>现在</span><strong>{money(shown.simulation?.cash_before_cny, hidden)}</strong><small>可用现金</small><b>{months(shown.battery?.essential_only_months_before)}</b><small>必要生活续航</small></div>
              <ArrowRight/>
              <div><span>花完</span><strong>{money(shown.simulation?.cash_after_cny, hidden)}</strong><small>可用现金</small><b>{months(shown.battery?.essential_only_months_after)}</b><small>必要生活续航</small></div>
            </div>
          </Card>
          <Card className="card-pad regret-card">
            <div className="card-head"><div><h2>最可能后悔的地方</h2><p>先看到代价，决定权仍然在你。</p></div></div>
            {shown.regret_warnings?.length ? <ul>{shown.regret_warnings.map((item)=><li key={item}><AlertTriangle/>{item}</li>)}</ul> : <div className="quiet-state"><CheckCircle2/><strong>没有触发明显预警</strong><span>预算仍在当前保护线以内。</span></div>}
          </Card>
          <Card className="card-pad alternative-card">
            <div className="card-head"><div><h2>更轻松的替代做法</h2><p>不是只有“买”和“不买”两种选择。</p></div></div>
            <ol>{shown.alternatives?.map((item,index)=><li key={item}><b>{index+1}</b><span>{item}</span></li>)}</ol>
          </Card>
          <Card className="card-pad protection-card">
            <div className="card-head"><div><h2>怀特替你守住了什么</h2><p>放心花额度会先扣开这些不能重复使用的钱。</p></div></div>
            <div className="protection-list"><div><ShieldCheck/><span>应急资金</span><strong>{money(shown.protection?.emergency_reserve_cny, hidden)}</strong></div><div><CalendarDays/><span>未来 90 天支出</span><strong>{money(shown.protection?.upcoming_90d_cny, hidden)}</strong></div><div><Coins/><span>已答应给目标的钱</span><strong>{money(shown.protection?.committed_goal_cash_cny, hidden)}</strong></div></div>
          </Card>
        </div>
      ) : null}

      {history.length ? (
        <Card className="card-pad spending-history">
          <div className="card-head"><div><h2>以前裁决过的事</h2><p>不用凭印象猜，回头看看当时为什么这样决定。</p></div></div>
          <div>{history.slice(0,6).map((row)=><button key={row.id} onClick={()=>{setPreview(row.result);setRuling(null);setDecision(row.decision);setAmount(row.amount_cny);}}><span className={verdictClass[row.verdict]}>{row.result.verdict_label}</span><div><strong>{row.decision}</strong><small>{formatDate(row.created_at)}</small></div><b>{money(row.amount_cny, hidden)}</b><ArrowRight/></button>)}</div>
        </Card>
      ) : null}
    </>
  );
}

export default function SpendingPage() {
  return <Protected><SpendingContent/></Protected>;
}
