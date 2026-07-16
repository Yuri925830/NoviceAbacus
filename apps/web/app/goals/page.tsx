"use client";

import { Protected } from "@/components/app-shell";
import { Badge, Button, Card, Empty, Field, Modal, Skeleton } from "@/components/ui";
import { api, errorMessage, formatDate, money, percent } from "@/lib/api";
import type { AgentRecommendation, AgentResult } from "@/lib/agent";
import {
  ArrowRight,
  CalendarDays,
  CircleAlert,
  CircleCheck,
  Flag,
  PartyPopper,
  PiggyBank,
  Pencil,
  Plus,
  Sparkles,
  Target,
  Trash2,
  WalletCards,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

type GoalPlan = {
  id: string;
  monthly_income_cny: string;
  monthly_fixed_expenses_cny: string;
  monthly_safety_buffer_cny: string;
  calculation: {
    monthly_surplus_cny: string;
    monthly_available_after_buffer_cny: string;
    suggested_monthly_contribution_cny: string;
    required_monthly_for_due_date_cny?: string | null;
    estimated_months?: number | null;
    gap_cny: string;
    calculation_note: string;
  };
  guidance: AgentResult;
  provider: string;
  model: string;
  updated_at: string;
};

type FinancialGoal = {
  id: string;
  name: string;
  goal_type: string;
  target_cny: string;
  due_date?: string | null;
  included_asset_types: string[];
  current_cny: string;
  progress_pct: string;
  gap_cny: string;
  months_left?: number | null;
  required_monthly_cny?: string | null;
  analysis: string[];
  completion_status: "IN_PROGRESS" | "AWAITING_CONFIRMATION" | "CONFIRMED";
  completion_confirmed_at?: string | null;
  plan?: GoalPlan | null;
};

const goalTypeLabels: Record<string, string> = {
  NET_WORTH: "净资产目标",
  LIQUID_CASH: "可用现金目标",
  SPECIFIC: "特定用途目标",
};

const specificTypes = [
  ["CASH", "现金与存款"],
  ["STOCK", "股票"],
  ["FUND", "基金"],
  ["GOLD", "黄金"],
  ["PENSION", "公积金 / 养老金"],
  ["PROPERTY", "房产"],
] as const;

function formatGoalDate(value: string): string {
  const normalized = value.length === 10 ? `${value}T00:00:00` : value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(normalized));
}

