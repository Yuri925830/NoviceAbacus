"use client";
import { Protected } from "@/components/app-shell";
import { PrivacyCanvas } from "@/components/privacy-canvas";
import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Modal,
  Skeleton,
} from "@/components/ui";
import { api, ApiError, errorMessage, money } from "@/lib/api";
import type { AssetItem, ClearingSession } from "@/lib/types";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleDollarSign,
  FileCheck2,
  HandCoins,
  Plus,
  Pencil,
  ScanLine,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";

const assetTypes = [
  ["CASH", "现金与活期存款"],
  ["FIXED_DEPOSIT", "定期存款"],
  ["STOCK", "股票"],
  ["FUND", "基金"],
  ["GOLD", "黄金"],
  ["PHYSICAL_GOLD", "实物黄金（按克重估值）"],
  ["PENSION", "公积金 / 养老金"],
  ["PROPERTY", "房产"],
  ["VEHICLE", "车辆"],
  ["LOAN_RECEIVABLE", "借出款 / 应收款"],
  ["LIABILITY", "负债"],
  ["OTHER", "其他"],
] as const;

const assetTypeLabels = Object.fromEntries(assetTypes) as Record<string, string>;
const liquidityLabels: Record<string, string> = {
  HIGH: "随时可用",
  MEDIUM: "需要一点时间变现",
  LOW: "不容易马上变现",
  RESTRICTED: "暂时受限",
};

const initial = {
  name: "",
  account_alias: "",
  asset_type: "CASH",
  category: "CASH",
  original_currency: "CNY",
  original_value: "",
  quantity: "",
  current_market_value: "",
  cost_basis: "",
  unrealized_pl: "",
  liquidity_level: "HIGH",
  is_liability: false,
  notes: "",
};

