"use client";

import { Protected } from "@/components/app-shell";
import { Badge, Button, Card, Empty, Field, Modal, Skeleton } from "@/components/ui";
import { api, errorMessage, formatDate, money, percent } from "@/lib/api";
import { CalendarClock, CircleAlert, CircleCheck, Coins, LockKeyhole, Plus, Save, Sparkles, Trash2, Wallet } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

type FundingMap = {
  has_snapshot: boolean;
  net_worth_cny: string;
  committed_to_goals_cny: string;
  standalone_obligations_cny: string;
  free_net_worth_cny: string;
  rule: string;
  assets: Array<{ asset_key: string; name: string; account_alias?: string; asset_type: string; value_cny: string; committed_cny: string; free_cny: string }>;
  goals: Array<{ id: string; name: string; target_cny: string; allocated_cny: string; due_date?: string; completion_status: "IN_PROGRESS" | "AWAITING_CONFIRMATION" | "CONFIRMED"; completion_confirmed_at?: string | null }>;
  allocations: Array<{ id: string; asset_key: string; goal_id: string; amount_cny: string }>;
  obligations: Array<{ id: string; goal_id?: string; title: string; category: string; amount_cny: string; due_date: string; likelihood: string; status: string; notes: string }>;
};

type AllocationMode = "" | "FULL" | "PARTIAL";
type AllocationControl = { goalId: string; mode: AllocationMode };

const categories = [
  ["TUITION", "学费"], ["RENT", "房租"], ["INSURANCE", "保险"], ["TAX", "税费"], ["MOVE", "签证 / 搬家"],
  ["WEDDING", "婚礼"], ["CAR", "买车"], ["FAMILY", "家庭支持"], ["LOAN", "贷款到期"], ["MEDICAL", "医疗支出"], ["OTHER", "其他"],
] as const;

