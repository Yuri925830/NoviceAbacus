"use client";

import { Protected } from "@/components/app-shell";
import { Badge, Button, Card, Empty, Field, Skeleton } from "@/components/ui";
import { api, errorMessage, formatDate, money } from "@/lib/api";
import { CircleAlert, FileSearch, FileText, FlaskConical, ScanLine, ShieldAlert, Sparkles, Trash2, Upload } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

type Xray = {
  id: string; filename: string; content_type: string; page_count?: number; provider: string; model: string; created_at: string; original_file_stored: boolean;
  extraction: {
    product_name: string; product_type: string; issuer: string; principal_guaranteed: { value: string; evidence: string }; return_type: string;
    displayed_return: { value: string; meaning: string; is_guaranteed: boolean }; closure_period: string; minimum_holding_period: string;
    early_redemption: { allowed: string; loss_or_condition: string }; fees: Array<{ name: string; value: string; evidence: string }>;
    risk_level: string; underlying_assets: string[]; worst_case: string; liquidity_features: string[]; plain_language_summary: string[]; red_flags: string[];
    evidence: Array<{ field: string; text: string }>; unknown_fields: string[]; scope: string;
  };
  suitability: { intended_amount_cny?: string; liquid_assets_before_cny?: string; liquid_assets_after_cny?: string; runway_before_months?: string; runway_after_months?: string; flags: string[]; calculation_note: string };
};