function GoalsContent() {
  const [goals, setGoals] = useState<FinancialGoal[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editMode, setEditMode] = useState<"EDIT" | "UPGRADE">("EDIT");
  const [planEditOpen, setPlanEditOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [planning, setPlanning] = useState(false);
  const [confirmingCompletion, setConfirmingCompletion] = useState(false);
  const [celebrationGoal, setCelebrationGoal] = useState<FinancialGoal | null>(null);
  const [celebrationReady, setCelebrationReady] = useState(false);
  const [newGoal, setNewGoal] = useState({
    name: "",
    goal_type: "NET_WORTH",
    target_cny: "",
    due_date: "",
    included_asset_types: [] as string[],
  });
  const [editGoal, setEditGoal] = useState({
    name: "",
    goal_type: "NET_WORTH",
    target_cny: "",
    due_date: "",
    included_asset_types: [] as string[],
  });
  const [planDraft, setPlanDraft] = useState({
    monthly_income_cny: "",
    monthly_fixed_expenses_cny: "",
    monthly_safety_buffer_cny: "",
    suggested_monthly_contribution_cny: "",
    executive_summary: "",
    analysis: "",
    recommendations: [] as AgentRecommendation[],
  });
  const [budget, setBudget] = useState({
    monthly_income_cny: "",
    monthly_fixed_expenses_cny: "",
    monthly_safety_buffer_cny: "",
    provider: "auto",
  });

  async function load(preferredId?: string) {
    setError("");
    try {
      const data = await api<FinancialGoal[]>("/goals");
      setGoals(data);
      const fromUrl =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("goal") || ""
          : "";
      const next = preferredId || selectedId || fromUrl || data[0]?.id || "";
      setSelectedId(data.some((goal) => goal.id === next) ? next : data[0]?.id || "");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // The first request restores the selected goal from the URL when available.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = useMemo(
    () => goals.find((goal) => goal.id === selectedId) || null,
    [goals, selectedId],
  );

  function openGoal(id: string) {
    setSelectedId(id);
    const url = new URL(window.location.href);
    url.searchParams.set("goal", id);
    window.history.replaceState({}, "", url);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function createGoal(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const created = await api<{ id: string }>("/goals", {
        method: "POST",
        body: JSON.stringify({
          ...newGoal,
          due_date: newGoal.due_date || null,
          included_asset_types:
            newGoal.goal_type === "SPECIFIC" ? newGoal.included_asset_types : [],
        }),
      });
      setCreateOpen(false);
      setNewGoal({
        name: "",
        goal_type: "NET_WORTH",
        target_cny: "",
        due_date: "",
        included_asset_types: [],
      });
      await load(created.id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function removeGoal(goal: FinancialGoal) {
    if (!confirm(`确定删除“${goal.name}”吗？已归属资金会恢复为可分配，已经生成的智能计划也会一起删除。`)) return;
    try {
      await api(`/goals/${goal.id}`, { method: "DELETE" });
      setSelectedId("");
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  function beginEditGoal(goal: FinancialGoal, mode: "EDIT" | "UPGRADE" = "EDIT") {
    setEditMode(mode);
    setEditGoal({
      name: goal.name,
      goal_type: goal.goal_type,
      target_cny: goal.target_cny,
      due_date: goal.due_date?.slice(0, 10) || "",
      included_asset_types: goal.included_asset_types || [],
    });
    setEditOpen(true);
  }

  async function confirmCompletion(goal: FinancialGoal) {
    setConfirmingCompletion(true);
    setError("");
    try {
      const confirmed = await api<FinancialGoal>(`/goals/${goal.id}/completion/confirm`, { method: "POST" });
      setGoals((current) => current.map((item) => item.id === confirmed.id ? confirmed : item));
      window.dispatchEvent(new CustomEvent("goal-completion-confirmed", { detail: { goalId: confirmed.id } }));
      setCelebrationGoal(confirmed);
      setCelebrationReady(false);
      window.setTimeout(() => setCelebrationReady(true), 1300);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setConfirmingCompletion(false);
    }
  }

  function keepCompletedGoal() {
    setCelebrationGoal(null);
    setCelebrationReady(false);
  }

  function upgradeCompletedGoal(goal: FinancialGoal) {
    keepCompletedGoal();
    beginEditGoal(goal, "UPGRADE");
  }

  async function deleteCompletedGoal(goal: FinancialGoal) {
    keepCompletedGoal();
    await removeGoal(goal);
  }

  async function saveGoal(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      await api(`/goals/${selected.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          ...editGoal,
          due_date: editGoal.due_date || null,
          included_asset_types: editGoal.goal_type === "SPECIFIC" ? editGoal.included_asset_types : [],
        }),
      });
      setEditOpen(false);
      await load(selected.id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  function beginEditPlan(plan: GoalPlan) {
    setPlanDraft({
      monthly_income_cny: plan.monthly_income_cny,
      monthly_fixed_expenses_cny: plan.monthly_fixed_expenses_cny,
      monthly_safety_buffer_cny: plan.monthly_safety_buffer_cny,
      suggested_monthly_contribution_cny: plan.calculation.suggested_monthly_contribution_cny,
      executive_summary: plan.guidance.executive_summary || "",
      analysis: (plan.guidance.analysis || []).join("\n"),
      recommendations: (plan.guidance.recommendations || []).map((item) => ({
        priority: item.priority || "MEDIUM",
        action: item.action || "",
        reason: item.reason || "",
        expected_impact: item.expected_impact || "",
        risk: item.risk || "",
        review_trigger: item.review_trigger || "",
      })),
    });
    setPlanEditOpen(true);
  }

  function updatePlanRecommendation(index: number, key: keyof AgentRecommendation, value: string) {
    setPlanDraft((current) => ({
      ...current,
      recommendations: current.recommendations.map((item, itemIndex) =>
        itemIndex === index ? ({ ...item, [key]: value } as AgentRecommendation) : item,
      ),
    }));
  }

  async function savePlan(e: FormEvent) {
    e.preventDefault();
    if (!selected?.plan) return;
    setSaving(true);
    setError("");
    try {
      await api(`/goals/${selected.id}/plan`, {
        method: "PATCH",
        body: JSON.stringify({
          monthly_income_cny: planDraft.monthly_income_cny,
          monthly_fixed_expenses_cny: planDraft.monthly_fixed_expenses_cny,
          monthly_safety_buffer_cny: planDraft.monthly_safety_buffer_cny || "0",
          suggested_monthly_contribution_cny: planDraft.suggested_monthly_contribution_cny,
          guidance: {
            ...selected.plan.guidance,
            executive_summary: planDraft.executive_summary,
            analysis: planDraft.analysis.split("\n").map((item) => item.trim()).filter(Boolean),
            recommendations: planDraft.recommendations,
          },
        }),
      });
      setPlanEditOpen(false);
      await load(selected.id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function buildPlan(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setPlanning(true);
    setError("");
    try {
      await api(`/goals/${selected.id}/plan`, {
        method: "POST",
        body: JSON.stringify({
          ...budget,
          monthly_safety_buffer_cny: budget.monthly_safety_buffer_cny || "0",
          depth: "complex",
        }),
      });
      await load(selected.id);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setPlanning(false);
    }
  }

  useEffect(() => {
    if (!selected?.plan) return;
    setBudget({
      monthly_income_cny: selected.plan.monthly_income_cny,
      monthly_fixed_expenses_cny: selected.plan.monthly_fixed_expenses_cny,
      monthly_safety_buffer_cny: selected.plan.monthly_safety_buffer_cny,
      provider: "auto",
    });
  }, [selected?.id, selected?.plan]);

  if (loading)
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">MY FINANCIAL GOALS</div>
            <h1>财务目标</h1>
          </div>
        </div>
        <Skeleton height={420} />
      </>
    );
  if (!goals.length && error) return <Card className="card-pad"><Empty title="暂时无法读取财务目标" body={error} action={<Button onClick={() => void load()}>重新加载</Button>} /></Card>;

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">MY FINANCIAL GOALS</div>
          <h1>把想去的地方，变成一步步能做到的计划</h1>
          <p>先写下目标。怀特会结合你的进度和每月收支，陪你找到更舒服、也更能坚持的节奏。</p>
        </div>
        <div className="page-actions">
          <Button onClick={() => setCreateOpen(true)}>
            <Plus /> 新建目标
          </Button>
        </div>
      </div>
      {error ? (
        <div className="inline-error">
          <CircleAlert /> <span>{error}</span>
        </div>
      ) : null}
      {goals.filter((goal) => goal.completion_status === "AWAITING_CONFIRMATION").map((goal) => (
        <div className="goal-completion-global-banner" key={goal.id}>
          <CircleCheck />
          <div><strong>您的{goal.name}理财目标已完成，请前往确认！</strong><span>确认后会播放庆祝礼花，并让你决定保留、升级或删除目标。</span></div>
          <button type="button" onClick={() => { openGoal(goal.id); window.setTimeout(() => document.getElementById("goal-completion-confirm")?.scrollIntoView({ behavior: "smooth", block: "center" }), 80); }}>前往确认</button>
        </div>
      ))}

      {!goals.length ? (
        <Card className="card-pad">
          <Empty
            title="想先为哪件事存下一笔钱？"
            body="可以是一笔应急金、一套房、一次进修，也可以只是让净资产稳稳长大。先写下第一个目标吧。"
            action={
              <Button onClick={() => setCreateOpen(true)}>
                <Target /> 写下第一个目标
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="goals-layout">
          <aside className="goal-list-panel">
            <div className="goal-list-title">
              <span>我的目标</span>
              <b>{goals.length}</b>
            </div>
            {goals.map((goal) => (
              <button
                key={goal.id}
                className={`goal-list-item ${goal.id === selectedId ? "active" : ""}`}
                onClick={() => openGoal(goal.id)}
              >
                <span className="goal-list-icon">
                  <Flag />
                </span>
                <span>
                  <strong>{goal.name}</strong>
                  <small>{goalTypeLabels[goal.goal_type] || goal.goal_type}</small>
                  <i>
                    <em style={{ width: `${Math.min(Number(goal.progress_pct), 100)}%` }} />
                  </i>
                </span>
                <b>{percent(goal.progress_pct)}</b>
                <ArrowRight />
              </button>
            ))}
          </aside>

          {selected ? (
            <div className="goal-detail">
              <Card className="goal-progress-card">
                <div className="goal-progress-head">
                  <div>
                    <Badge tone="purple">{goalTypeLabels[selected.goal_type] || selected.goal_type}</Badge>
                    <h2>{selected.name}</h2>
                    <p>
                      {selected.due_date
                        ? `希望在 ${formatGoalDate(selected.due_date)} 前完成`
                        : "没有赶时间，按自己的节奏前进就好"}
                    </p>
                  </div>
                  <div className="goal-head-actions">
                    <Button variant="ghost" onClick={() => beginEditGoal(selected)}>
                      <Pencil /> 编辑目标
                    </Button>
                    <button className="icon-button danger-text" onClick={() => removeGoal(selected)} title="删除目标">
                      <Trash2 />
                    </button>
                  </div>
                </div>
                <div className="goal-progress-number">
                  <strong>{percent(selected.progress_pct)}</strong>
                  <span>已经完成</span>
                </div>
                <div className="goal-progress-track">
                  <i style={{ width: `${Math.min(Number(selected.progress_pct), 100)}%` }} />
                </div>
                <div className="goal-metrics">
                  <div>
                    <span>现在</span>
                    <strong>{money(selected.current_cny)}</strong>
                  </div>
                  <div>
                    <span>目标</span>
                    <strong>{money(selected.target_cny)}</strong>
                  </div>
                  <div>
                    <span>还差</span>
                    <strong>{money(selected.gap_cny)}</strong>
                  </div>
                </div>
                {selected.completion_status === "AWAITING_CONFIRMATION" ? (
                  <div className="goal-completion-confirm" id="goal-completion-confirm">
                    <PartyPopper />
                    <div><strong>您的{selected.name}理财目标已完成，请前往确认！</strong><span>点击确认，正式记下这个完成时刻。</span></div>
                    <Button loading={confirmingCompletion} onClick={() => confirmCompletion(selected)}><CircleCheck /> 确认目标完成</Button>
                  </div>
                ) : selected.completion_status === "CONFIRMED" ? (
                  <div className="goal-completion-confirm confirmed">
                    <CircleCheck />
                    <div><strong>这个目标已经完成并确认</strong><span>你可以一直保留这枚里程碑，也可以把它升级成下一阶段目标。</span></div>
                    <Button variant="secondary" onClick={() => beginEditGoal(selected, "UPGRADE")}><Sparkles /> 升级目标</Button>
                  </div>
                ) : null}
              </Card>

              <div className="goal-detail-grid">
                <Card className="card-pad goal-analysis-card">
                  <div className="card-title-row">
                    <div className="card-icon"><WalletCards /></div>
                    <div>
                      <h2>进度小结</h2>
                      <p>先看清当下，再决定下一小步。</p>
                    </div>
                  </div>
                  <ul>
                    {selected.analysis.map((item) => <li key={item}>{item}</li>)}
                    {selected.required_monthly_cny ? (
                      <li>如果希望按期完成，每月大约需要准备 {money(selected.required_monthly_cny)}。</li>
                    ) : null}
                  </ul>
                </Card>

                <Card className="card-pad goal-plan-builder">
                  <div className="card-title-row">
                    <div className="card-icon"><Sparkles /></div>
                    <div>
                      <h2>请怀特制定智能计划</h2>
                      <p>告诉她每月稳定的收支，她会生成计划并直接收进这个目标里。</p>
                    </div>
                  </div>
                  <form onSubmit={buildPlan}>
                    <div className="form-grid">
                      <Field label="每月固定收入（元）">
                        <input
                          inputMode="decimal"
                          value={budget.monthly_income_cny}
                          onChange={(e) => setBudget({ ...budget, monthly_income_cny: e.target.value })}
                          placeholder="例如 12000"
                          required
                        />
                      </Field>
                      <Field label="每月固定支出（元）">
                        <input
                          inputMode="decimal"
                          value={budget.monthly_fixed_expenses_cny}
                          onChange={(e) => setBudget({ ...budget, monthly_fixed_expenses_cny: e.target.value })}
                          placeholder="例如 5000"
                          required
                        />
                      </Field>
                      <Field label="每月想保留的机动金（元）" hint="可以留空。它会被完整保留下来，不安排进目标。">
                        <input
                          inputMode="decimal"
                          value={budget.monthly_safety_buffer_cny}
                          onChange={(e) => setBudget({ ...budget, monthly_safety_buffer_cny: e.target.value })}
                          placeholder="例如 2000"
                        />
                      </Field>
                      <Field label="智能线路">
                        <select value={budget.provider} onChange={(e) => setBudget({ ...budget, provider: e.target.value })}>
                          <option value="auto">自动选择</option>
                          <option value="qwen">千问</option>
                          <option value="openai">OpenAI</option>
                        </select>
                      </Field>
                    </div>
                    <Button className="full-button" loading={planning}>
                      <Sparkles /> {selected.plan ? "重新制定并保存" : "生成并保存智能计划"}
                    </Button>
                  </form>
                </Card>
              </div>

              {selected.plan ? <SavedPlan plan={selected.plan} onEdit={() => beginEditPlan(selected.plan!)} /> : null}
            </div>
          ) : null}
        </div>
      )}

      {celebrationGoal ? <GoalCelebration goal={celebrationGoal} ready={celebrationReady} onKeep={keepCompletedGoal} onUpgrade={() => upgradeCompletedGoal(celebrationGoal)} onDelete={() => deleteCompletedGoal(celebrationGoal)} /> : null}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="写下一个新目标">
        <form onSubmit={createGoal}>
          <div className="form-grid">
            <Field label="目标名称">
              <input
                value={newGoal.name}
                onChange={(e) => setNewGoal({ ...newGoal, name: e.target.value })}
                placeholder="例如：准备一笔安心应急金"
                required
              />
            </Field>
            <Field label="目标类型">
              <select value={newGoal.goal_type} onChange={(e) => setNewGoal({ ...newGoal, goal_type: e.target.value })}>
                <option value="NET_WORTH">净资产目标</option>
                <option value="LIQUID_CASH">可用现金目标</option>
                <option value="SPECIFIC">特定资产目标</option>
              </select>
            </Field>
            <Field label="目标金额（元）">
              <input
                inputMode="decimal"
                value={newGoal.target_cny}
                onChange={(e) => setNewGoal({ ...newGoal, target_cny: e.target.value })}
                placeholder="例如 100000"
                required
              />
            </Field>
            <Field label="希望完成的日期" hint="没有明确日期也可以留空。">
              <input type="date" value={newGoal.due_date} onChange={(e) => setNewGoal({ ...newGoal, due_date: e.target.value })} />
            </Field>
            {newGoal.goal_type === "SPECIFIC" ? (
              <div className="span-2 goal-type-picker">
                <span>哪些资产算进这个目标？</span>
                <div>
                  {specificTypes.map(([value, label]) => (
                    <label key={value}>
                      <input
                        type="checkbox"
                        checked={newGoal.included_asset_types.includes(value)}
                        onChange={(e) =>
                          setNewGoal({
                            ...newGoal,
                            included_asset_types: e.target.checked
                              ? [...newGoal.included_asset_types, value]
                              : newGoal.included_asset_types.filter((item) => item !== value),
                          })
                        }
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
          <div className="form-actions">
            <Button variant="ghost" type="button" onClick={() => setCreateOpen(false)}>先不写</Button>
            <Button loading={saving}><Target /> 保存目标</Button>
          </div>
        </form>
      </Modal>

      <Modal open={editOpen} onClose={() => setEditOpen(false)} title={editMode === "UPGRADE" ? "升级理财目标" : "调整这个目标"}>
        <form onSubmit={saveGoal}>
          <div className="form-grid">
            <Field label="目标名称">
              <input value={editGoal.name} onChange={(e) => setEditGoal({ ...editGoal, name: e.target.value })} required />
            </Field>
            <Field label="目标类型">
              <select value={editGoal.goal_type} onChange={(e) => setEditGoal({ ...editGoal, goal_type: e.target.value })}>
                <option value="NET_WORTH">净资产目标</option>
                <option value="LIQUID_CASH">可用现金目标</option>
                <option value="SPECIFIC">特定资产目标</option>
              </select>
            </Field>
            <Field label="目标金额（元）" hint={editMode === "UPGRADE" ? "提高目标金额，或调整日期，开启下一阶段。" : undefined}>
              <input inputMode="decimal" value={editGoal.target_cny} onChange={(e) => setEditGoal({ ...editGoal, target_cny: e.target.value })} required />
            </Field>
            <Field label="希望完成的日期" hint="可以随时修改，也可以留空。">
              <input type="date" value={editGoal.due_date} onChange={(e) => setEditGoal({ ...editGoal, due_date: e.target.value })} />
            </Field>
            {editGoal.goal_type === "SPECIFIC" ? (
              <div className="span-2 goal-type-picker">
                <span>哪些资产算进这个目标？</span>
                <div>
                  {specificTypes.map(([value, label]) => (
                    <label key={value}>
                      <input
                        type="checkbox"
                        checked={editGoal.included_asset_types.includes(value)}
                        onChange={(e) => setEditGoal({
                          ...editGoal,
                          included_asset_types: e.target.checked
                            ? [...editGoal.included_asset_types, value]
                            : editGoal.included_asset_types.filter((item) => item !== value),
                        })}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
          <div className="form-actions">
            <Button variant="ghost" type="button" onClick={() => setEditOpen(false)}>先不改</Button>
            <Button loading={saving}>{editMode === "UPGRADE" ? <Sparkles /> : <Pencil />} {editMode === "UPGRADE" ? "保存升级" : "保存修改"}</Button>
          </div>
        </form>
      </Modal>

      <Modal open={planEditOpen} onClose={() => setPlanEditOpen(false)} title="编辑智能计划">
        <form onSubmit={savePlan} className="plan-editor">
          <div className="form-grid">
            <Field label="每月固定收入（元）">
              <input inputMode="decimal" value={planDraft.monthly_income_cny} onChange={(e) => setPlanDraft({ ...planDraft, monthly_income_cny: e.target.value })} required />
            </Field>
            <Field label="每月固定支出（元）">
              <input inputMode="decimal" value={planDraft.monthly_fixed_expenses_cny} onChange={(e) => setPlanDraft({ ...planDraft, monthly_fixed_expenses_cny: e.target.value })} required />
            </Field>
            <Field label="每月保留机动金（元）">
              <input inputMode="decimal" value={planDraft.monthly_safety_buffer_cny} onChange={(e) => setPlanDraft({ ...planDraft, monthly_safety_buffer_cny: e.target.value })} />
            </Field>
            <Field label="每月投入目标（元）" hint="不能超过扣除支出和机动金后的可用额。">
              <input inputMode="decimal" value={planDraft.suggested_monthly_contribution_cny} onChange={(e) => setPlanDraft({ ...planDraft, suggested_monthly_contribution_cny: e.target.value })} required />
            </Field>
            <Field label="计划结论" className="span-2">
              <textarea value={planDraft.executive_summary} onChange={(e) => setPlanDraft({ ...planDraft, executive_summary: e.target.value })} rows={3} />
            </Field>
            <Field label="分析要点" hint="每行一条，可直接改写、增删。" className="span-2">
              <textarea value={planDraft.analysis} onChange={(e) => setPlanDraft({ ...planDraft, analysis: e.target.value })} rows={5} />
            </Field>
          </div>
          <div className="plan-rec-editor">
            <div className="plan-rec-editor-head">
              <strong>执行步骤</strong>
              <Button
                variant="ghost"
                type="button"
                onClick={() => setPlanDraft({
                  ...planDraft,
                  recommendations: [...planDraft.recommendations, { priority: "MEDIUM", action: "", reason: "", expected_impact: "", risk: "", review_trigger: "" }],
                })}
              ><Plus /> 添加一步</Button>
            </div>
            {planDraft.recommendations.map((item, index) => (
              <Card className="plan-rec-edit-card" key={index}>
                <div className="plan-rec-edit-top">
                  <strong>第 {index + 1} 步</strong>
                  <button type="button" className="icon-button danger-text" onClick={() => setPlanDraft({ ...planDraft, recommendations: planDraft.recommendations.filter((_, i) => i !== index) })}><Trash2 /></button>
                </div>
                <div className="form-grid">
                  <Field label="优先级">
                    <select value={item.priority} onChange={(e) => updatePlanRecommendation(index, "priority", e.target.value)}>
                      <option value="HIGH">优先处理</option><option value="MEDIUM">随后处理</option><option value="LOW">可选优化</option>
                    </select>
                  </Field>
                  <Field label="行动">
                    <input value={item.action} onChange={(e) => updatePlanRecommendation(index, "action", e.target.value)} required />
                  </Field>
                  <Field label="为什么这样做" className="span-2">
                    <textarea value={item.reason} onChange={(e) => updatePlanRecommendation(index, "reason", e.target.value)} />
                  </Field>
                  <Field label="预期影响">
                    <input value={item.expected_impact} onChange={(e) => updatePlanRecommendation(index, "expected_impact", e.target.value)} />
                  </Field>
                  <Field label="需要留意">
                    <input value={item.risk} onChange={(e) => updatePlanRecommendation(index, "risk", e.target.value)} />
                  </Field>
                  <Field label="什么时候复盘" className="span-2">
                    <input value={item.review_trigger} onChange={(e) => updatePlanRecommendation(index, "review_trigger", e.target.value)} />
                  </Field>
                </div>
              </Card>
            ))}
          </div>
          <div className="form-actions">
            <Button variant="ghost" type="button" onClick={() => setPlanEditOpen(false)}>先不改</Button>
            <Button loading={saving}><Pencil /> 保存计划</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}

const celebrationColors = ["#7d38ce", "#f4c95d", "#f07aa8", "#6fd6c5", "#ffffff"];

function GoalCelebration({
  goal,
  ready,
  onKeep,
  onUpgrade,
  onDelete,
}: {
  goal: FinancialGoal;
  ready: boolean;
  onKeep: () => void;
  onUpgrade: () => void;
  onDelete: () => void | Promise<void>;
}) {
  const pieces = Array.from({ length: 56 }, (_, index) => ({
    left: (index * 37) % 100,
    delay: (index % 14) * 0.06,
    duration: 1.8 + (index % 7) * 0.14,
    drift: ((index * 29) % 120) - 60,
    rotate: (index * 71) % 360,
    color: celebrationColors[index % celebrationColors.length],
  }));
  return (
    <div className="goal-celebration" role="dialog" aria-modal="true" aria-label={`${goal.name}目标完成庆祝`}>
      <div className="goal-confetti" aria-hidden="true">
        {pieces.map((piece, index) => <i key={index} className={index % 6 === 0 ? "ribbon" : ""} style={{ "--left": `${piece.left}%`, "--delay": `${piece.delay}s`, "--duration": `${piece.duration}s`, "--drift": `${piece.drift}px`, "--rotate": `${piece.rotate}deg`, "--color": piece.color } as React.CSSProperties} />)}
      </div>
      <Card className="goal-celebration-card">
        <div className="goal-celebration-icon"><PartyPopper /></div>
        <Badge tone="purple">目标达成</Badge>
        <h2>恭喜你，{goal.name}完成啦！</h2>
        <p>你已经为这个目标准备了 {money(goal.current_cny)}，这一步值得被认真记住。</p>
        <div className={`goal-celebration-actions ${ready ? "ready" : ""}`}>
          <span>接下来想怎样安排这个目标？</span>
          <div>
            <Button onClick={onKeep}><CircleCheck /> 保留目标</Button>
            <Button variant="secondary" onClick={onUpgrade}><Sparkles /> 升级目标</Button>
            <Button variant="danger" onClick={onDelete}><Trash2 /> 删除目标</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function SavedPlan({ plan, onEdit }: { plan: GoalPlan; onEdit: () => void }) {
  const calculation = plan.calculation;
  return (
    <Card className="card-pad saved-goal-plan">
      <div className="saved-plan-head">
        <div className="card-title-row">
          <div className="card-icon"><PiggyBank /></div>
          <div>
            <h2>你的智能计划</h2>
            <p>怀特已经把这份计划收在目标里，下次回来还能继续看。</p>
          </div>
        </div>
        <div className="saved-plan-actions">
          <Badge tone="purple">{plan.provider} · {plan.model}</Badge>
          <Button variant="ghost" onClick={onEdit}><Pencil /> 编辑计划</Button>
        </div>
      </div>
      <div className="plan-numbers">
        <div>
          <span>每月建议存入</span>
          <strong>{money(calculation.suggested_monthly_contribution_cny)}</strong>
        </div>
        <div>
          <span>扣除机动金后可安排</span>
          <strong>{money(calculation.monthly_available_after_buffer_cny)}</strong>
        </div>
        <div>
          <span>预计需要</span>
          <strong>{calculation.estimated_months ? `${calculation.estimated_months} 个月` : "已经完成"}</strong>
        </div>
      </div>
      <p className="plan-note"><CircleCheck /> {calculation.calculation_note}</p>
      {plan.guidance.executive_summary ? (
        <div className="plan-executive-summary">
          <Sparkles />
          <strong>{plan.guidance.executive_summary}</strong>
        </div>
      ) : null}
      <div className="plan-guidance-grid">
        <section>
          <h3>怀特怎么看</h3>
          <ul>{(plan.guidance.analysis || []).map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
        <section>
          <h3>每月可以这样做</h3>
          <div className="plan-actions">
            {(plan.guidance.recommendations || []).map((item) => (
              <div key={`${item.action}-${item.reason}`}>
                <CircleCheck />
                <div>
                  <strong>{item.action}</strong>
                  <p>{item.reason}</p>
                  {item.expected_impact ? <small>预期影响：{item.expected_impact}</small> : null}
                  {item.risk ? <small>留意：{item.risk}</small> : null}
                  {item.review_trigger ? <small>复盘：{item.review_trigger}</small> : null}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
      <div className="saved-plan-foot">
        <CalendarDays /> 最近更新于 {formatDate(plan.updated_at)}
      </div>
    </Card>
  );
}

export default function GoalsPage() {
  return (
    <Protected>
      <GoalsContent />
    </Protected>
  );
}