function FundingContent() {
  const [data, setData] = useState<FundingMap | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [controls, setControls] = useState<Record<string, AllocationControl>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [obligationOpen, setObligationOpen] = useState(false);
  const [obligation, setObligation] = useState({ title: "", category: "TUITION", amount_cny: "", due_date: "", likelihood: "CERTAIN", goal_id: "", notes: "" });

  function applyFundingMap(result: FundingMap) {
    setData(result);
    setValues(Object.fromEntries(result.allocations.map((item) => [`${item.asset_key}|${item.goal_id}`, item.amount_cny])));
    setControls(Object.fromEntries(result.assets.map((asset) => {
      const assigned = result.allocations.filter((item) => item.asset_key === asset.asset_key);
      const first = assigned[0];
      const isFull = assigned.length === 1 && Math.abs(Number(first.amount_cny) - Number(asset.value_cny)) < 0.005;
      return [asset.asset_key, {
        goalId: first?.goal_id || result.goals[0]?.id || "",
        mode: isFull ? "FULL" : first ? "PARTIAL" : "",
      }];
    })));
  }

  async function load() {
    try {
      const result = await api<FundingMap>("/funding/map");
      applyFundingMap(result);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  const drafts = useMemo(() => Object.entries(values).map(([key, value]) => [key, value.trim().replace(/[,，\s]/g, "")] as const).filter(([, value]) => Number(value) > 0).map(([key, amount_cny]) => {
    const [asset_key, goal_id] = key.split("|");
    return { asset_key, goal_id, amount_cny };
  }), [values]);
  const draftGoalTotals = useMemo(() => Object.fromEntries((data?.goals || []).map((goal) => [goal.id, drafts.filter((item) => item.goal_id === goal.id).reduce((sum, item) => sum + Number(item.amount_cny), 0)])), [data?.goals, drafts]);

  function replaceAssetAllocation(assetKey: string, goalId: string, amount: string) {
    setValues((current) => {
      const next = Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${assetKey}|`)));
      if (amount) next[`${assetKey}|${goalId}`] = amount;
      return next;
    });
  }

  function selectGoal(assetKey: string, goalId: string) {
    setControls((current) => ({ ...current, [assetKey]: { goalId, mode: "" } }));
  }

  function allocateFull(asset: FundingMap["assets"][number]) {
    const goalId = controls[asset.asset_key]?.goalId || data?.goals[0]?.id || "";
    if (!goalId) return;
    replaceAssetAllocation(asset.asset_key, goalId, asset.value_cny);
    setControls((current) => ({ ...current, [asset.asset_key]: { goalId, mode: "FULL" } }));
  }

  function allocatePartial(asset: FundingMap["assets"][number]) {
    const goalId = controls[asset.asset_key]?.goalId || data?.goals[0]?.id || "";
    if (!goalId) return;
    const currentValue = values[`${asset.asset_key}|${goalId}`] || "";
    const amount = Number(currentValue) > 0 && Number(currentValue) < Number(asset.value_cny) ? currentValue : "";
    replaceAssetAllocation(asset.asset_key, goalId, amount);
    setControls((current) => ({ ...current, [asset.asset_key]: { goalId, mode: "PARTIAL" } }));
  }

  function clearAssetAllocation(assetKey: string) {
    replaceAssetAllocation(assetKey, "", "");
    setControls((current) => ({ ...current, [assetKey]: { goalId: current[assetKey]?.goalId || data?.goals[0]?.id || "", mode: "" } }));
  }

  async function saveAllocations() {
    setSaving(true); setError("");
    try {
      for (const value of Object.values(values)) {
        const normalized = value.trim().replace(/[,，\s]/g, "");
        if (normalized && (!Number.isFinite(Number(normalized)) || Number(normalized) < 0)) {
          throw new Error("归属金额需要填写 0 或更大的整数、小数。");
        }
      }
      for (const asset of data?.assets || []) {
        const total = drafts.filter((item) => item.asset_key === asset.asset_key).reduce((sum, item) => sum + Number(item.amount_cny), 0);
        if (!Number.isFinite(total) || total > Number(asset.value_cny) + 0.005) {
          throw new Error(`“${asset.name}”的归属金额不能超过资产全额 ${money(asset.value_cny)}。`);
        }
      }
      const result = await api<FundingMap>("/funding/allocations", { method: "PUT", body: JSON.stringify({ allocations: drafts }) });
      applyFundingMap(result);
    } catch (e) { setError(errorMessage(e)); } finally { setSaving(false); }
  }

  async function addObligation(e: FormEvent) {
    e.preventDefault(); setSaving(true); setError("");
    try {
      await api("/funding/obligations", { method: "POST", body: JSON.stringify({ ...obligation, goal_id: obligation.goal_id || null }) });
      setObligationOpen(false);
      setObligation({ title: "", category: "TUITION", amount_cny: "", due_date: "", likelihood: "CERTAIN", goal_id: "", notes: "" });
      await load();
    } catch (e) { setError(errorMessage(e)); } finally { setSaving(false); }
  }
  async function removeObligation(id: string) {
    if (!confirm("确定删除这笔未来支出吗？")) return;
    await api(`/funding/obligations/${id}`, { method: "DELETE" });
    await load();
  }

  if (loading) return <><div className="page-head"><div><div className="eyebrow">ONE YUAN · ONE PURPOSE</div><h1>资金归属与自由净资产</h1></div></div><Skeleton height={520} /></>;
  if (!data?.has_snapshot) return <Card className="card-pad"><Empty title="先完成一次资产清算" body="有了真实资产明细，才能确保同一笔钱不会被多个目标重复使用。" action={<a href="/clearing"><Button>前往资产清算</Button></a>} /></Card>;
  return <>
    <div className="page-head funding-head"><div><div className="eyebrow">ONE YUAN · ONE PURPOSE</div><h1>自由净资产</h1><p>给每一笔已经有用途的钱一个归属，剩下的才是真正可以自由决定的部分。</p></div><Button onClick={() => setObligationOpen(true)}><Plus /> 记录未来支出</Button></div>
    {error ? <div className="inline-error"><CircleAlert />{error}</div> : null}
    {data.goals.filter((goal) => goal.completion_status === "AWAITING_CONFIRMATION").map((goal) => <div className="goal-completion-global-banner" key={goal.id}><CircleCheck /><div><strong>您的{goal.name}理财目标已完成，请前往确认！</strong><span>这笔目标资金已经达到设定金额。</span></div><a href={`/goals?goal=${goal.id}`}>前往确认</a></div>)}
    <section className="freedom-metrics">
      <Card><span>账面净资产</span><strong>{money(data.net_worth_cny)}</strong><small>最新确认快照</small></Card>
      <Card><span>已承诺给目标</span><strong>{money(data.committed_to_goals_cny)}</strong><small>不会被重复计算</small></Card>
      <Card><span>独立未来义务</span><strong>{money(data.standalone_obligations_cny)}</strong><small>未关联目标的确定支出</small></Card>
      <Card className="free-net-card"><span>真正自由净资产</span><strong>{money(data.free_net_worth_cny)}</strong><small>净资产 - 已归属目标 - 独立义务</small></Card>
    </section>
    <Card className="card-pad one-yuan-rule"><LockKeyhole /><div><strong>一元一归属</strong><p>{data.rule}</p></div></Card>
    <Card className="card-pad allocation-studio">
      <div className="card-head"><div><h2>把真实资产分给未来目标</h2><p>每项资产先选目标，再选择全额或部分放入；保存时仍会严格检查资产总额。</p></div><Button loading={saving} onClick={saveAllocations}><Save /> 保存资金归属</Button></div>
      {!data.goals.length ? <Empty title="还没有财务目标" body="先写下目标，再回来给它安排专属资金。" action={<a href="/goals"><Button>去写目标</Button></a>} /> : <div className="allocation-asset-list">{data.assets.map((asset) => {
        const assigned = drafts.filter((item) => item.asset_key === asset.asset_key);
        const used = assigned.reduce((sum, item) => sum + Number(item.amount_cny), 0);
        const free = Number(asset.value_cny) - used;
        const control = controls[asset.asset_key] || { goalId: data.goals[0]?.id || "", mode: "" };
        const selectedAmount = values[`${asset.asset_key}|${control.goalId}`] || "";
        return <article className="allocation-asset-card" key={asset.asset_key}>
          <div className="allocation-asset-summary"><Wallet /><span><strong>{asset.name}</strong><small>{asset.account_alias || asset.asset_type}</small></span><div><small>当前全额</small><strong>{money(asset.value_cny)}</strong></div></div>
          {assigned.length ? <div className="allocation-current"><span>当前归属</span>{assigned.map((item) => <Badge tone="purple" key={`${item.asset_key}|${item.goal_id}`}>{data.goals.find((goal) => goal.id === item.goal_id)?.name || "目标"} · {money(item.amount_cny)}</Badge>)}</div> : <div className="allocation-current empty-current"><span>当前还没有归属</span></div>}
          <div className="allocation-controls">
            <Field label="选定理财目标"><select value={control.goalId} onChange={(e) => selectGoal(asset.asset_key, e.target.value)}>{data.goals.map((goal) => <option value={goal.id} key={goal.id}>{goal.name}（已归属 {money(draftGoalTotals[goal.id])} / 目标 {money(goal.target_cny)}）</option>)}</select></Field>
            <div className="allocation-mode-buttons" aria-label={`${asset.name}的放入方式`}><Button type="button" variant={control.mode === "FULL" ? "primary" : "secondary"} onClick={() => allocateFull(asset)}>全额放入</Button><Button type="button" variant={control.mode === "PARTIAL" ? "primary" : "secondary"} onClick={() => allocatePartial(asset)}>非全额放入</Button></div>
            {control.mode === "PARTIAL" ? <Field label="手动输入放入金额" hint={`最多可填 ${money(asset.value_cny)}`}><input autoFocus inputMode="decimal" value={selectedAmount} onChange={(e) => replaceAssetAllocation(asset.asset_key, control.goalId, e.target.value)} placeholder="例如 10000" aria-label={`${asset.name}部分放入金额`} /></Field> : null}
          </div>
          <div className="allocation-asset-foot"><span>放入后仍可分配 <strong className={free < 0 ? "negative" : ""}>{money(free)}</strong></span>{assigned.length ? <button type="button" onClick={() => clearAssetAllocation(asset.asset_key)}>清除这项归属</button> : null}</div>
        </article>;
      })}</div>}
    </Card>
    <Card className="card-pad obligation-map">
      <div className="card-head"><div className="card-title-row"><div className="card-icon"><CalendarClock /></div><div><h2>未来义务地图</h2><p>沿着时间往前看，提前知道哪些钱已经有了去处。</p></div></div><Badge tone="purple">{data.obligations.length} 笔待发生</Badge></div>
      {data.obligations.length ? <div className="obligation-timeline">{data.obligations.map((item, index) => <div key={item.id}><i /><div className="obligation-date"><strong>{formatDate(item.due_date)}</strong><small>{index === 0 ? "最近一笔" : "未来"}</small></div><div className="obligation-copy"><Badge tone={item.likelihood === "CERTAIN" ? "warning" : "purple"}>{item.likelihood === "CERTAIN" ? "确定支出" : "大概率"}</Badge><strong>{item.title}</strong><span>{money(item.amount_cny)}</span>{item.notes ? <p>{item.notes}</p> : null}</div><button className="icon-button danger-text" onClick={() => removeObligation(item.id)}><Trash2 /></button></div>)}</div> : <Empty title="未来时间轴还是空的" body="把学费、保险、搬家、贷款到期等较确定的大额支出记下来。" />}
    </Card>
    <Modal open={obligationOpen} onClose={() => setObligationOpen(false)} title="记录一笔未来支出"><form onSubmit={addObligation}><div className="form-grid"><Field label="支出名称"><input value={obligation.title} onChange={(e) => setObligation({ ...obligation, title: e.target.value })} required /></Field><Field label="类型"><select value={obligation.category} onChange={(e) => setObligation({ ...obligation, category: e.target.value })}>{categories.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></Field><Field label="预计金额（元）"><input inputMode="decimal" value={obligation.amount_cny} onChange={(e) => setObligation({ ...obligation, amount_cny: e.target.value })} required /></Field><Field label="预计日期"><input type="date" value={obligation.due_date} onChange={(e) => setObligation({ ...obligation, due_date: e.target.value })} required /></Field><Field label="发生概率"><select value={obligation.likelihood} onChange={(e) => setObligation({ ...obligation, likelihood: e.target.value })}><option value="CERTAIN">确定会发生</option><option value="LIKELY">大概率会发生</option></select></Field><Field label="关联目标"><select value={obligation.goal_id} onChange={(e) => setObligation({ ...obligation, goal_id: e.target.value })}><option value="">不关联目标</option>{data.goals.map((goal) => <option value={goal.id} key={goal.id}>{goal.name}</option>)}</select></Field><Field label="备注" className="span-2"><textarea value={obligation.notes} onChange={(e) => setObligation({ ...obligation, notes: e.target.value })} /></Field></div><div className="form-actions"><Button type="button" variant="ghost" onClick={() => setObligationOpen(false)}>取消</Button><Button loading={saving}><Coins /> 放入未来地图</Button></div></form></Modal>
  </>;
}

export default function FundingPage() { return <Protected><FundingContent /></Protected>; }