function XrayContent() {
  const [items, setItems] = useState<Xray[]>([]);
  const [selected, setSelected] = useState<Xray | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  async function load() { try { const result = await api<Xray[]>("/xray"); setItems(result); setSelected((current) => current ? result.find((item) => item.id === current.id) || result[0] || null : result[0] || null); } catch (e) { setError(errorMessage(e)); } finally { setLoading(false); } }
  useEffect(() => { load(); }, []);
  async function analyze(e: FormEvent) { e.preventDefault(); if (!file) return; setAnalyzing(true); setError(""); const body = new FormData(); body.append("file", file); if (amount) body.append("intended_amount_cny", amount); try { const result = await api<Xray>("/xray", { method: "POST", body }); setSelected(result); setFile(null); if (fileRef.current) fileRef.current.value = ""; await load(); } catch (e) { setError(errorMessage(e)); } finally { setAnalyzing(false); } }
  async function remove(id: string) { if (!confirm("确定删除这份产品 X 光吗？")) return; await api(`/xray/${id}`, { method: "DELETE" }); if (selected?.id === id) setSelected(null); await load(); }
  if (loading) return <><div className="page-head"><div><div className="eyebrow">PRODUCT X-RAY</div><h1>理财产品 X 光</h1></div></div><Skeleton height={520} /></>;
  return <>
    <div className="page-head xray-head"><div><div className="eyebrow">PRODUCT X-RAY</div><h1>理财产品 X 光</h1><p>把专业条款翻译成人话，再放回你的现金流里看看是否合拍。</p></div><Badge tone="purple"><ShieldAlert /> 不输出买入或卖出指令</Badge></div>
    {error ? <div className="inline-error"><CircleAlert />{error}</div> : null}
    <div className="xray-layout">
      <aside className="xray-side">
        <Card className="card-pad xray-uploader"><div className="card-title-row"><div className="card-icon"><ScanLine /></div><div><h2>上传产品页面</h2><p>支持截图或 PDF，原文件分析后不保留。</p></div></div><form onSubmit={analyze}><button type="button" className={`xray-drop ${file ? "has-file" : ""}`} onClick={() => fileRef.current?.click()}><Upload /><strong>{file ? file.name : "选择截图或 PDF"}</strong><span>PNG / JPG / WebP / PDF</span></button><input ref={fileRef} type="file" hidden accept="image/png,image/jpeg,image/webp,application/pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} /><Field label="如果考虑投入，大约多少钱？" hint="可留空；填写后会计算现金续航变化。"><input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="例如 50000" /></Field><Button className="full-button" loading={analyzing} disabled={!file}><FileSearch /> 开始做 X 光</Button></form></Card>
        <Card className="card-pad xray-history"><h3>最近分析</h3>{items.length ? items.map((item) => <button key={item.id} className={selected?.id === item.id ? "active" : ""} onClick={() => setSelected(item)}><FileText /><span><strong>{item.extraction.product_name || item.filename}</strong><small>{formatDate(item.created_at)}</small></span><i onClick={(e) => { e.stopPropagation(); remove(item.id); }}><Trash2 /></i></button>) : <p>还没有分析记录。</p>}</Card>
      </aside>
      <main className="xray-result">
        {!selected ? <Card className="card-pad"><Empty title="先放进一份产品资料" body="怀特会逐项找出保本、收益口径、封闭期、赎回、费用、风险等级和底层资产。" /></Card> : <>
          <Card className="xray-hero"><div><Badge tone="purple">{selected.extraction.product_type}</Badge><h2>{selected.extraction.product_name}</h2><p>{selected.extraction.issuer}</p></div><div><span>本金保证</span><strong className={selected.extraction.principal_guaranteed.value === "YES" ? "positive" : "negative"}>{selected.extraction.principal_guaranteed.value === "YES" ? "页面明确保本" : selected.extraction.principal_guaranteed.value === "NO" ? "不保证本金" : "页面没有写清"}</strong><small>{selected.extraction.principal_guaranteed.evidence}</small></div></Card>
          <Card className="card-pad xray-plain"><div className="card-head"><div className="card-title-row"><div className="card-icon"><Sparkles /></div><div><h2>先用普通话讲明白</h2><p>这些结论只来自页面明确条款。</p></div></div><Badge>{selected.provider} · {selected.model}</Badge></div><ul>{selected.extraction.plain_language_summary.map((item) => <li key={item}>{item}</li>)}</ul></Card>
          <section className="xray-facts"><Card><span>页面展示收益</span><strong>{selected.extraction.displayed_return.value}</strong><small>{selected.extraction.displayed_return.meaning}</small></Card><Card><span>封闭期</span><strong>{selected.extraction.closure_period}</strong><small>最短持有：{selected.extraction.minimum_holding_period}</small></Card><Card><span>提前赎回</span><strong>{selected.extraction.early_redemption.allowed === "YES" ? "允许" : selected.extraction.early_redemption.allowed === "NO" ? "不允许" : "未写清"}</strong><small>{selected.extraction.early_redemption.loss_or_condition}</small></Card><Card><span>风险等级</span><strong>{selected.extraction.risk_level}</strong><small>{selected.extraction.underlying_assets.join("、") || "底层资产未写清"}</small></Card></section>
          <Card className="card-pad suitability-card"><div className="card-head"><div className="card-title-row"><div className="card-icon"><FlaskConical /></div><div><h2>放回你的现金流里看</h2><p>重点不是产品名字，而是这段时间的钱还能不能随时使用。</p></div></div></div>{selected.suitability.runway_before_months ? <div className="runway-shift"><div><span>投入前现金续航</span><strong>{selected.suitability.runway_before_months} 个月</strong></div><i>→</i><div><span>投入后现金续航</span><strong>{selected.suitability.runway_after_months} 个月</strong></div></div> : null}<ul>{selected.suitability.flags.map((item) => <li key={item}>{item}</li>)}</ul><small>{selected.suitability.calculation_note}</small></Card>
          <div className="xray-detail-grid"><Card className="card-pad"><h3>费用清单</h3>{selected.extraction.fees.length ? <dl>{selected.extraction.fees.map((fee, index) => <div key={`${fee.name}-${index}`}><dt>{fee.name}</dt><dd>{fee.value}<small>{fee.evidence}</small></dd></div>)}</dl> : <p>页面没有清楚列出费用。</p>}</Card><Card className="card-pad danger-panel"><h3>最坏情况下可能发生什么</h3><p>{selected.extraction.worst_case}</p>{selected.extraction.red_flags.map((item) => <div key={item}><CircleAlert />{item}</div>)}</Card></div>
          <Card className="card-pad evidence-panel"><h3>仍需要向销售方确认</h3><div>{selected.extraction.unknown_fields.map((item) => <Badge key={item}>{item}</Badge>)}</div><p>{selected.extraction.scope}</p></Card>
        </>}
      </main>
    </div>
  </>;
}
export default function XrayPage() { return <Protected><XrayContent /></Protected>; }
