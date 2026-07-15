"use client";

import { Protected } from "@/components/app-shell";
import { Badge, Button, Card, Empty, Field, Modal, Skeleton } from "@/components/ui";
import { api, errorMessage, formatDate, money, percent } from "@/lib/api";
import { CalendarClock, CircleAlert, Coins, LockKeyhole, Plus, Save, Sparkles, Trash2, Wallet } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

type FundingMap = {
  has_snapshot: boolean;
  net_worth_cny: string;
  committed_to_goals_cny: string;
  standalone_obligations_cny: string;
  free_net_worth_cny: string;
  rule: string;
  assets: Array<{ asset_key: string; name: string; account_alias?: string; asset_type: string; value_cny: string; committed_cny: string; free_cny: string }>;
  goals: Array<{ id: string; name: string; target_cny: string; allocated_cny: string; due_date?: string }>;
  allocations: Array<{ id: string; asset_key: string; goal_id: string; amount_cny: string }>;
  obligations: Array<{ id: string; goal_id?: string; title: string; category: string; amount_cny: string; due_date: string; likelihood: string; status: string; notes: string }>;
};

const categories = [
  ["TUITION", "学费"], ["RENT", "房租"], ["INSURANCE", "保险"], ["TAX", "税费"], ["MOVE", "签证 / 搬家"],
  ["WEDDING", "婚礼"], ["CAR", "买车"], ["FAMILY", "家庭支持"], ["LOAN", "贷款到期"], ["MEDICAL", "医疗支出"], ["OTHER", "其他"],
] as const;

