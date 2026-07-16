"use client";
import { Protected } from "@/components/app-shell";
import { usePrivacy } from "@/components/providers";
import { Badge, Button, Card, Empty, Modal, Skeleton } from "@/components/ui";
import { api, apiUrl, errorMessage, formatDate, money } from "@/lib/api";
import type { ClearingSession } from "@/lib/types";
import {
  ArchiveRestore,
  ArrowRight,
  CalendarDays,
  Download,
  FileJson,
  FileSpreadsheet,
  History,
  PencilLine,
  ReceiptText,
  Trash2,
  WalletCards,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

function AssetsContent() {
  const [rows, setRows] = useState<ClearingSession[] | null>(null);
  const [selected, setSelected] = useState<ClearingSession | null>(null);
  const [error, setError] = useState("");
  const { hidden } = usePrivacy();
  const router = useRouter();
  const load = () =>
    api<ClearingSession[]>("/sessions")
      .then((result) => { setRows(result); setError(""); })
      .catch((e) => setError(errorMessage(e)));
  useEffect(() => {
    load();
  }, []);
  async function open(row: ClearingSession) {
    setError("");
    try {
      setSelected(await api<ClearingSession>(`/sessions/${row.id}`));
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function revise(row: ClearingSession) {
    const reason = prompt(
      "本次修订原因（会保留原版本审计）：",
      "修正资产金额或分类",
    );
    if (!reason) return;
    setError("");
    try {
      await api(`/sessions/${row.id}/revise`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      router.push("/clearing");
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function remove(row: ClearingSession) {
    if (!confirm("确定删除这次清算？趋势、K 线和指标会随之重算。")) return;
    setError("");
    try {
      await api(`/sessions/${row.id}`, { method: "DELETE" });
      setSelected(null);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  if (!rows && error) return <Card className="card-pad"><Empty title="暂时无法读取清算历史" body={error} action={<Button onClick={load}>重新加载</Button>} /></Card>;
  if (!rows)
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">CLEARING HISTORY</div>
            <h1>清算历史记录</h1>
          </div>
        </div>
        <Skeleton height={370} />
      </>
    );
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">AUDITABLE CLEARING HISTORY</div>
          <h1>清算历史记录</h1>
          <p>每次清算都会留下一张快照。后来发现哪里写错了，也能修订，同时保留之前的版本。</p>
        </div>
        <div className="page-actions">
          <a href="/clearing">
            <Button>
              发起新清算 <ArrowRight />
            </Button>
          </a>
        </div>
      </div>
      {error ? <div className="inline-error">{error}</div> : null}
      {rows.length ? (
        <div className="history-layout">
          <div className="history-timeline">
            {rows.map((row, index) => (
              <div
                className={`timeline-item status-${row.status.toLowerCase()}`}
                key={row.id}
              >
                <div className="timeline-axis">
                  <span>{index === 0 ? <WalletCards /> : <History />}</span>
                  <i />
                </div>
                <Card className="history-card">
                  <button className="history-open" onClick={() => open(row)}>
                    <div className="history-date">
                      <CalendarDays />
                      <div>
                        <strong>
                          {formatDate(row.confirmed_at || row.started_at)}
                        </strong>
                        <span>
                          {row.kind === "AD_HOC" ? "临时清算" : "计划清算"} ·
                          完整度 {row.completeness}%
                        </span>
                      </div>
                    </div>
                    <div className="history-net">
                      <span>净资产</span>
                      <strong>
                        {money(row.totals?.net_worth_cny, hidden)}
                      </strong>
                    </div>
                    <div className="history-delta">
                      <span>较上次</span>
                      <strong>
                        {money(
                          (row.comparison as { net_worth_change_cny?: string })
                            ?.net_worth_change_cny,
                          hidden,
                        )}
                      </strong>
                    </div>
                    <div>
                      <Badge
                        tone={
                          row.status === "SUPERSEDED" ? "neutral" : "purple"
                        }
                      >
                        {row.status === "SUPERSEDED"
                          ? "已被修订"
                          : `版本 ${row.revision_number}`}
                      </Badge>
                    </div>
                    <ArrowRight />
                  </button>
                </Card>
              </div>
            ))}
          </div>
          <Card className="history-side">
            <ArchiveRestore />
            <h2>可追溯，不覆盖</h2>
            <p>
              发现哪里不对时，可以从这张快照创建修订。旧版本会好好保留，趋势会采用最新版本。
            </p>
            <ul>
              <li>原币金额与人民币价值</li>
              <li>汇率来源与时间</li>
              <li>确认完整度与修订原因</li>
              <li>CSV / JSON / PDF 导出</li>
            </ul>
          </Card>
        </div>
      ) : (
        <Card className="card-pad">
          <Empty
            title="还没有清算历史"
            body="完成第一次清算后，你的第一张资产快照就会安静地收在这里。"
            action={
              <a href="/clearing">
                <Button>开始清算</Button>
              </a>
            }
          />
        </Card>
      )}
      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title={`清算详情 · 版本 ${selected?.revision_number || 1}`}
      >
        {selected ? (
          <div className="snapshot-detail">
            <div className="snapshot-summary">
              <div>
                <span>总资产</span>
                <strong>{money(selected.totals?.assets_cny, hidden)}</strong>
              </div>
              <div>
                <span>总负债</span>
                <strong>
                  {money(selected.totals?.liabilities_cny, hidden)}
                </strong>
              </div>
              <div className="highlight">
                <span>净资产</span>
                <strong>{money(selected.totals?.net_worth_cny, hidden)}</strong>
              </div>
            </div>
            <div className="detail-meta">
              <span>
                <CalendarDays /> {formatDate(selected.confirmed_at)}
              </span>
              <span>
                <ReceiptText /> 完整度 {selected.completeness}%
              </span>
              <span>
                <History /> 状态 {selected.status}
              </span>
            </div>
            <div className="detail-items">
              {selected.items
                ?.filter((x) => ["CONFIRMED", "REVISED"].includes(x.status))
                .map((item) => (
                  <div key={item.id}>
                    <div>
                      <strong>{item.name}</strong>
                      <span>
                        {item.asset_type} · {item.liquidity_level}
                      </span>
                    </div>
                    <div>
                      <strong>
                        {Number(item.original_value).toLocaleString()}{" "}
                        {item.original_currency}
                      </strong>
                      <span>
                        {item.fx_rate_to_cny
                          ? `汇率 ${Number(item.fx_rate_to_cny).toPrecision(6)}`
                          : ""}
                      </span>
                    </div>
                    <b>{money(item.value_cny, hidden)}</b>
                  </div>
                ))}
            </div>
            <div className="export-row">
              <a href={apiUrl(`/sessions/${selected.id}/export/csv`)}>
                <Button variant="secondary">
                  <FileSpreadsheet />
                  CSV
                </Button>
              </a>
              <a href={apiUrl(`/sessions/${selected.id}/export/json`)}>
                <Button variant="secondary">
                  <FileJson />
                  JSON
                </Button>
              </a>
              <a href={apiUrl(`/sessions/${selected.id}/export/pdf`)}>
                <Button variant="secondary">
                  <Download />
                  PDF 报告
                </Button>
              </a>
            </div>
            {selected.status !== "SUPERSEDED" ? (
              <div className="form-actions">
                <Button variant="ghost" onClick={() => revise(selected)}>
                  <PencilLine />
                  创建修订
                </Button>
                <Button variant="danger" onClick={() => remove(selected)}>
                  <Trash2 />
                  删除本次
                </Button>
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  );
}
export default function AssetsPage() {
  return (
    <Protected>
      <AssetsContent />
    </Protected>
  );
}
