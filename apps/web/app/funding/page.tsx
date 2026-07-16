"use client";

import { Protected } from "@/components/app-shell";
import { Badge, Button, Card, Empty, Field, Modal, Skeleton } from "@/components/ui";
import { api, ApiError, errorMessage, formatDate, money } from "@/lib/api";
import { CalendarClock, ChevronDown, ChevronUp, CircleAlert, CircleCheck, Coins, Layers3, LockKeyhole, Plus, Save, Trash2, Wallet } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type FundingMap = {
  has_snapshot: boolean;
  snapshot_id?: string | null;
  net_worth_cny: string;
  committed_to_goals_cny: string;
  standalone_obligations_cny: string;
  free_net_worth_cny: string;
  rule: string;
  assets: Array<{ asset_key: string; name: string; account_alias?: string; asset_type: string; value_cny: string; committed_cny: string; free_cny: string }>;
  asset_categories: Array<{ asset_type: string; asset_count: number; value_cny: string; committed_cny: string; free_cny: string }>;
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

const assetTypeLabels: Record<string, string> = {
  CASH: "现金",
  FIXED_DEPOSIT: "定期存款",
  STOCK: "股票",
  FUND: "基金",
  BOND: "债券",
  GOLD: "黄金",
  PHYSICAL_GOLD: "实物黄金",
  PENSION: "公积金 / 养老金",
  PROPERTY: "房产",
  VEHICLE: "车辆",
  LOAN_RECEIVABLE: "借出款 / 应收款",
  OTHER: "其他资产",
};

function cents(value: string | number): number {
  const amount = Number(value);
  return Number.isFinite(amount) ? Math.round((amount + Number.EPSILON) * 100) / 100 : 0;
}

function FundingContent() {
  const [data, setData] = useState<FundingMap | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [controls, setControls] = useState<Record<string, AllocationControl>>({});
  const [selectedGoalId, setSelectedGoalId] = useState("");
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [obligationOpen, setObligationOpen] = useState(false);
  const [obligation, setObligation] = useState({ title: "", category: "TUITION", amount_cny: "", due_date: "", likelihood: "CERTAIN", goal_id: "", notes: "" });
  const currentMapRef = useRef<FundingMap | null>(null);
  const allocationDraftDirtyRef = useRef(false);

  const applyFundingMap = useCallback((result: FundingMap) => {
    const categoryRows = result.asset_categories || Object.values(result.assets.reduce<Record<string, FundingMap["asset_categories"][number]>>((groups, asset) => {
      const group = groups[asset.asset_type] || { asset_type: asset.asset_type, asset_count: 0, value_cny: "0", committed_cny: "0", free_cny: "0" };
      groups[asset.asset_type] = { ...group, asset_count: group.asset_count + 1, value_cny: String(cents(group.value_cny) + cents(asset.value_cny)), committed_cny: String(cents(group.committed_cny) + cents(asset.committed_cny)), free_cny: String(cents(group.free_cny) + cents(asset.free_cny)) };
      return groups;
    }, {}));
    const normalizedResult = { ...result, asset_categories: categoryRows };
    currentMapRef.current = normalizedResult;
    allocationDraftDirtyRef.current = false;
    setData(normalizedResult);
    setValues(Object.fromEntries(result.allocations.map((item) => [`${item.asset_key}|${item.goal_id}`, item.amount_cny])));
    setControls(Object.fromEntries(result.assets.map((asset) => [asset.asset_key, { goalId: "", mode: "" }])));
    setSelectedGoalId((current) => result.goals.some((goal) => goal.id === current) ? current : result.goals[0]?.id || "");
  }, []);

  const load = useCallback(async (preserveSameSnapshotDraft = false): Promise<boolean> => {
    try {
      const result = await api<FundingMap>("/funding/map");
      const previousSnapshotId = currentMapRef.current?.snapshot_id;
      if (preserveSameSnapshotDraft && allocationDraftDirtyRef.current && previousSnapshotId === result.snapshot_id) {
        return true;
      }
      applyFundingMap(result);
      setError(previousSnapshotId && previousSnapshotId !== result.snapshot_id
        ? "检测到最新资产清算，资产列表已实时更新；旧清算中的未保存归属没有带入。"
        : "");
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setLoading(false);
    }
  }, [applyFundingMap]);
  useEffect(() => {
    void load();
    const refresh = () => { if (document.visibilityState === "visible") void load(true); };
    const onFundingChanged = () => { void load(); };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("funding-assets-changed", onFundingChanged);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("funding-assets-changed", onFundingChanged);
    };
  }, [load]);

  const drafts = useMemo(() => Object.entries(values).map(([key, value]) => [key, value.trim().replace(/[,，\s]/g, "")] as const).filter(([, value]) => Number(value) > 0).map(([key, amount_cny]) => {
    const [asset_key, goal_id] = key.split("|");
    return { asset_key, goal_id, amount_cny };
  }), [values]);
  const draftGoalTotals = useMemo(() => Object.fromEntries((data?.goals || []).map((goal) => [goal.id, drafts.filter((item) => item.goal_id === goal.id).reduce((sum, item) => sum + Number(item.amount_cny), 0)])), [data?.goals, drafts]);
  const assetsByType = useMemo(() => Object.fromEntries((data?.asset_categories || []).map((category) => [category.asset_type, (data?.assets || []).filter((asset) => asset.asset_type === category.asset_type)])), [data]);

  function setAssetGoalAllocation(assetKey: string, goalId: string, amount: string) {
    allocationDraftDirtyRef.current = true;
    setValues((current) => {
      const next = { ...current };
      const pairKey = `${assetKey}|${goalId}`;
      if (amount) next[pairKey] = amount;
      else delete next[pairKey];
      return next;
    });
  }

  function allocatedToOtherGoals(assetKey: string, goalId: string, source = values) {
    return cents(Object.entries(source).reduce((sum, [key, amount]) => {
      const [keyAsset, keyGoal] = key.split("|");
      return keyAsset === assetKey && keyGoal !== goalId ? sum + cents(amount) : sum;
    }, 0));
  }

  function changeSelectedGoal(goalId: string) {
    setSelectedGoalId(goalId);
    setControls((current) => Object.fromEntries(Object.keys(current).map((assetKey) => [assetKey, { goalId, mode: "" as AllocationMode }])));
  }

  function allocateFull(asset: FundingMap["assets"][number]) {
    const goalId = selectedGoalId;
    if (!goalId) return;
    allocationDraftDirtyRef.current = true;
    setValues((current) => {
      const next = { ...current };
      const availableToGoal = cents(cents(asset.value_cny) - allocatedToOtherGoals(asset.asset_key, goalId, current));
      const pairKey = `${asset.asset_key}|${goalId}`;
      if (availableToGoal > 0) next[pairKey] = String(availableToGoal);
      else delete next[pairKey];
      return next;
    });
    setControls((current) => ({ ...current, [asset.asset_key]: { goalId, mode: "FULL" } }));
  }

  function allocatePartial(asset: FundingMap["assets"][number]) {
    const goalId = selectedGoalId;
    if (!goalId) return;
    const currentValue = values[`${asset.asset_key}|${goalId}`] || "";
    const availableToGoal = cents(cents(asset.value_cny) - allocatedToOtherGoals(asset.asset_key, goalId));
    const amount = cents(currentValue) > 0 && cents(currentValue) < availableToGoal ? currentValue : "";
    setAssetGoalAllocation(asset.asset_key, goalId, amount);
    setControls((current) => ({ ...current, [asset.asset_key]: { goalId, mode: "PARTIAL" } }));
  }

  function clearAssetAllocation(assetKey: string) {
    if (!selectedGoalId) return;
    setAssetGoalAllocation(assetKey, selectedGoalId, "");
    setControls((current) => ({ ...current, [assetKey]: { goalId: selectedGoalId, mode: "" } }));
  }

  function allocateCategoryFull(assetType: string) {
    const goalId = selectedGoalId;
    if (!goalId) return;
    const categoryAssets = assetsByType[assetType] || [];
    allocationDraftDirtyRef.current = true;
    setValues((current) => {
      const next = { ...current };
      categoryAssets.forEach((asset) => {
        const pairKey = `${asset.asset_key}|${goalId}`;
        const availableToGoal = cents(cents(asset.value_cny) - allocatedToOtherGoals(asset.asset_key, goalId, current));
        if (availableToGoal > 0) next[pairKey] = String(availableToGoal);
        else delete next[pairKey];
      });
      return next;
    });
    setControls((current) => ({ ...current, ...Object.fromEntries(categoryAssets.map((asset) => [asset.asset_key, { goalId, mode: "FULL" as AllocationMode }])) }));
  }

  function clearCategory(assetType: string) {
    if (!selectedGoalId) return;
    const categoryAssets = assetsByType[assetType] || [];
    allocationDraftDirtyRef.current = true;
    setValues((current) => {
      const next = { ...current };
      categoryAssets.forEach((asset) => delete next[`${asset.asset_key}|${selectedGoalId}`]);
      return next;
    });
    setControls((current) => ({ ...current, ...Object.fromEntries(categoryAssets.map((asset) => [asset.asset_key, { goalId: selectedGoalId, mode: "" as AllocationMode }])) }));
  }

  function toggleCategory(assetType: string) {
    setExpandedTypes((current) => {
      const next = new Set(current);
      if (next.has(assetType)) next.delete(assetType); else next.add(assetType);
      return next;
    });
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
        const total = cents(drafts.filter((item) => item.asset_key === asset.asset_key).reduce((sum, item) => sum + Number(item.amount_cny), 0));
        if (!Number.isFinite(total) || total > cents(asset.value_cny)) {
          throw new Error(`“${asset.name}”的归属金额不能超过资产全额 ${money(asset.value_cny)}。`);
        }
        const control = controls[asset.asset_key];
        if (control?.mode === "PARTIAL") {
          const partial = cents(values[`${asset.asset_key}|${control.goalId}`] || "");
          const availableToGoal = cents(cents(asset.value_cny) - allocatedToOtherGoals(asset.asset_key, control.goalId));
          if (partial <= 0 || partial >= availableToGoal) {
            throw new Error(`“${asset.name}”选择了非全额放入，请填写大于 0 且小于当前目标最多可归属金额 ${money(availableToGoal)} 的金额。`);
          }
        }
      }
      const result = await api<FundingMap>("/funding/allocations", { method: "PUT", body: JSON.stringify({ snapshot_id: data?.snapshot_id, allocations: drafts }) });
      applyFundingMap(result);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const refreshed = await load();
        setError(refreshed ? `${errorMessage(e)} 最新数据已自动载入，没有保存旧页面中的归属。` : `${errorMessage(e)} 自动载入失败，请检查网络后重试。`);
      } else setError(errorMessage(e));
    } finally { setSaving(false); }
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
    setError("");
    try {
      await api(`/funding/obligations/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  if (loading) return <><div className="page-head"><div><div className="eyebrow">ONE YUAN · ONE PURPOSE</div><h1>资金归属与自由净资产</h1></div></div><Skeleton height={520} /></>;
  if (!data) return <Card className="card-pad"><Empty title="暂时无法读取资金归属" body={error || "请检查网络后重试。"} action={<Button onClick={() => void load()}>重新加载</Button>} /></Card>;
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
      <div className="card-head allocation-studio-head">
        <div><h2>按资产类别安排资金归属</h2><p>先在右侧统一选择归属目标，再把整个类别或单项资产全额、部分放入。</p></div>
        <div className="allocation-studio-head-actions">
          <Button loading={saving} onClick={saveAllocations}><Save /> 保存全部资金归属</Button>
          <Field label="选择归属到哪里">
            <select aria-label="统一选择资金归属目标" value={selectedGoalId} onChange={(e) => changeSelectedGoal(e.target.value)} disabled={!data.goals.length}>
              {!data.goals.length ? <option value="">暂无理财目标</option> : data.goals.map((goal) => <option value={goal.id} key={goal.id}>{goal.name}（当前 {money(draftGoalTotals[goal.id])} / 目标 {money(goal.target_cny)}）</option>)}
            </select>
          </Field>
        </div>
      </div>
      {!data.goals.length ? <Empty title="还没有财务目标" body="先写下目标，再回来给它安排专属资金。" action={<a href="/goals"><Button>去写目标</Button></a>} /> : !data.assets.length ? <Empty title="最新清算里没有可归属资产" body="请先在资产清算中确认至少一项非负债资产。" action={<a href="/clearing"><Button>前往资产清算</Button></a>} /> : <div className="allocation-category-list">{data.asset_categories.map((category) => {
        const categoryAssets = assetsByType[category.asset_type] || [];
        const categoryKeys = new Set(categoryAssets.map((asset) => asset.asset_key));
        const categoryDrafts = drafts.filter((item) => categoryKeys.has(item.asset_key));
        const selectedGoalCategoryDrafts = categoryDrafts.filter((item) => item.goal_id === selectedGoalId);
        const used = cents(categoryDrafts.reduce((sum, item) => sum + Number(item.amount_cny), 0));
        const free = cents(Number(category.value_cny) - used);
        const expanded = expandedTypes.has(category.asset_type);
        return <section className="allocation-category-card" key={category.asset_type}>
          <div className="allocation-category-summary">
            <div className="allocation-category-icon"><Layers3 /></div>
            <div><strong>{assetTypeLabels[category.asset_type] || category.asset_type}</strong><span>{category.asset_count} 项资产</span></div>
            <div><small>类别总额</small><strong>{money(category.value_cny)}</strong></div>
            <div><small>已安排</small><strong>{money(used)}</strong></div>
            <div><small>仍可分配</small><strong className={free < 0 ? "negative" : ""}>{money(free)}</strong></div>
          </div>
          <div className="allocation-category-actions">
            <Button type="button" onClick={() => allocateCategoryFull(category.asset_type)}>整类全部放入</Button>
            {selectedGoalCategoryDrafts.length ? <Button type="button" variant="ghost" onClick={() => clearCategory(category.asset_type)}>清除本目标的整类归属</Button> : null}
            <Button type="button" variant="secondary" onClick={() => toggleCategory(category.asset_type)}>{expanded ? <ChevronUp /> : <ChevronDown />}{expanded ? "收起类别详情" : "进入类别详情"}</Button>
          </div>
          {expanded ? <div className="allocation-category-detail">{categoryAssets.map((asset) => {
            const assigned = drafts.filter((item) => item.asset_key === asset.asset_key);
            const assetUsed = cents(assigned.reduce((sum, item) => sum + Number(item.amount_cny), 0));
            const assetFree = cents(Number(asset.value_cny) - assetUsed);
            const control = controls[asset.asset_key] || { goalId: selectedGoalId, mode: "" };
            const selectedAmount = values[`${asset.asset_key}|${control.goalId}`] || "";
            const selectedGoalAmount = values[`${asset.asset_key}|${selectedGoalId}`] || "";
            const selectedGoalCapacity = cents(cents(asset.value_cny) - allocatedToOtherGoals(asset.asset_key, selectedGoalId));
            return <article className="allocation-asset-card" key={asset.asset_key}>
              <div className="allocation-asset-summary"><Wallet /><span><strong>{asset.name}</strong><small>{asset.account_alias || assetTypeLabels[asset.asset_type] || asset.asset_type}</small></span><div><small>资产全额</small><strong>{money(asset.value_cny)}</strong></div></div>
              {assigned.length ? <div className="allocation-current"><span>当前归属</span>{assigned.map((item) => <Badge tone="purple" key={`${item.asset_key}|${item.goal_id}`}>{data.goals.find((goal) => goal.id === item.goal_id)?.name || "目标已变化"} · {money(item.amount_cny)}</Badge>)}</div> : <div className="allocation-current empty-current"><span>当前还没有归属</span></div>}
              <div className="allocation-controls">
                <div className="allocation-mode-buttons" aria-label={`${asset.name}的放入方式`}><Button type="button" variant={control.mode === "FULL" ? "primary" : "secondary"} onClick={() => allocateFull(asset)}>全额放入</Button><Button type="button" variant={control.mode === "PARTIAL" ? "primary" : "secondary"} onClick={() => allocatePartial(asset)}>非全额放入</Button></div>
                {control.mode === "PARTIAL" ? <Field label="手动输入放入金额" hint={`当前目标最多可归属 ${money(selectedGoalCapacity)}；尚未归属余额 ${money(assetFree)}`}><input autoFocus inputMode="decimal" value={selectedAmount} onChange={(e) => setAssetGoalAllocation(asset.asset_key, control.goalId, e.target.value)} placeholder="例如 3000" aria-label={`${asset.name}部分放入金额`} /></Field> : null}
              </div>
              <div className="allocation-asset-foot"><span>尚未归属、仍可放入 <strong className={assetFree < 0 ? "negative" : ""}>{money(assetFree)}</strong></span>{cents(selectedGoalAmount) > 0 ? <button type="button" onClick={() => clearAssetAllocation(asset.asset_key)}>清除当前目标的这项归属</button> : null}</div>
            </article>;
          })}</div> : null}
        </section>;
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
