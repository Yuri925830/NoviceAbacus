"use client";
import { Protected } from "@/components/app-shell";
import { Badge, Button, Card, Empty, Skeleton } from "@/components/ui";
import { usePrivacy } from "@/components/providers";
import { api, formatDate, money, percent } from "@/lib/api";
import type { Dashboard } from "@/lib/types";
import {
  ArrowRight,
  BatteryCharging,
  CalendarClock,
  ChartNoAxesCombined,
  CircleAlert,
  Coins,
  Landmark,
  Plus,
  ScanLine,
  Sparkles,
  Target,
  TrendingUp,
  WalletCards,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

const assetPalette: Record<string, { color: string; soft: string }> = {
  CASH: { color: "#6c3ec2", soft: "#eee6fa" },
  FIXED_DEPOSIT: { color: "#9564cf", soft: "#f0e8f8" },
  STOCK: { color: "#4b6fb5", soft: "#e8edf8" },
  FUND: { color: "#bd548f", soft: "#f8e8f1" },
  GOLD: { color: "#c58a32", soft: "#faf0dc" },
  PENSION: { color: "#7b5eb9", soft: "#ece8f7" },
  PROPERTY: { color: "#b66155", soft: "#f8e9e6" },
  VEHICLE: { color: "#596b99", soft: "#e9ecf4" },
  LOAN_RECEIVABLE: { color: "#a97145", soft: "#f6ece3" },
  LIABILITY: { color: "#c74962", soft: "#fae8ec" },
  OTHER: { color: "#71717f", soft: "#ececf0" },
};

function DashboardContent() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const { hidden } = usePrivacy();
  useEffect(() => {
    api<Dashboard>("/dashboard")
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);
  if (!data && !error)
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">MY FINANCIAL HOME</div>
            <h1>资产驾驶舱</h1>
          </div>
        </div>
        <Skeleton height={210} />
      </>
    );
  if (error)
    return (
      <Card className="card-pad">
        <Empty title="暂时打不开驾驶舱" body={error} />
      </Card>
    );
  if (!data?.has_snapshot)
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">YOUR FINANCIAL BASELINE</div>
            <h1>从第一张资产底牌开始</h1>
            <p>先留下第一张资产快照。以后回头看，每一步都会更清楚。</p>
          </div>
        </div>
        <div className="onboarding-grid">
          <Card className="onboarding-main">
            <div className="onboarding-copy">
              <Badge tone="purple">第一步 · 约 10 分钟</Badge>
              <h2>把资产放到同一个时间点里看</h2>
              <p>上传截图或手工添加都可以，怀特会陪你一项一项理顺。</p>
              <Link href="/clearing">
                <Button>
                  开始第一次清算 <ArrowRight size={17} />
                </Button>
              </Link>
            </div>
            <div className="onboarding-orbits">
              <span />
              <span />
              <span />
              <Sparkles />
            </div>
          </Card>
          <Card className="card-pad">
            <div className="card-head">
              <div>
                <h3>你会得到什么</h3>
                <p>不是流水账，是清算时点的资产全景</p>
              </div>
            </div>
            <ul className="value-list">
              <li>
                <ScanLine />
                <div>
                  <strong>一张可信快照</strong>
                  <span>原币、汇率、人民币价值全部可追溯</span>
                </div>
              </li>
              <li>
                <ChartNoAxesCombined />
                <div>
                  <strong>一条慢慢长出来的趋势</strong>
                  <span>每次清算都会留下一个坐标，方便以后回头看。</span>
                </div>
              </li>
              <li>
                <Sparkles />
                <div>
                  <strong>一份白话解释</strong>
                  <span>事实、判断、建议和限制清楚分开</span>
                </div>
              </li>
            </ul>
          </Card>
        </div>
      </>
    );
  const t = data.totals!;
  const spend = data.spending;
  const types = Object.entries(t.type_percentages || {}).sort(
    (a, b) => Number(b[1]) - Number(a[1]),
  );
  return (
    <>
      <div className="page-head">
        <div>
            <div className="eyebrow">MY FINANCIAL HOME</div>
          <h1>你的资产底牌</h1>
          <p>
            最近清算于 {formatDate(data.snapshot?.confirmed_at)} · 完整度{" "}
            {data.snapshot?.completeness}%
          </p>
        </div>
        <div className="page-actions">
          <Link href="/clearing">
            <Button>
              <Plus size={17} />
              发起清算
            </Button>
          </Link>
          <Link href="/assistant">
            <Button variant="secondary">
              <Sparkles size={17} />
              问怀特
            </Button>
          </Link>
        </div>
      </div>
      <Card className="dashboard-spending-spotlight">
        <div className="dashboard-spending-art" aria-hidden="true" />
        <div className="dashboard-spending-copy">
          <Badge tone="purple">今天先看这一件事</Badge>
          {spend.ready ? (
            <>
              <span>本月可以更安心地自由安排</span>
              <strong>{money(spend.safe_to_spend_cny, hidden)}</strong>
              <p>
                财务电量 {Number(spend.battery?.before_pct).toFixed(0)}% · {spend.battery?.before_label}。
                想买东西之前，先让怀特替你看看买完后的日子会不会变紧。
              </p>
            </>
          ) : (
            <>
              <span>再补几个日常数字</span>
              <strong>算出放心花额度</strong>
              <p>{spend.reason}</p>
            </>
          )}
          <Link href="/spending">去做一笔钱事裁决 <ArrowRight /></Link>
        </div>
        {spend.ready ? (
          <div className="dashboard-battery">
            <BatteryCharging />
            <strong>{Number(spend.battery?.before_pct).toFixed(0)}%</strong>
            <span>财务电量</span>
          </div>
        ) : null}
      </Card>
      <section className="metric-grid">
        <Card className="metric-card metric-primary">
          <div className="metric-label">
            <span>当前净资产</span>
            <Badge tone="purple">基准 CNY</Badge>
          </div>
          <strong className="amount">{money(t.net_worth_cny, hidden)}</strong>
          <div className="metric-change">
            <TrendingUp size={15} />
            <span>
              {(data.snapshot?.comparison as { is_baseline?: boolean })
                ?.is_baseline
                ? "这是你的第一条基准线"
                : `较上次 ${money((data.snapshot?.comparison as { net_worth_change_cny?: string })?.net_worth_change_cny, hidden)}`}
            </span>
          </div>
          <div className="metric-glow" />
        </Card>
        <Card className="metric-card">
          <div className="metric-label">
            <span>总资产</span>
            <WalletCards size={18} />
          </div>
          <strong className="amount">{money(t.assets_cny, hidden)}</strong>
          <small>全部已确认资产</small>
        </Card>
        <Card className="metric-card">
          <div className="metric-label">
            <span>总负债</span>
            <Landmark size={18} />
          </div>
          <strong className="amount">{money(t.liabilities_cny, hidden)}</strong>
          <small>当前应还余额</small>
        </Card>
        <Card className="metric-card">
          <div className="metric-label">
            <span>可立即使用</span>
            <Coins size={18} />
          </div>
          <strong className="amount">
            {money(t.liquid_assets_cny, hidden)}
          </strong>
          <small>不含受限资产</small>
        </Card>
      </section>
      <div className="section-grid dashboard-grid">
        <Card className="card-pad col-7">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <ChartNoAxesCombined size={18} />
              </div>
              <div>
                <h2>资产结构</h2>
                <p>按人民币价值计算，不重复计入浮盈</p>
              </div>
            </div>
            <Link href="/assets" className="text-link">
              查看明细 <ArrowRight />
            </Link>
          </div>
          <div className="structure-list">
            {types.length ? (
              types.map(([key, value]) => {
                const palette = assetPalette[key] || assetPalette.OTHER;
                return (
                <div
                  className="structure-row"
                  key={key}
                  style={
                    {
                      "--asset-color": palette.color,
                      "--asset-soft": palette.soft,
                    } as React.CSSProperties
                  }
                >
                  <div>
                    <span className="structure-dot" />
                    <strong>{labelType(key)}</strong>
                    <em>{percent(value)}</em>
                  </div>
                  <div className="structure-track">
                    <i style={{ width: `${Math.min(Number(value), 100)}%` }} />
                  </div>
                  <small>{money(t.by_type[key], hidden)}</small>
                </div>
                );
              })
            ) : (
              <p className="muted">暂无分类数据</p>
            )}
          </div>
        </Card>
        <Card className="fox-insight col-5">
          <div className="fox-insight-bg" />
          <div className="fox-insight-content">
            <Badge tone="purple">怀特观察</Badge>
            <h2>
              {Number(
                (data.trend as { point_count?: number }).point_count || 0,
              ) < 4
                ? "已经有了起点，再清算一次就能看见方向。"
                : "趋势已有初步轮廓，别急着把变化都叫收益。"}
            </h2>
            <p>
              {String(
                ((data.trend as { limitations?: string[] }).limitations ||
                  [])[0] ||
                  "资产规模变化可能同时来自入金、价格、汇率和负债变化。",
              )}
            </p>
            <Link href="/trend">
              看完整趋势 <ArrowRight />
            </Link>
          </div>
        </Card>
        <Card className="card-pad col-7">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <Target size={18} />
              </div>
              <div>
                <h2>目标进度</h2>
                <p>把远一点的愿望，拆成现在看得见的一小步。</p>
              </div>
            </div>
            <Link href="/goals" className="text-link">
              管理目标
            </Link>
          </div>
          {data.goals.length ? (
            <div className="goal-list">
              {data.goals.map((goal) => (
                <div className="goal-row" key={goal.id}>
                  <div className="goal-row-head">
                    <div>
                      <strong>{goal.name}</strong>
                      <span>
                        {money(goal.current_cny, hidden)} /{" "}
                        {money(goal.target_cny, hidden)}
                      </span>
                    </div>
                    <b>{percent(goal.progress_pct)}</b>
                  </div>
                  <div className="goal-track">
                    <i
                      style={{
                        width: `${Math.min(Number(goal.progress_pct), 100)}%`,
                      }}
                    />
                  </div>
                  <small>
                    还差 {money(goal.gap_cny, hidden)}
                    {goal.due_date
                      ? ` · 目标日 ${formatDate(goal.due_date)}`
                      : ""}
                  </small>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="还没有目标"
              body="设置净资产、可用现金或特定用途目标，清算后自动更新进度。"
              action={
                <Link href="/goals">
                  <Button variant="secondary">添加目标</Button>
                </Link>
              }
            />
          )}
        </Card>
        <Card className="card-pad col-5">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <CircleAlert size={18} />
              </div>
              <div>
                <h2>需要留意</h2>
                <p>把值得留意的事情说清楚，也不会故意吓人。</p>
              </div>
            </div>
          </div>
          {data.risks.length ? (
            <div className="risk-list">
              {data.risks.map((risk) => (
                <div
                  className={`risk-row risk-${risk.level.toLowerCase()}`}
                  key={risk.code}
                >
                  <CircleAlert />
                  <div>
                    <strong>{risk.title}</strong>
                    <span>{risk.detail}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="quiet-state">
              <Sparkles />
              <strong>当前没有触发规则风险</strong>
              <span>目前看起来很平稳，之后也记得偶尔回来更新一下。</span>
            </div>
          )}
          <div className="next-clearing">
            <CalendarClock />
            <div>
              <span>下次计划清算</span>
              <strong>{formatDate(data.next_clearing_at)}</strong>
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
function labelType(value: string) {
  return (
    (
      {
        CASH: "现金与存款",
        STOCK: "股票",
        FUND: "基金",
        GOLD: "黄金",
        PENSION: "公积金/养老金",
        PROPERTY: "房产",
        FIXED_DEPOSIT: "定期存款",
        OTHER: "其他资产",
      } as Record<string, string>
    )[value] || value
  );
}
export default function DashboardPage() {
  return (
    <Protected>
      <DashboardContent />
    </Protected>
  );
}