function FundingContent() {
  const [data, setData] = useState<FundingMap | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [obligationOpen, setObligationOpen] = useState(false);
  const [obligation, setObligation] = useState({ title: "", category: "TUITION", amount_cny: "", due_date: "", likelihood: "CERTAIN", goal_id: "", notes: "" });

  async function load() {
    try {
      const result = await api<FundingMap>("/funding/map");
      setData(result);
      setValues(Object.fromEntries(result.allocations.map((item) => [`${item.asset_key}|${item.goal_id}`, item.amount_cny])));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, []);

  const drafts = useMemo(() => Object.entries(values).filter(([, value]) => Number(value) > 0).map(([key, amount_cny]) => {
    const [asset_key, goal_id] = key.split("|");
    return { asset_key, goal_id, amount_cny };
  }), [values]);

  async function saveAllocations() {
    setSaving(true); setError("");
    try {
      const result = await api<FundingMap>("/funding/allocations", { method: "PUT", body: JSON.stringify({ allocations: drafts }) });
      setData(result);
      setValues(Object.fromEntries(result.allocations.map((item) => [`${item.asset_key}|${item.goal_id}`, item.amount_cny])));
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
    <section className="freedom-metrics">
      <Card><span>账面净资产</span><strong>{money(data.net_worth_cny)}</strong><small>最新确认快照</small></Card>
      <Card><span>已承诺给目标</span><strong>{money(data.committed_to_goals_cny)}</strong><small>不会被重复计算</small></Card>
      <Card><span>独立未来义务</span><strong>{money(data.standalone_obligations_cny)}</strong><small>未关联目标的确定支出</small></Card>
      <Card className="free-net-card"><span>真正自由净资产</span><strong>{money(data.free_net_worth_cny)}</strong><small>净资产 - 已归属目标 - 独立义务</small></Card>
    </section>
    <Card className="card-pad one-yuan-rule"><LockKeyhole /><div><strong>一元一归属</strong><p>{data.rule}</p></div></Card>
    <Card className="card-pad allocation-studio">
      <div className="card-head"><div><h2>把真实资产分给未来目标</h2><p>每行是一项资产，每列是一个目标。系统会在保存时严格检查总额。</p></div><Button loading={saving} onClick={saveAllocations}><Save /> 保存资金归属</Button></div>
      {!data.goals.length ? <Empty title="还没有财务目标" body="先写下目标，再回来给它安排专属资金。" action={<a href="/goals"><Button>去写目标</Button></a>} /> : <div className="allocation-table-wrap"><table className="allocation-table"><thead><tr><th>资产项目</th><th>当前价值</th>{data.goals.map((goal) => <th key={goal.id}><span>{goal.name}</span><small>{money(goal.allocated_cny)} / {money(goal.target_cny)}</small></th>)}<th>仍可分配</th></tr></thead><tbody>{data.assets.map((asset) => {
        const used = data.goals.reduce((sum, goal) => sum + Number(values[`${asset.asset_key}|${goal.id}`] || 0), 0);
        const free = Number(asset.value_cny) - used;
        return <tr key={asset.asset_key}><td><Wallet /><span><strong>{asset.name}</strong><small>{asset.account_alias || asset.asset_type}</small></span></td><td>{money(asset.value_cny)}</td>{data.goals.map((goal) => <td key={goal.id}><input inputMode="decimal" value={values[`${asset.asset_key}|${goal.id}`] || ""} onChange={(e) => setValues({ ...values, [`${asset.asset_key}|${goal.id}`]: e.target.value })} placeholder="0" aria-label={`${asset.name} 分配给 ${goal.name}`} /></td>)}<td className={free < 0 ? "negative" : ""}>{money(free)}</td></tr>;
      })}</tbody></table></div>}
    </Card>
    <Card className="card-pad obligation-map">
      <div className="card-head"><div className="card-title-row"><div className="card-icon"><CalendarClock /></div><div><h2>未来义务地图</h2><p>沿着时间往前看，提前知道哪些钱已经有了去处。</p></div></div><Badge tone="purple">{data.obligations.length} 笔待发生</Badge></div>
      {data.obligations.length ? <div className="obligation-timeline">{data.obligations.map((item, index) => <div key={item.id}><i /><div className="obligation-date"><strong>{formatDate(item.due_date)}</strong><small>{index === 0 ? "最近一笔" : "未来"}</small></div><div className="obligation-copy"><Badge tone={item.likelihood === "CERTAIN" ? "warning" : "purple"}>{item.likelihood === "CERTAIN" ? "确定支出" : "大概率"}</Badge><strong>{item.title}</strong><span>{money(item.amount_cny)}</span>{item.notes ? <p>{item.notes}</p> : null}</div><button className="icon-button danger-text" onClick={() => removeObligation(item.id)}><Trash2 /></button></div>)}</div> : <Empty title="未来时间轴还是空的" body="把学费、保险、搬家、贷款到期等较确定的大额支出记下来。" />}
    </Card>
    <Modal open={obligationOpen} onClose={() => setObligationOpen(false)} title="记录一笔未来支出"><form onSubmit={addObligation}><div className="form-grid"><Field label="支出名称"><input value={obligation.title} onChange={(e) => setObligation({ ...obligation, title: e.target.value })} required /></Field><Field label="类型"><select value={obligation.category} onChange={(e) => setObligation({ ...obligation, category: e.target.value })}>{categories.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></Field><Field label="预计金额（元）"><input inputMode="decimal" value={obligation.amount_cny} onChange={(e) => setObligation({ ...obligation, amount_cny: e.target.value })} required /></Field><Field label="预计日期"><input type="date" value={obligation.due_date} onChange={(e) => setObligation({ ...obligation, due_date: e.target.value })} required /></Field><Field label="发生概率"><select value={obligation.likelihood} onChange={(e) => setObligation({ ...obligation, likelihood: e.target.value })}><option value="CERTAIN">确定会发生</option><option value="LIKELY">大概率会发生</option></select></Field><Field label="关联目标"><select value={obligation.goal_id} onChange={(e) => setObligation({ ...obligation, goal_id: e.target.value })}><option value="">不关联目标</option>{data.goals.map((goal) => <option value={goal.id} key={goal.id}>{goal.name}</option>)}</select></Field><Field label="备注" className="span-2"><textarea value={obligation.notes} onChange={(e) => setObligation({ ...obligation, notes: e.target.value })} /></Field></div><div className="form-actions"><Button type="button" variant="ghost" onClick={() => setObligationOpen(false)}>取消</Button><Button loading={saving}><Coins /> 放入未来地图</Button></div></form></Modal>
  </>;
}

export default function FundingPage() { return <Protected><FundingContent /></Protected>; }