function cleanDecimal(value: string): string {
  return value.trim().replace(/[,，\s]/g, "");
}
type GoldSpot = {
  symbol: string;
  usd_per_troy_ounce: string;
  usd_cny: string;
  cny_per_gram: string;
  quoted_at: string;
  source: string;
  status: string;
  note: string;
};
function ClearingContent() {
  const [session, setSession] = useState<ClearingSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [recognizing, setRecognizing] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<AssetItem | null>(null);
  const [form, setForm] = useState({ ...initial });
  const [editForm, setEditForm] = useState({ ...initial });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [savingItem, setSavingItem] = useState(false);
  const [stale, setStale] = useState(false);
  const [goldSpot, setGoldSpot] = useState<GoldSpot | null>(null);
  const [goldLoading, setGoldLoading] = useState(false);
  const [recognitionState, setRecognitionState] = useState<
    "idle" | "reading" | "done" | "empty" | "error"
  >("idle");
  const refresh = () =>
    session
      ? api<ClearingSession>(`/sessions/${session.id}`).then(setSession)
      : Promise.resolve();
  useEffect(() => {
    api<ClearingSession>("/sessions", {
      method: "POST",
      body: JSON.stringify({ kind: "AD_HOC" }),
    })
      .then(setSession)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  }, []);
  const counts = useMemo(() => {
    const items = session?.items || [];
    return {
      all: items.length,
      confirmed: items.filter((x) => x.status === "CONFIRMED").length,
      review: items.filter((x) =>
        ["EXTRACTED", "NEEDS_REVIEW"].includes(x.status),
      ).length,
      excluded: items.filter((x) => x.status === "EXCLUDED").length,
    };
  }, [session]);
  async function recognize(blob: Blob, name: string) {
    if (!session) return false;
    setRecognizing(true);
    setRecognitionState("reading");
    setMessage("");
    setError("");
    const fd = new FormData();
    fd.append("file", blob, name);
    fd.append("privacy_confirmed", "true");
    try {
      const result = await api<{
        items: AssetItem[];
        warnings: string[];
        message: string;
        status: "RECOGNIZED" | "NO_ITEMS";
      }>(
        `/sessions/${session.id}/recognize`,
        { method: "POST", body: fd },
      );
      await refresh();
      if (result.items.length) {
        setRecognitionState("done");
        setMessage(
          `看完啦，找到了 ${result.items.length} 个项目，已经放到下面。你花一点时间看看金额和币种就好。`,
        );
        window.setTimeout(
          () => document.getElementById("clearing-review")?.scrollIntoView({ behavior: "smooth" }),
          120,
        );
      } else {
        setRecognitionState("empty");
        setMessage(
          "图片已经看完了，这次没有找到清楚的资产金额。换一张更清晰的图，或者手工记下来都可以。",
        );
      }
      return true;
    } catch (e) {
      setRecognitionState("error");
      setError(errorMessage(e));
      return false;
    } finally {
      setRecognizing(false);
    }
  }
  async function addManual(e: FormEvent) {
    e.preventDefault();
    if (!session) return;
    setError("");
    try {
      await api(`/sessions/${session.id}/items`, {
        method: "POST",
        body: JSON.stringify({
          ...form,
          original_value: form.asset_type === "PHYSICAL_GOLD" ? "0" : cleanDecimal(form.original_value),
          quantity: form.asset_type === "PHYSICAL_GOLD" ? cleanDecimal(form.quantity) : null,
          current_market_value: cleanDecimal(form.current_market_value) || null,
          cost_basis: cleanDecimal(form.cost_basis) || null,
          unrealized_pl: cleanDecimal(form.unrealized_pl) || null,
          source: "MANUAL",
          status: "CONFIRMED",
        }),
      });
      setManualOpen(false);
      setForm({ ...initial });
      await refresh();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function loadGoldSpot() {
    setGoldLoading(true);
    setError("");
    try {
      setGoldSpot(await api<GoldSpot>("/gold/spot"));
    } catch (e) {
      setGoldSpot(null);
      setError(errorMessage(e));
    } finally {
      setGoldLoading(false);
    }
  }
  async function setStatus(item: AssetItem, status: string) {
    if (!session) return;
    await api(`/sessions/${session.id}/items/${item.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
    await refresh();
  }
  function beginEdit(item: AssetItem) {
    setEditingItem(item);
    setEditForm({
      name: item.name || "",
      account_alias: item.account_alias || "",
      asset_type: item.asset_type || "OTHER",
      category: item.category || categoryFor(item.asset_type),
      original_currency: item.original_currency || "CNY",
      original_value: item.original_value || "",
      quantity: item.quantity || "",
      current_market_value: item.current_market_value || "",
      cost_basis: item.cost_basis || "",
      unrealized_pl: item.unrealized_pl || "",
      liquidity_level: item.liquidity_level || "HIGH",
      is_liability: item.is_liability,
      notes: item.notes || "",
    });
  }
  async function saveEdited(e?: FormEvent, confirmAfter = false) {
    e?.preventDefault();
    if (!session || !editingItem) return;
    setSavingItem(true);
    setError("");
    try {
      await api(`/sessions/${session.id}/items/${editingItem.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          ...editForm,
          original_value: editForm.asset_type === "PHYSICAL_GOLD" ? "0" : cleanDecimal(editForm.original_value),
          quantity: editForm.asset_type === "PHYSICAL_GOLD" ? cleanDecimal(editForm.quantity) : null,
          current_market_value: cleanDecimal(editForm.current_market_value) || null,
          cost_basis: cleanDecimal(editForm.cost_basis) || null,
          unrealized_pl: cleanDecimal(editForm.unrealized_pl) || null,
          status: confirmAfter ? "CONFIRMED" : editingItem.status,
        }),
      });
      setEditingItem(null);
      setMessage(confirmAfter ? "修改已经保存，这一项也确认好了。" : "修改已经保存，数字会按你刚刚核对的内容使用。 ");
      await refresh();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSavingItem(false);
    }
  }
  async function remove(item: AssetItem) {
    if (!session || !confirm("确定删除这个候选项？")) return;
    await api(`/sessions/${session.id}/items/${item.id}`, { method: "DELETE" });
    await refresh();
  }
  async function confirmSession(acceptStale = false) {
    if (!session) return;
    setConfirming(true);
    setError("");
    try {
      const result = await api<ClearingSession>(
        `/sessions/${session.id}/confirm`,
        {
          method: "POST",
          body: JSON.stringify({
            accept_stale_rates: acceptStale,
            idempotency_key: crypto.randomUUID(),
          }),
        },
      );
      setSession(result);
      setMessage("这次清算已经收好啦。新的资产快照和趋势也一起更新好了。");
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        typeof e.detail === "object" &&
        e.detail &&
        "code" in e.detail &&
        (e.detail as { code: string }).code === "STALE_RATES"
      )
        setStale(true);
      setError(errorMessage(e));
    } finally {
      setConfirming(false);
    }
  }
  if (loading)
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">CLEARING WORKFLOW</div>
            <h1>资产清算</h1>
          </div>
        </div>
        <Skeleton height={420} />
      </>
    );
  if (!session)
    return (
      <Card className="card-pad">
        <Empty title="无法创建清算" body={error || "请检查服务状态"} />
      </Card>
    );
  if (["CONFIRMED", "REVISED"].includes(session.status))
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">CLEARING COMPLETE</div>
            <h1>这次资产底牌已确认</h1>
            <p>你刚刚核对过的项目，已经汇成一张新的资产快照。</p>
          </div>
        </div>
        <Card className="clearing-success">
          <div className="success-orbit">
            <CheckCircle2 />
          </div>
          <Badge tone="purple">修订版本 {session.revision_number}</Badge>
          <h2>{money(session.totals?.net_worth_cny)}</h2>
          <span>当前净资产</span>
          <div className="success-metrics">
            <div>
              <strong>{money(session.totals?.assets_cny)}</strong>
              <span>总资产</span>
            </div>
            <div>
              <strong>{money(session.totals?.liabilities_cny)}</strong>
              <span>总负债</span>
            </div>
            <div>
              <strong>{money(session.totals?.liquid_assets_cny)}</strong>
              <span>可立即使用</span>
            </div>
          </div>
          <div className="form-actions">
            <a href="/dashboard">
              <Button>回到驾驶舱</Button>
            </a>
            <a href="/trend">
              <Button variant="secondary">查看资产 K 线</Button>
            </a>
          </div>
        </Card>
      </>
    );
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">ASSET CHECK-IN · {session.kind}</div>
          <h1>资产清算</h1>
          <p>{session.items?.some((item) => item.source === "CARRY_FORWARD") ? "上次确认的资产已经带过来了。直接修改变化的项目，再补上新增或删掉不再持有的项目就好。" : "可以上传截图让怀特帮你读，也可以直接手工添加，按你觉得轻松的方式来。"}</p>
        </div>
        <div className="page-actions">
          <Button variant="secondary" onClick={() => setManualOpen(true)}>
            <Plus size={17} />
            手工添加
          </Button>
        </div>
      </div>
      <div className="clearing-steps">
        <div className="active">
          <b>1</b>
          <span>
            <strong>输入</strong>
            <small>遮挡截图或手工录入</small>
          </span>
        </div>
        <i />
        <div className={counts.review || counts.confirmed ? "active" : ""}>
          <b>2</b>
          <span>
            <strong>核对</strong>
            <small>金额、币种、重复项</small>
          </span>
        </div>
        <i />
        <div className={counts.confirmed ? "active" : ""}>
          <b>3</b>
          <span>
            <strong>确认</strong>
            <small>汇率快照与入账</small>
          </span>
        </div>
      </div>
      {message ? (
        <div className="inline-message">
          <Sparkles />
          <span>{message}</span>
          <button onClick={() => setMessage("")}>
            <X />
          </button>
        </div>
      ) : null}
      {error ? (
        <div className="inline-error">
          <AlertTriangle />
          <span>{error}</span>
          {stale ? (
            <Button variant="secondary" onClick={() => confirmSession(true)}>
              我已核对，使用最近有效汇率
            </Button>
          ) : null}
        </div>
      ) : null}
      <div className="section-grid clearing-grid">
        <Card className="card-pad col-7">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <ShieldCheck size={18} />
              </div>
              <div>
                <h2>上传前先看一眼</h2>
                <p>把姓名、完整账号等敏感信息轻轻遮住，再交给怀特读取。</p>
              </div>
            </div>
            <Badge tone="purple">先遮挡再识别</Badge>
          </div>
          <div className="privacy-reminder">
            <AlertTriangle />
            <div>
              <strong>藏好身份信息，金额和资产名称可以留下</strong>
              <span>
                建议保留资产名称、币种、余额、市值、成本、浮盈、到期日和利率。
              </span>
            </div>
          </div>
          <PrivacyCanvas onSubmit={recognize} loading={recognizing} />
          {recognitionState !== "idle" ? (
            <div className={`recognition-feedback ${recognitionState}`} aria-live="polite">
              <Sparkles />
              <div>
                <strong>
                  {recognitionState === "reading"
                    ? "怀特正在认真读这张图…"
                    : recognitionState === "done"
                      ? "已经读好啦"
                      : recognitionState === "empty"
                        ? "这张图有点难认"
                        : "刚才没有读成功"}
                </strong>
                <span>
                  {recognitionState === "reading"
                    ? "通常只要几十秒，这个页面会自动显示结果。"
                    : recognitionState === "done"
                      ? "识别到的项目就在下方，等你核对。"
                      : recognitionState === "empty"
                        ? "换一张更清晰的截图，或者手工添加都没关系。"
                        : "可以直接再试一次；如果仍有问题，页面会告诉你原因。"}
                </span>
              </div>
            </div>
          ) : null}
        </Card>
        <Card className="card-pad col-5">
          <div className="card-head">
            <div>
              <h2>本次进度</h2>
              <p>每确认一项，这里的进度就会向前一点。</p>
            </div>
          </div>
          <div className="progress-ring-wrap">
            <div
              className="progress-ring"
              style={
                {
                  "--progress": `${counts.all ? (counts.confirmed / counts.all) * 360 : 0}deg`,
                } as React.CSSProperties
              }
            >
              <div>
                <strong>{counts.confirmed}</strong>
                <span>/ {counts.all} 已确认</span>
              </div>
            </div>
          </div>
          <div className="count-list">
            <div>
              <span>待核对</span>
              <Badge tone={counts.review ? "warning" : "neutral"}>
                {counts.review}
              </Badge>
            </div>
            <div>
              <span>已确认</span>
              <Badge tone="purple">{counts.confirmed}</Badge>
            </div>
            <div>
              <span>已排除</span>
              <Badge>{counts.excluded}</Badge>
            </div>
          </div>
          <Button
            className="full-button"
            disabled={!counts.confirmed || counts.review > 0}
            loading={confirming}
            onClick={() => confirmSession(false)}
          >
            <FileCheck2 />
            确认本次清算
          </Button>
          {counts.review > 0 ? (
            <p className="confirm-hint">
              还有 {counts.review} 个识别候选未核对。请确认或排除后继续。
            </p>
          ) : null}
        </Card>
        <Card className="card-pad col-12 review-card" id="clearing-review">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <ScanLine size={18} />
              </div>
              <div>
                <h2>识别与手工项目</h2>
                <p>怀特先帮你读一遍，你只需要看看金额、币种和类型有没有偏差。</p>
              </div>
            </div>
            <Button variant="ghost" onClick={() => setManualOpen(true)}>
              <Plus />
              添加项目
            </Button>
          </div>
          {session.items?.length ? (
            <div className="item-table">
              <div className="item-table-head">
                <span>项目</span>
                <span>原币金额</span>
                <span>类型 / 流动性</span>
                <span>状态</span>
                <span>操作</span>
              </div>
              {session.items.map((item) => (
                <div
                  className={`item-row item-${item.status.toLowerCase()}`}
                  key={item.id}
                >
                  <div>
                    <div className="item-source">
                      {item.source === "SCREENSHOT" ? (
                        <ScanLine />
                      ) : (
                        <HandCoins />
                      )}
                      <span>
                        {item.source === "SCREENSHOT" ? "截图识别" : item.source === "CARRY_FORWARD" ? "沿用上次清算" : "手工录入"}
                      </span>
                      {item.confidence ? (
                        <em>
                          置信度 {(Number(item.confidence) * 100).toFixed(0)}%
                        </em>
                      ) : null}
                    </div>
                    <strong>{item.name}</strong>
                    <small>{item.account_alias || "未设置账户别名"}</small>
                  </div>
                  <div>
                    <strong className="mono">
                      {item.asset_type === "PHYSICAL_GOLD" ? `${Number(item.quantity || 0).toLocaleString()} 克` : Number(item.original_value).toLocaleString()}
                    </strong>
                    <small>{item.asset_type === "PHYSICAL_GOLD" ? `估值 ${Number(item.original_value).toLocaleString()} CNY` : item.original_currency}</small>
                  </div>
                  <div>
                    <Badge tone="info">{assetTypeLabels[item.asset_type] || item.asset_type}</Badge>
                    <small>{liquidityLabels[item.liquidity_level] || item.liquidity_level}</small>
                  </div>
                  <div>
                    <Badge
                      tone={
                        item.status === "CONFIRMED"
                          ? "purple"
                          : item.status === "EXCLUDED"
                            ? "neutral"
                            : "warning"
                      }
                    >
                      {statusLabel(item.status)}
                    </Badge>
                  </div>
                  <div className="row-actions">
                    {item.status !== "EXCLUDED" ? (
                      <Button variant="ghost" onClick={() => beginEdit(item)}>
                        <Pencil />
                        编辑
                      </Button>
                    ) : null}
                    {["EXTRACTED", "NEEDS_REVIEW"].includes(item.status) ? (
                      <>
                        <Button
                          variant="secondary"
                          onClick={() => setStatus(item, "CONFIRMED")}
                        >
                          <Check />
                          确认
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() => setStatus(item, "EXCLUDED")}
                        >
                          排除
                        </Button>
                      </>
                    ) : item.status === "EXCLUDED" ? (
                      <Button
                        variant="ghost"
                        onClick={() => setStatus(item, "CONFIRMED")}
                      >
                        恢复
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        onClick={() => setStatus(item, "EXCLUDED")}
                      >
                        排除
                      </Button>
                    )}
                    <button
                      className="icon-button danger-text"
                      onClick={() => remove(item)}
                    >
                      <Trash2 />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="还没有资产项目"
              body="从一张资产截图开始，或者先手工记下一项。哪一种顺手，就用哪一种。"
              action={
                <Button variant="secondary" onClick={() => setManualOpen(true)}>
                  手工添加
                </Button>
              }
            />
          )}
        </Card>
      </div>
      <Modal
        open={manualOpen}
        onClose={() => setManualOpen(false)}
        title="手工添加资产或负债"
      >
        <form onSubmit={addManual}>
          <div className="form-grid">
            <Field label="名称">
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="例如：韩国活期"
                required
              />
            </Field>
            <Field label="账户别名">
              <input
                value={form.account_alias}
                onChange={(e) =>
                  setForm({ ...form, account_alias: e.target.value })
                }
                placeholder="可选，不填真实账号"
              />
            </Field>
            <Field label="资产类型">
              <select
                value={form.asset_type}
                onChange={(e) =>
                  {
                    const value = e.target.value;
                    setForm({
                    ...form,
                    asset_type: value,
                    category: categoryFor(value),
                    is_liability: value === "LIABILITY",
                  });
                    if (value === "PHYSICAL_GOLD") loadGoldSpot();
                  }
                }
              >
                {assetTypes.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            {form.asset_type !== "PHYSICAL_GOLD" ? <Field label="币种">
              <select
                value={form.original_currency}
                onChange={(e) =>
                  setForm({ ...form, original_currency: e.target.value })
                }
              >
                {[
                  "CNY",
                  "KRW",
                  "USD",
                  "HKD",
                  "JPY",
                  "EUR",
                  "GBP",
                  "SGD",
                  "AUD",
                  "CAD",
                ].map((x) => (
                  <option key={x}>{x}</option>
                ))}
              </select>
            </Field> : null}
            {form.asset_type === "PHYSICAL_GOLD" ? (
              <>
                <Field label="实物黄金克重">
                  <input inputMode="decimal" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} placeholder="例如 25.8" required />
                </Field>
                <div className="gold-live-quote">
                  <div><Sparkles /><span>实时国际金价</span></div>
                  {goldLoading ? <strong>正在读取…</strong> : goldSpot ? <><strong>{money(goldSpot.cny_per_gram)} / 克</strong><small>XAU/USD {Number(goldSpot.usd_per_troy_ounce).toLocaleString()} · {new Date(goldSpot.quoted_at).toLocaleString("zh-CN")}</small><b>当前估值约 {money(Number(form.quantity || 0) * Number(goldSpot.cny_per_gram))}</b></> : <Button type="button" variant="ghost" onClick={loadGoldSpot}>刷新实时金价</Button>}
                </div>
              </>
            ) : <Field
              label={
                form.asset_type === "STOCK" || form.asset_type === "FUND"
                  ? "当前市值"
                  : "当前金额 / 本金"
              }
            >
              <input
                inputMode="decimal"
                value={form.original_value}
                onChange={(e) =>
                  setForm({ ...form, original_value: e.target.value })
                }
                placeholder="0.00"
                required
              />
            </Field>}
            <Field label="流动性">
              <select
                value={form.liquidity_level}
                onChange={(e) =>
                  setForm({ ...form, liquidity_level: e.target.value })
                }
              >
                <option value="HIGH">随时可用</option>
                <option value="MEDIUM">需要一点时间变现</option>
                <option value="LOW">不容易马上变现</option>
                <option value="RESTRICTED">暂时受限</option>
              </select>
            </Field>
            {["STOCK", "FUND"].includes(form.asset_type) ? (
              <>
                <Field label="成本（可选）">
                  <input
                    inputMode="decimal"
                    value={form.cost_basis}
                    onChange={(e) =>
                      setForm({ ...form, cost_basis: e.target.value })
                    }
                  />
                </Field>
                <Field label="浮盈浮亏（仅展示）">
                  <input
                    inputMode="decimal"
                    value={form.unrealized_pl}
                    onChange={(e) =>
                      setForm({ ...form, unrealized_pl: e.target.value })
                    }
                  />
                </Field>
              </>
            ) : null}
            <Field label="备注" hint="不要填写完整账号、证件号或密码">
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Field>
          </div>
          <div className="form-actions">
            <Button
              variant="ghost"
              type="button"
              onClick={() => setManualOpen(false)}
            >
              取消
            </Button>
            <Button type="submit">
              <CircleDollarSign />
              加入本次清算
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={Boolean(editingItem)}
        onClose={() => setEditingItem(null)}
        title="核对并修改识别结果"
      >
        <form onSubmit={(e) => saveEdited(e, false)}>
          <p className="modal-warm-note">识别偶尔会看错一个数字或类型，按截图里的真实内容改好就行。</p>
          {error ? <div className="inline-error"><AlertTriangle />{error}</div> : null}
          <div className="form-grid">
            <Field label="名称">
              <input value={editForm.name} onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} required />
            </Field>
            <Field label="账户别名">
              <input value={editForm.account_alias} onChange={(e) => setEditForm({ ...editForm, account_alias: e.target.value })} placeholder="可选，不填真实账号" />
            </Field>
            <Field label="资产类型">
              <select
                value={editForm.asset_type}
                onChange={(e) => {
                  const value = e.target.value;
                  setEditForm({
                    ...editForm,
                    asset_type: value,
                    category: categoryFor(value),
                    is_liability: value === "LIABILITY",
                  });
                  if (value === "PHYSICAL_GOLD") loadGoldSpot();
                }}
              >
                {assetTypes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
            {editForm.asset_type !== "PHYSICAL_GOLD" ? <Field label="币种">
              <select value={editForm.original_currency} onChange={(e) => setEditForm({ ...editForm, original_currency: e.target.value })}>
                {["CNY", "KRW", "USD", "HKD", "JPY", "EUR", "GBP", "SGD", "AUD", "CAD"].map((item) => <option key={item}>{item}</option>)}
              </select>
            </Field> : null}
            {editForm.asset_type === "PHYSICAL_GOLD" ? (
              <>
                <Field label="实物黄金克重">
                  <input inputMode="decimal" value={editForm.quantity} onChange={(e) => setEditForm({ ...editForm, quantity: e.target.value })} required />
                </Field>
                <div className="gold-live-quote">
                  <div><Sparkles /><span>实时国际金价</span></div>
                  {goldLoading ? <strong>正在读取…</strong> : goldSpot ? <><strong>{money(goldSpot.cny_per_gram)} / 克</strong><small>{new Date(goldSpot.quoted_at).toLocaleString("zh-CN")} 更新</small><b>保存后估值约 {money(Number(editForm.quantity || 0) * Number(goldSpot.cny_per_gram))}</b></> : <Button type="button" variant="ghost" onClick={loadGoldSpot}>刷新实时金价</Button>}
                </div>
              </>
            ) : <Field label="识别出的金额">
              <input inputMode="decimal" value={editForm.original_value} onChange={(e) => setEditForm({ ...editForm, original_value: e.target.value })} required />
            </Field>}
            <Field label="流动性">
              <select value={editForm.liquidity_level} onChange={(e) => setEditForm({ ...editForm, liquidity_level: e.target.value })}>
                <option value="HIGH">随时可用</option>
                <option value="MEDIUM">需要一点时间变现</option>
                <option value="LOW">不容易马上变现</option>
                <option value="RESTRICTED">暂时受限</option>
              </select>
            </Field>
            {["STOCK", "FUND"].includes(editForm.asset_type) ? (
              <>
                <Field label="成本（可选）">
                  <input inputMode="decimal" value={editForm.cost_basis} onChange={(e) => setEditForm({ ...editForm, cost_basis: e.target.value })} />
                </Field>
                <Field label="浮盈浮亏（可选）">
                  <input inputMode="decimal" value={editForm.unrealized_pl} onChange={(e) => setEditForm({ ...editForm, unrealized_pl: e.target.value })} />
                </Field>
              </>
            ) : null}
            <Field label="备注" className="span-2">
              <textarea value={editForm.notes} onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} />
            </Field>
          </div>
          <div className="form-actions">
            <Button variant="ghost" type="button" onClick={() => setEditingItem(null)}>先不改</Button>
            <Button variant="secondary" type="submit" loading={savingItem}><Pencil /> 只保存修改</Button>
            <Button type="button" loading={savingItem} onClick={() => saveEdited(undefined, true)}><Check /> 保存并确认</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
function statusLabel(s: string) {
  return (
    (
      {
        EXTRACTED: "待核对",
        NEEDS_REVIEW: "需重点核对",
        CONFIRMED: "已确认",
        EXCLUDED: "已排除",
      } as Record<string, string>
    )[s] || s
  );
}
function categoryFor(type: string) {
  if (type === "LIABILITY") return "LIABILITY";
  if (["STOCK", "FUND"].includes(type)) return "INVESTMENT";
  if (type === "GOLD") return "GOLD";
  if (type === "PENSION") return "RESTRICTED";
  if (["PROPERTY", "VEHICLE"].includes(type)) return "PHYSICAL";
  return "CASH";
}
export default function ClearingPage() {
  return (
    <Protected>
      <ClearingContent />
    </Protected>
  );
}
