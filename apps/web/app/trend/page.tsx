"use client";
import { Protected } from "@/components/app-shell";
import { usePrivacy } from "@/components/providers";
import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Modal,
  Skeleton,
} from "@/components/ui";
import { api, errorMessage, formatDate, money } from "@/lib/api";
import { actionItemPayload, type AgentRecommendation, type AgentReply } from "@/lib/agent";
import {
  Activity,
  BookmarkCheck,
  BrainCircuit,
  CalendarPlus,
  ChartCandlestick,
  CircleAlert,
  LineChart,
  Minus,
  Plus,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Point = {
  session_id: string;
  time: string;
  value: string;
  completeness: string;
  low_completeness: boolean;
};
type Candle = {
  bucket: string;
  open: string;
  high: string;
  low: string;
  close: string;
  change: string;
  sample_count: number;
  single_point: boolean;
};
type Trend = {
  metric: string;
  granularity: string;
  points: Point[];
  candles: Candle[];
  analysis: {
    data_level: string;
    point_count: number;
    span_days?: number;
    total_change_cny?: string;
    change_rate_pct?: string | null;
    max_drawdown_pct?: string;
    volatility_pct?: string | null;
    slope_per_clearing_cny?: string;
    limitations: string[];
  };
  annotations: Array<{
    id: string;
    event_at: string;
    event_type: string;
    label: string;
    notes?: string;
  }>;
  disclaimer: string;
};
type Attribution = {
  available: boolean;
  session_id: string;
  total_change_cny: string;
  liquid_change_cny?: string;
  narrative?: string;
  calculation_note?: string;
  breakdown: Array<{ code: string; label: string; value_cny: string }>;
  questions: Array<{ id: string; type: string; question: string; options?: Array<{ value: string; label: string }>; suggested_value?: string }>;
  answers: Array<{ question_id: string; value: string | boolean }>;
  reason?: string;
};
function chartScale(values: number[]) {
  const min = Math.min(...values),
    max = Math.max(...values);
  const pad = (max - min || Math.abs(max) || 1) * 0.12;
  return {
    min: min - pad,
    max: max + pad,
    y: (v: number) => 250 - ((v - (min - pad)) / (max - min + 2 * pad)) * 210,
  };
}
function TrendLine({ points, hidden }: { points: Point[]; hidden: boolean }) {
  const values = points.map((p) => Number(p.value));
  if (!values.length) return null;
  const s = chartScale(values);
  const coords = values.map((v, i) => ({
    x: 35 + (i / Math.max(values.length - 1, 1)) * 690,
    y: s.y(v),
  }));
  const path = coords.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join(" ");
  const area = `${path} L${coords.at(-1)!.x},270 L${coords[0].x},270 Z`;
  return (
    <div className="chart-scroll">
      <svg
        className="trend-svg"
        viewBox="0 0 760 300"
        role="img"
        aria-label="资产清算点趋势图"
      >
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="#7c4bc4" stopOpacity=".28" />
            <stop offset="1" stopColor="#7c4bc4" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[60, 112, 164, 216, 268].map((y) => (
          <line key={y} x1="35" x2="725" y1={y} y2={y} stroke="#e8e1ed" />
        ))}
        <path d={area} fill="url(#area)" />
        <path
          d={path}
          fill="none"
          stroke="#7040b5"
          strokeWidth="3"
          strokeLinejoin="round"
        />
        {coords.map((p, i) => (
          <g key={points[i].session_id}>
            <circle
              cx={p.x}
              cy={p.y}
              r={points[i].low_completeness ? 6 : 5}
              fill={points[i].low_completeness ? "#fff" : "#7040b5"}
              stroke="#7040b5"
              strokeWidth="2"
            >
              <title>
                {formatDate(points[i].time)} ·{" "}
                {hidden ? "金额已隐藏" : money(points[i].value)}
              </title>
            </circle>
            {i === 0 || i === coords.length - 1 ? (
              <text
                x={p.x}
                y="292"
                textAnchor={i === 0 ? "start" : "end"}
                className="chart-label"
              >
                {new Date(points[i].time).toLocaleDateString("zh-CN", {
                  month: "short",
                  day: "numeric",
                })}
              </text>
            ) : null}
          </g>
        ))}
      </svg>
    </div>
  );
}
function Candles({ items, hidden }: { items: Candle[]; hidden: boolean }) {
  if (!items.length) return null;
  const values = items.flatMap((x) => [Number(x.high), Number(x.low)]);
  const s = chartScale(values);
  const width = Math.max(760, items.length * 62 + 80);
  return (
    <div className="chart-scroll">
      <svg
        className="trend-svg"
        viewBox={`0 0 ${width} 300`}
        style={{ minWidth: width }}
        role="img"
        aria-label="聚合资产 K 线"
      >
        {[60, 112, 164, 216, 268].map((y) => (
          <line
            key={y}
            x1="35"
            x2={width - 30}
            y1={y}
            y2={y}
            stroke="#e8e1ed"
          />
        ))}
        {items.map((c, i) => {
          const x = 60 + i * 62,
            o = s.y(Number(c.open)),
            close = s.y(Number(c.close)),
            hi = s.y(Number(c.high)),
            lo = s.y(Number(c.low)),
            up = Number(c.close) >= Number(c.open),
            color = up ? "#7040b5" : "#c65370";
          return (
            <g key={c.bucket}>
              <line
                x1={x}
                x2={x}
                y1={hi}
                y2={lo}
                stroke={color}
                strokeWidth="2"
              />
              <rect
                x={x - 8}
                y={Math.min(o, close)}
                width="16"
                height={Math.max(Math.abs(close - o), 2)}
                rx="2"
                fill={c.single_point ? "#fff" : color}
                stroke={color}
                strokeWidth="2"
              >
                <title>
                  {c.bucket} · O {hidden ? "••" : money(c.open)} H{" "}
                  {hidden ? "••" : money(c.high)} L{" "}
                  {hidden ? "••" : money(c.low)} C{" "}
                  {hidden ? "••" : money(c.close)} · {c.sample_count} 个点
                </title>
              </rect>
              <text x={x} y="292" textAnchor="middle" className="chart-label">
                {c.bucket.replace(/^\d{4}-/, "")}
              </text>
              {c.single_point ? (
                <circle cx={x + 12} cy={close} r="2" fill="#9e8daa" />
              ) : null}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
function AttributionWaterfall({ data, hidden }: { data: Attribution; hidden: boolean }) {
  const items = data.breakdown;
  const width = Math.max(760, (items.length + 1) * 128);
  const height = 330;
  const bars = items.reduce<Array<(typeof items)[number] & { value: number; start: number; end: number }>>((result, item) => {
    const value = Number(item.value_cny);
    const start = result.at(-1)?.end || 0;
    result.push({ ...item, value, start, end: start + value });
    return result;
  }, []);
  const allValues = [0, ...bars.flatMap((item) => [item.start, item.end]), Number(data.total_change_cny)];
  const min = Math.min(...allValues, 0);
  const max = Math.max(...allValues, 0);
  const span = max - min || 1;
  const y = (value: number) => 245 - ((value - min) / span) * 180;
  const zeroY = y(0);
  return (
    <div className="waterfall-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="净资产变化归因瀑布图">
        <line x1="34" y1={zeroY} x2={width - 24} y2={zeroY} className="waterfall-zero" />
        {bars.map((item, index) => {
          const x = 56 + index * 128;
          const top = y(Math.max(item.start, item.end));
          const bottom = y(Math.min(item.start, item.end));
          return (
            <g key={`${item.code}-${index}`}>
              {index > 0 ? <line x1={x - 58} y1={y(item.start)} x2={x} y2={y(item.start)} className="waterfall-connector" /> : null}
              <rect x={x} y={top} width="68" height={Math.max(bottom - top, 3)} rx="8" className={item.value >= 0 ? "waterfall-positive" : "waterfall-negative"} />
              <text x={x + 34} y={top - 9} textAnchor="middle" className="waterfall-value">{hidden ? "••••" : `${item.value >= 0 ? "+" : ""}${Math.round(item.value).toLocaleString()}`}</text>
              <foreignObject x={x - 22} y="264" width="112" height="54"><div className="waterfall-label">{item.label}</div></foreignObject>
            </g>
          );
        })}
        {(() => {
          const x = 56 + bars.length * 128;
          const total = Number(data.total_change_cny);
          const top = y(Math.max(total, 0));
          const bottom = y(Math.min(total, 0));
          return <g><rect x={x} y={top} width="74" height={Math.max(bottom - top, 3)} rx="8" className="waterfall-total" /><text x={x + 37} y={top - 9} textAnchor="middle" className="waterfall-value">{hidden ? "••••" : money(total)}</text><foreignObject x={x - 10} y="264" width="96" height="54"><div className="waterfall-label total">本次净变化</div></foreignObject></g>;
        })()}
      </svg>
    </div>
  );
}

function TrendContent() {
  const [metric, setMetric] = useState("net_worth_cny"),
    [granularity, setGranularity] = useState("month"),
    [view, setView] = useState<"line" | "candle">("line");
  const [data, setData] = useState<Trend | null>(null),
    [error, setError] = useState(""),
    [eventOpen, setEventOpen] = useState(false);
  const [insight, setInsight] = useState<AgentReply | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [savedActions, setSavedActions] = useState<number[]>([]);
  const [attribution, setAttribution] = useState<Attribution | null>(null);
  const [attributionSaving, setAttributionSaving] = useState(false);
  const [threeAnswers, setThreeAnswers] = useState({ cause: "", amount: "", remember: false });
  const [event, setEvent] = useState({
    event_at: new Date().toISOString().slice(0, 16),
    event_type: "OTHER",
    label: "",
    notes: "",
  });
  const { hidden } = usePrivacy();
  const load = useCallback(async (signal?: AbortSignal) => {
    setError("");
    try {
      const next = await api<Trend>(`/trend?metric=${metric}&granularity=${view === "line" ? "clearing" : granularity}`, { signal });
      setData(next);
      const latestPoint = next.points[next.points.length - 1];
      if (latestPoint) {
        const result = await api<Attribution>(`/sessions/${latestPoint.session_id}/attribution`, { signal }).catch((e) => {
          if (e instanceof DOMException && e.name === "AbortError") throw e;
          return null;
        });
        setAttribution(result);
        if (result?.answers?.length) {
          setThreeAnswers({
            cause: String(result.answers.find((item) => item.question_id === "cause")?.value || ""),
            amount: String(result.answers.find((item) => item.question_id === "amount")?.value || ""),
            remember: Boolean(result.answers.find((item) => item.question_id === "remember")?.value),
          });
        } else setThreeAnswers({ cause: "", amount: "", remember: false });
      } else {
        setAttribution(null);
        setThreeAnswers({ cause: "", amount: "", remember: false });
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      setError(errorMessage(e));
    }
  }, [granularity, metric, view]);
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  async function addEvent(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api("/trend/annotations", {
        method: "POST",
        body: JSON.stringify({
          ...event,
          event_at: new Date(event.event_at).toISOString(),
        }),
      });
      setEventOpen(false);
      setEvent((current) => ({ ...current, label: "", notes: "" }));
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function interpretTrend() {
    setInsightLoading(true);
    setError("");
    try {
      const result = await api<AgentReply>("/trend/insight", {
        method: "POST",
        body: JSON.stringify({ metric, provider: "auto", depth: "complex" }),
      });
      setInsight(result);
      setSavedActions([]);
      window.setTimeout(() => document.getElementById("trend-agent-insight")?.scrollIntoView({ behavior: "smooth" }), 80);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setInsightLoading(false);
    }
  }
  async function saveInsightAction(item: AgentRecommendation, index: number) {
    try {
      await api("/intelligence/actions", {
        method: "POST",
        body: JSON.stringify(actionItemPayload(item, "TREND")),
      });
      setSavedActions((current) => [...current, index]);
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function saveThreeAnswers(e: FormEvent) {
    e.preventDefault();
    if (!attribution) return;
    setAttributionSaving(true);
    setError("");
    try {
      const answers = [
        { question_id: "cause", value: threeAnswers.cause },
        { question_id: "amount", value: threeAnswers.amount || "0" },
        { question_id: "remember", value: threeAnswers.remember },
      ];
      setAttribution(await api<Attribution>(`/sessions/${attribution.session_id}/attribution`, {
        method: "PATCH",
        body: JSON.stringify({ answers }),
      }));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setAttributionSaving(false);
    }
  }
  if (!data)
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">VERIFIED TIME SERIES</div>
            <h1>资产 K 线</h1>
          </div>
        </div>
        <Skeleton height={430} />
      </>
    );
  const a = data.analysis;
  const direction =
    Number(a.total_change_cny || 0) > 0
      ? "up"
      : Number(a.total_change_cny || 0) < 0
        ? "down"
        : "flat";
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">VERIFIED TIME SERIES</div>
          <h1>资产 K 线与趋势</h1>
          <p>每完成一次清算，这里就多一枚坐标。两个点开始，就能看见变化方向。</p>
        </div>
        <div className="page-actions">
          <Button variant="secondary" onClick={() => setEventOpen(true)}>
            <CalendarPlus />
            添加事件标记
          </Button>
        </div>
      </div>
      {error ? <div className="inline-error">{error}</div> : null}
      <Card className="trend-oracle-banner">
        <div className="trend-oracle-copy">
          <Badge tone="purple">怀特 · 趋势解读</Badge>
          <h2>不用等很久，从第二次清算开始就能看见变化。</h2>
          <p>
            每一根线都来自你亲手确认过的资产快照。清算次数越多，回头看的故事也会越清楚。
          </p>
        </div>
        <Button
          loading={insightLoading}
          disabled={data.points.length < 2}
          onClick={interpretTrend}
        >
          <BrainCircuit />
          {data.points.length < 2 ? "再清算一次即可解读" : insight ? "重新深度解读" : "请怀特深度解读"}
        </Button>
      </Card>
      {insight ? (
        <Card className="card-pad trend-agent-insight" id="trend-agent-insight">
          <div className="agent-insight-head">
            <div>
              <Badge tone="purple">{insight.provider} · {insight.model}</Badge>
              <h2>怀特的趋势复盘</h2>
            </div>
            <BrainCircuit />
          </div>
          <div className="insight-verdict">{insight.result.executive_summary}</div>
          {insight.result.key_numbers.length ? (
            <div className="agent-key-numbers">
              {insight.result.key_numbers.map((item, index) => (
                <div key={`${item.label}-${index}`}><span>{item.label}</span><strong>{item.value}</strong><small>{item.meaning}</small></div>
              ))}
            </div>
          ) : null}
          <div className="insight-columns">
            <section>
              <h3>判断依据</h3>
              <ul>{insight.result.analysis.map((item) => <li key={item}>{item}</li>)}</ul>
              {insight.result.alternatives.length ? <><h3>其他合理解释</h3><ul>{insight.result.alternatives.map((item) => <li key={item}>{item}</li>)}</ul></> : null}
            </section>
            <section>
              <h3>接下来值得做</h3>
              <div className="insight-actions">
                {insight.result.recommendations.map((item, index) => (
                  <div key={`${item.action}-${index}`}>
                    <Badge tone={item.priority === "HIGH" ? "warning" : "purple"}>{item.priority === "HIGH" ? "优先" : item.priority === "MEDIUM" ? "随后" : "可选"}</Badge>
                    <strong>{item.action}</strong>
                    <p>{item.reason}</p>
                    {item.expected_impact ? <small>预期影响：{item.expected_impact}</small> : null}
                    {item.review_trigger ? <small>复盘触发：{item.review_trigger}</small> : null}
                    <Button variant="ghost" disabled={savedActions.includes(index)} onClick={() => saveInsightAction(item, index)}>
                      <BookmarkCheck /> {savedActions.includes(index) ? "已加入行动账本" : "加入行动账本"}
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </Card>
      ) : null}
      {!data.points.length ? (
        <Card className="card-pad">
          <Empty
            title="还没有清算点"
            body="完成第一次清算，这里就会放下第一枚坐标；再来一次，我们就能一起看方向了。"
            action={
              <a href="/clearing">
                <Button>开始清算</Button>
              </a>
            }
          />
        </Card>
      ) : (
        <>
          <section className="trend-metrics">
            <Card>
              <span>累计变化</span>
              <strong className={direction}>
                {direction === "up" ? (
                  <TrendingUp />
                ) : direction === "down" ? (
                  <TrendingDown />
                ) : (
                  <Minus />
                )}
                {money(a.total_change_cny, hidden)}
              </strong>
              <small>
                {a.change_rate_pct
                  ? `${Number(a.change_rate_pct).toFixed(2)}%`
                  : "从这里开始"}
              </small>
            </Card>
            <Card>
              <span>最大回撤</span>
              <strong>{a.max_drawdown_pct || "0.00"}%</strong>
              <small>历史峰值到当前低点</small>
            </Card>
            <Card>
              <span>清算点</span>
              <strong>{a.point_count}</strong>
              <small>跨度 {a.span_days || 0} 天</small>
            </Card>
            <Card>
              <span>分析等级</span>
              <strong className="level-text">{levelLabel(a.data_level)}</strong>
              <small>{a.point_count >= 2 ? "已经可以看方向" : "再清算一次就能看方向"}</small>
            </Card>
          </section>
          <Card className="card-pad trend-main">
            <div className="chart-controls">
              <div className="segmented">
                {[
                  { v: "net_worth_cny", l: "净资产" },
                  { v: "assets_cny", l: "总资产" },
                  { v: "liquid_assets_cny", l: "流动资产" },
                  { v: "investment_assets_cny", l: "投资资产" },
                ].map((x) => (
                  <button
                    key={x.v}
                    className={metric === x.v ? "active" : ""}
                    onClick={() => setMetric(x.v)}
                  >
                    {x.l}
                  </button>
                ))}
              </div>
              <div className="segmented">
                <button
                  className={view === "line" ? "active" : ""}
                  onClick={() => setView("line")}
                >
                  <LineChart />
                  清算点
                </button>
                <button
                  className={view === "candle" ? "active" : ""}
                  onClick={() => setView("candle")}
                >
                  <ChartCandlestick />K 线
                </button>
              </div>
              {view === "candle" ? (
                <select
                  className="compact-select"
                  value={granularity}
                  onChange={(e) => setGranularity(e.target.value)}
                >
                  <option value="day">日</option>
                  <option value="week">周</option>
                  <option value="month">月</option>
                  <option value="quarter">季度</option>
                  <option value="year">年</option>
                </select>
              ) : null}
            </div>
            <div className="chart-legend">
              <span>
                <i className="dot-solid" />
                完整快照
              </span>
              <span>
                <i className="dot-hollow" />
                完整度不足
              </span>
              {view === "candle" ? (
                <span>
                  <i className="dot-tiny" />
                  单点样本 O=H=L=C
                </span>
              ) : null}
            </div>
            {view === "line" ? (
              <TrendLine points={data.points} hidden={hidden} />
            ) : (
              <Candles items={data.candles} hidden={hidden} />
            )}
            <div className="chart-foot">
              <CircleAlert />
              <span>{data.disclaimer}</span>
            </div>
          </Card>
          {attribution ? (
            <Card className="card-pad attribution-card">
              <div className="card-head">
                <div className="card-title-row">
                  <div className="card-icon"><Activity /></div>
                  <div><h2>资产变动归因</h2><p>不只看涨跌，也把能确认的原因一层层拆出来。</p></div>
                </div>
                <Badge tone="purple">三问清算</Badge>
              </div>
              {!attribution.available ? <p className="warm-empty-note">{attribution.reason}</p> : (
                <>
                  <div className="attribution-summary"><strong>{attribution.narrative}</strong><small>{attribution.calculation_note}</small></div>
                  <AttributionWaterfall data={attribution} hidden={hidden} />
                  {attribution.questions.length ? (
                    <form className="three-question-form" onSubmit={saveThreeAnswers}>
                      <div className="three-question-head"><Sparkles /><div><h3>只问三个最有用的问题</h3><p>不用补录整本账单，选最接近真实情况的答案就好。</p></div></div>
                      <Field label={attribution.questions[0]?.question || "最接近实际情况的是？"}>
                        <select value={threeAnswers.cause} onChange={(e) => setThreeAnswers({ ...threeAnswers, cause: e.target.value })} required>
                          <option value="">请选择</option>
                          {attribution.questions[0]?.options?.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
                        </select>
                      </Field>
                      <Field label="大约涉及多少钱？">
                        <input inputMode="decimal" value={threeAnswers.amount} onChange={(e) => setThreeAnswers({ ...threeAnswers, amount: e.target.value })} placeholder={attribution.questions[1]?.suggested_value || "0"} required />
                      </Field>
                      <label className="remember-answer"><input type="checkbox" checked={threeAnswers.remember} onChange={(e) => setThreeAnswers({ ...threeAnswers, remember: e.target.checked })} /><span>以后遇到同类变化，把这个答案放在优先提示里</span></label>
                      <Button loading={attributionSaving}><Sparkles /> 更新归因结果</Button>
                    </form>
                  ) : <div className="attribution-complete"><Sparkles /> 这次变化已经有足够清楚的解释，不需要再补问题。</div>}
                </>
              )}
            </Card>
          ) : null}
          <div className="section-grid">
            <Card className="card-pad col-7">
              <div className="card-head">
                <div className="card-title-row">
                  <div className="card-icon">
                    <Sparkles />
                  </div>
                  <div>
                    <h2>这段时间发生了什么</h2>
                    <p>把几个重要变化放在一起看，会比只盯着一个数字更轻松。</p>
                  </div>
                </div>
                <Badge tone="purple">{levelLabel(a.data_level)}</Badge>
              </div>
              <div className="analysis-grid">
                <div>
                  <span>每清算点斜率</span>
                  <strong>{money(a.slope_per_clearing_cny, hidden)}</strong>
                </div>
                <div>
                  <span>波动程度</span>
                  <strong>
                    {a.volatility_pct ? `${a.volatility_pct}%` : "数据不足"}
                  </strong>
                </div>
                <div>
                  <span>最大回撤</span>
                  <strong>{a.max_drawdown_pct || 0}%</strong>
                </div>
              </div>
              <ul className="limitation-list">
                {a.limitations.map((x) => (
                  <li key={x}>{x}</li>
                ))}
              </ul>
            </Card>
            <Card className="card-pad col-5">
              <div className="card-head">
                <div>
                  <h2>事件标记</h2>
                  <p>把换汇、还贷或大额入金记下来，以后回看就不容易忘。</p>
                </div>
              </div>
              {data.annotations.length ? (
                <div className="event-list">
                  {data.annotations.map((x) => (
                    <div key={x.id}>
                      <span />
                      <div>
                        <strong>{x.label}</strong>
                        <small>
                          {formatDate(x.event_at)} · {x.event_type}
                        </small>
                        {x.notes ? <p>{x.notes}</p> : null}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty
                  title="还没有事件"
                  body="有过换汇、大额入金、还贷或买房时，可以在这里留一句话给未来的自己。"
                />
              )}
            </Card>
          </div>
        </>
      )}
      <Modal
        open={eventOpen}
        onClose={() => setEventOpen(false)}
        title="添加资产变化事件"
      >
        <form onSubmit={addEvent}>
          <div className="form-grid">
            <Field label="时间">
              <input
                type="datetime-local"
                value={event.event_at}
                onChange={(e) =>
                  setEvent({ ...event, event_at: e.target.value })
                }
                required
              />
            </Field>
            <Field label="类型">
              <select
                value={event.event_type}
                onChange={(e) =>
                  setEvent({ ...event, event_type: e.target.value })
                }
              >
                <option value="DEPOSIT">大额入金</option>
                <option value="FX">换汇</option>
                <option value="DEBT_PAYMENT">还贷</option>
                <option value="PROPERTY">房产变化</option>
                <option value="OTHER">其他</option>
              </select>
            </Field>
            <Field label="简短说明">
              <input
                value={event.label}
                onChange={(e) => setEvent({ ...event, label: e.target.value })}
                required
              />
            </Field>
            <Field label="备注">
              <textarea
                value={event.notes}
                onChange={(e) => setEvent({ ...event, notes: e.target.value })}
              />
            </Field>
          </div>
          <div className="form-actions">
            <Button
              variant="ghost"
              type="button"
              onClick={() => setEventOpen(false)}
            >
              取消
            </Button>
            <Button type="submit">
              <Plus />
              添加标记
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
function levelLabel(v: string) {
  return (
    (
      {
        EMPTY: "无数据",
        BASELINE: "起点",
        DIRECTION_ONLY: "只描述方向",
        PRELIMINARY: "初步趋势",
        FULL: "趋势可读",
      } as Record<string, string>
    )[v] || v
  );
}
export default function TrendPage() {
  return (
    <Protected>
      <TrendContent />
    </Protected>
  );
}
