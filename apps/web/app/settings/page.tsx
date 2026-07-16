"use client";
import { Protected } from "@/components/app-shell";
import {
  Badge,
  Button,
  Card,
  Field,
  Modal,
  Skeleton,
} from "@/components/ui";
import { api, errorMessage, formatDate } from "@/lib/api";
import type { Me } from "@/lib/types";
import {
  CalendarClock,
  Check,
  Copy,
  KeyRound,
  Laptop,
  Plus,
  Save,
  Server,
  ShieldCheck,
  Smartphone,
  Sparkles,
  UserRoundCog,
  Vault,
} from "lucide-react";
import QRCode from "qrcode";
import Image from "next/image";
import { FormEvent, useEffect, useState } from "react";

type Settings = {
  region: string;
  model_preference: string;
  timezone: string;
  providers: {
    qwen: {
      configured: boolean;
      workspace_configured: boolean;
      ocr_model: string;
      vision_model: string;
      chat_model: string;
    };
    openai: {
      configured: boolean;
      gateway_reachable: boolean;
      upstream_available: boolean | null;
      error_code: string | null;
      checked_at: string | null;
      ordinary_model: string;
      complex_model: string;
      region_allowed: boolean;
    };
    fx: { provider: string; max_age_hours: number };
    gold: { mode: string; message: string };
  };
  schedule?: Record<string, unknown> | null;
};
type Device = {
  id: string;
  device_name: string;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at?: string;
};
type Quote = {
  id: string;
  method: string;
  price_per_gram_cny: string;
  source: string;
  quoted_at: string;
  brand?: string;
  city?: string;
};
function SettingsContent() {
  const [data, setData] = useState<Settings | null>(null),
    [devices, setDevices] = useState<Device[]>([]),
    [quotes, setQuotes] = useState<Quote[]>([]),
    [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  const [owner, setOwner] = useState({
    region: "UNKNOWN",
    model_preference: "AUTO",
    timezone: "Asia/Seoul",
  });
  const [schedule, setSchedule] = useState({
    frequency: "MONTHLY",
    timezone: "Asia/Seoul",
    hour: 20,
    minute: 0,
    day_of_month: 28,
    weekday: 0,
    custom_date: "",
    remind_before_days: 1,
    repeat_overdue_days: 2,
    email_enabled: true,
    paused: false,
  });
  const [quoteOpen, setQuoteOpen] = useState(false),
    [quote, setQuote] = useState({
      method: "INTERNATIONAL",
      price_per_gram_cny: "",
      source: "",
      quoted_at: new Date().toISOString().slice(0, 16),
      brand: "",
      city: "",
    });
  async function load() {
    setError("");
    try {
      const [s, d, q] = await Promise.all([
        api<Settings>("/settings"),
        api<Device[]>("/auth/devices"),
        api<Quote[]>("/gold/quotes"),
      ]);
      setData(s);
      setOwner({
        region: s.region,
        model_preference: s.model_preference,
        timezone: s.timezone,
      });
      if (s.schedule)
        setSchedule((old) => ({ ...old, ...s.schedule }) as typeof old);
      setDevices(d);
      setQuotes(q);
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  useEffect(() => {
    load();
  }, []);
  async function saveOwner() {
    setSaving(true);
    setError("");
    try {
      await api("/settings", { method: "PUT", body: JSON.stringify(owner) });
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }
  async function saveSchedule() {
    setSaving(true);
    setError("");
    try {
      await api("/schedule", {
        method: "PUT",
        body: JSON.stringify({
          ...schedule,
          custom_date: schedule.custom_date || null,
          timezone: owner.timezone,
        }),
      });
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }
  async function addQuote(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api("/gold/quotes", {
        method: "POST",
        body: JSON.stringify({
          ...quote,
          quoted_at: new Date(quote.quoted_at).toISOString(),
          brand: quote.brand || null,
          city: quote.city || null,
        }),
      });
      setQuoteOpen(false);
      setQuote((current) => ({ ...current, price_per_gram_cny: "", source: "" }));
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }
  async function revoke(id: string) {
    if (!confirm("让这台设备立即退出？")) return;
    setError("");
    try {
      await api(`/auth/devices/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  if (!data && error) return <Card className="card-pad"><div className="inline-error">{error}</div><Button onClick={() => void load()}>重新加载</Button></Card>;
  if (!data)
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">MY PREFERENCES</div>
            <h1>系统设置</h1>
          </div>
        </div>
        <Skeleton height={420} />
      </>
    );
  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">MY PREFERENCES</div>
          <h1>系统设置</h1>
          <p>把提醒时间、智能线路和账号保护调成你用起来最顺手的样子。</p>
        </div>
      </div>
      {error ? <div className="inline-error">{error}</div> : null}
      <div className="settings-layout">
        <nav className="settings-nav">
          <a href="#account">
            <UserRoundCog />
            账号与智能顾问
          </a>
          <a href="#security">
            <ShieldCheck />
            双重验证
          </a>
          <a href="#schedule">
            <CalendarClock />
            清算计划
          </a>
          <a href="#market">
            <Server />
            行情来源
          </a>
          <a href="#devices">
            <Laptop />
            可信设备
          </a>
        </nav>
        <div className="settings-content">
          <Card className="card-pad settings-section" id="account">
            <div className="card-head">
              <div className="card-title-row">
                <div className="card-icon">
                  <UserRoundCog />
                </div>
                <div>
                  <h2>账号与智能顾问</h2>
                  <p>选择你所在的地区，系统会自动走合适的智能线路。</p>
                </div>
              </div>
              <Button loading={saving} onClick={saveOwner}>
                <Save />
                保存
              </Button>
            </div>
            <div className="form-grid">
              <Field label="当前使用地区">
                <select
                  value={owner.region}
                  onChange={(e) =>
                    setOwner({
                      ...owner,
                      region: e.target.value,
                      model_preference:
                        e.target.value === "CN"
                          ? "QWEN"
                          : owner.model_preference,
                    })
                  }
                >
                  <option value="UNKNOWN">无法可靠判断</option>
                  <option value="CN">中国大陆</option>
                  <option value="KR">韩国</option>
                  <option value="OTHER_SUPPORTED">
                    其他 OpenAI 官方支持地区
                  </option>
                </select>
              </Field>
              <Field label="模型偏好">
                <select
                  value={owner.model_preference}
                  onChange={(e) =>
                    setOwner({ ...owner, model_preference: e.target.value })
                  }
                >
                  <option value="AUTO">自动（推荐）</option>
                  <option value="QWEN">仅千问北京</option>
                  <option
                    value="OPENAI"
                    disabled={
                      owner.region === "CN" || owner.region === "UNKNOWN"
                    }
                  >
                    OpenAI 海外网关
                  </option>
                </select>
              </Field>
              <Field label="时区">
                <select
                  value={owner.timezone}
                  onChange={(e) =>
                    setOwner({ ...owner, timezone: e.target.value })
                  }
                >
                  <option value="Asia/Seoul">Asia/Seoul</option>
                  <option value="Asia/Shanghai">Asia/Shanghai</option>
                  <option value="Asia/Hong_Kong">Asia/Hong_Kong</option>
                  <option value="UTC">UTC</option>
                </select>
              </Field>
            </div>
            <div className="provider-grid">
              <Provider
                name="千问北京"
                status={
                  data.providers.qwen.configured ? "available" : "unconfigured"
                }
                detail={`${data.providers.qwen.ocr_model} · ${data.providers.qwen.chat_model}`}
              />
              <Provider
                name="OpenAI 海外网关"
                status={openAIStatus(data.providers.openai)}
                detail={`${data.providers.openai.ordinary_model} · ${data.providers.openai.complex_model}${data.providers.openai.error_code ? ` · ${data.providers.openai.error_code}` : ""}`}
              />
            </div>
          </Card>
          <Card className="card-pad settings-section" id="security">
            <div className="card-head">
              <div className="card-title-row">
                <div className="card-icon">
                  <Vault />
                </div>
                <div>
                  <h2>双重验证</h2>
                  <p>给账号多加一道保护。恢复码会在绑定成功后显示一次，记得收好。</p>
                </div>
              </div>
            </div>
            <TotpSetup />
          </Card>
          <Card className="card-pad settings-section" id="schedule">
            <div className="card-head">
              <div className="card-title-row">
                <div className="card-icon">
                  <CalendarClock />
                </div>
                <div>
                  <h2>清算计划与提醒</h2>
                  <p>选一个你方便的时间，到点会在站内和邮箱轻轻提醒你。</p>
                </div>
              </div>
              <Button loading={saving} onClick={saveSchedule}>
                <Save />
                保存计划
              </Button>
            </div>
            <div className="form-grid">
              <Field label="周期">
                <select
                  value={schedule.frequency}
                  onChange={(e) =>
                    setSchedule({ ...schedule, frequency: e.target.value })
                  }
                >
                  <option value="WEEKLY">每周</option>
                  <option value="MONTHLY">每月</option>
                  <option value="QUARTERLY">每三个月</option>
                  <option value="SEMIANNUAL">每六个月</option>
                  <option value="YEARLY">每年</option>
                  <option value="CUSTOM">单次指定日期</option>
                </select>
              </Field>
              {schedule.frequency === "WEEKLY" ? (
                <Field label="星期">
                  <select
                    value={schedule.weekday}
                    onChange={(e) =>
                      setSchedule({
                        ...schedule,
                        weekday: Number(e.target.value),
                      })
                    }
                  >
                    <option value={0}>周一</option>
                    <option value={1}>周二</option>
                    <option value={2}>周三</option>
                    <option value={3}>周四</option>
                    <option value={4}>周五</option>
                    <option value={5}>周六</option>
                    <option value={6}>周日</option>
                  </select>
                </Field>
              ) : schedule.frequency === "CUSTOM" ||
                schedule.frequency === "YEARLY" ? (
                <Field
                  label={
                    schedule.frequency === "YEARLY"
                      ? "年度日期（仅月日生效）"
                      : "指定日期"
                  }
                >
                  <input
                    type="date"
                    value={schedule.custom_date}
                    onChange={(e) =>
                      setSchedule({ ...schedule, custom_date: e.target.value })
                    }
                    required
                  />
                </Field>
              ) : (
                <Field label="每期日期">
                  <input
                    type="number"
                    min="1"
                    max="31"
                    value={schedule.day_of_month}
                    onChange={(e) =>
                      setSchedule({
                        ...schedule,
                        day_of_month: Number(e.target.value),
                      })
                    }
                  />
                </Field>
              )}
              <Field label="小时">
                <input
                  type="number"
                  min="0"
                  max="23"
                  value={schedule.hour}
                  onChange={(e) =>
                    setSchedule({ ...schedule, hour: Number(e.target.value) })
                  }
                />
              </Field>
              <Field label="分钟">
                <input
                  type="number"
                  min="0"
                  max="59"
                  value={schedule.minute}
                  onChange={(e) =>
                    setSchedule({ ...schedule, minute: Number(e.target.value) })
                  }
                />
              </Field>
              <Field label="提前提醒（天）">
                <input
                  type="number"
                  min="0"
                  max="30"
                  value={schedule.remind_before_days}
                  onChange={(e) =>
                    setSchedule({
                      ...schedule,
                      remind_before_days: Number(e.target.value),
                    })
                  }
                />
              </Field>
              <Field label="逾期重复（天）" hint="设为 0 表示到期后不重复">
                <input
                  type="number"
                  min="0"
                  max="30"
                  value={schedule.repeat_overdue_days}
                  onChange={(e) =>
                    setSchedule({
                      ...schedule,
                      repeat_overdue_days: Number(e.target.value),
                    })
                  }
                />
              </Field>
              <Field label="通知">
                <label className="switch-line">
                  <input
                    type="checkbox"
                    checked={schedule.email_enabled}
                    onChange={(e) =>
                      setSchedule({
                        ...schedule,
                        email_enabled: e.target.checked,
                      })
                    }
                  />
                  <span>邮件提醒（需 SMTP）</span>
                </label>
              </Field>
              <Field label="状态">
                <label className="switch-line">
                  <input
                    type="checkbox"
                    checked={schedule.paused}
                    onChange={(e) =>
                      setSchedule({ ...schedule, paused: e.target.checked })
                    }
                  />
                  <span>暂停当前计划</span>
                </label>
              </Field>
            </div>
          </Card>
          <Card className="card-pad settings-section" id="market">
            <div className="card-head">
              <div className="card-title-row">
                <div className="card-icon">
                  <Server />
                </div>
                <div>
                  <h2>汇率与黄金报价</h2>
                  <p>每个价格都会带上来源和时间，用到旧报价时也会先告诉你。</p>
                </div>
              </div>
              <Button variant="secondary" onClick={() => setQuoteOpen(true)}>
                <Plus />
                录入黄金报价
              </Button>
            </div>
            <div className="market-source">
              <div>
                <Server />
                <div>
                  <strong>汇率</strong>
                  <span>
                    {data.providers.fx.provider} · 最大时效{" "}
                    {data.providers.fx.max_age_hours} 小时
                  </span>
                </div>
                <Badge tone="purple">实时接口</Badge>
              </div>
              <div>
                <Sparkles />
                <div>
                  <strong>黄金</strong>
                  <span>{data.providers.gold.message}</span>
                </div>
                <Badge tone="warning">由你维护</Badge>
              </div>
            </div>
            {quotes.length ? (
              <div className="quote-list">
                {quotes.slice(0, 6).map((q) => (
                  <div key={q.id}>
                    <Badge tone="info">{q.method}</Badge>
                    <div>
                      <strong>
                        ¥{Number(q.price_per_gram_cny).toLocaleString()} / 克
                      </strong>
                      <span>
                        {q.source} · {formatDate(q.quoted_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </Card>
          <Card className="card-pad settings-section" id="devices">
            <div className="card-head">
              <div className="card-title-row">
                <div className="card-icon">
                  <Laptop />
                </div>
                <div>
                  <h2>可信设备与会话</h2>
                  <p>看到不熟悉的设备时，可以让它立即退出。</p>
                </div>
              </div>
            </div>
            <div className="device-list">
              {devices.map((d) => (
                <div key={d.id}>
                  <div className="device-icon">
                    {d.user_agent.includes("Mobile") ? (
                      <Smartphone />
                    ) : (
                      <Laptop />
                    )}
                  </div>
                  <div>
                    <strong>{d.device_name}</strong>
                    <span>
                      最近活动 {formatDate(d.last_seen_at)} · 到期{" "}
                      {formatDate(d.expires_at)}
                    </span>
                  </div>
                  <Badge tone={d.revoked_at ? "neutral" : "purple"}>
                    {d.revoked_at ? "已撤销" : "有效"}
                  </Badge>
                  {!d.revoked_at ? (
                    <Button variant="ghost" onClick={() => revoke(d.id)}>
                      退出
                    </Button>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
      <Modal
        open={quoteOpen}
        onClose={() => setQuoteOpen(false)}
        title="录入可追溯黄金报价"
      >
        <form onSubmit={addQuote}>
          <div className="form-grid">
            <Field label="估值口径">
              <select
                value={quote.method}
                onChange={(e) => setQuote({ ...quote, method: e.target.value })}
              >
                <option value="INTERNATIONAL">国际金价人民币克价</option>
                <option value="DOMESTIC_BENCHMARK">国内黄金基准</option>
                <option value="STORE_BUYBACK">金店回收参考价</option>
              </select>
            </Field>
            <Field label="人民币 / 克">
              <input
                inputMode="decimal"
                value={quote.price_per_gram_cny}
                onChange={(e) =>
                  setQuote({ ...quote, price_per_gram_cny: e.target.value })
                }
                required
              />
            </Field>
            <Field label="来源">
              <input
                value={quote.source}
                onChange={(e) => setQuote({ ...quote, source: e.target.value })}
                placeholder="供应商或门店名称"
                required
              />
            </Field>
            <Field label="报价时间">
              <input
                type="datetime-local"
                value={quote.quoted_at}
                onChange={(e) =>
                  setQuote({ ...quote, quoted_at: e.target.value })
                }
                required
              />
            </Field>
            <Field label="品牌（可选）">
              <input
                value={quote.brand}
                onChange={(e) => setQuote({ ...quote, brand: e.target.value })}
              />
            </Field>
            <Field label="城市（可选）">
              <input
                value={quote.city}
                onChange={(e) => setQuote({ ...quote, city: e.target.value })}
              />
            </Field>
          </div>
          <div className="form-actions">
            <Button
              variant="ghost"
              type="button"
              onClick={() => setQuoteOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" loading={saving}>保存报价</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
function Provider({
  name,
  status,
  detail,
}: {
  name: string;
  status: ProviderStatus;
  detail: string;
}) {
  const ready = status === "available";
  const label: Record<ProviderStatus, string> = {
    available: "可用",
    configured: "已配置，待验证",
    quota: "已配置，额度不足",
    region_blocked: "地区未启用",
    unreachable: "网关不可达",
    unconfigured: "未配置",
  };
  return (
    <div>
      <div className={`provider-light ${ready ? "ready" : ""}`}>
        <i />
      </div>
      <div>
        <strong>{name}</strong>
        <span>{detail}</span>
      </div>
      <Badge tone={ready ? "purple" : "warning"}>{label[status]}</Badge>
    </div>
  );
}

type ProviderStatus =
  | "available"
  | "configured"
  | "quota"
  | "region_blocked"
  | "unreachable"
  | "unconfigured";

function openAIStatus(openai: Settings["providers"]["openai"]): ProviderStatus {
  if (!openai.gateway_reachable) return "unreachable";
  if (!openai.configured) return "unconfigured";
  if (!openai.region_allowed) return "region_blocked";
  if (openai.upstream_available === true) return "available";
  if (openai.error_code === "insufficient_quota") return "quota";
  return "configured";
}
function TotpSetup() {
  const [setup, setSetup] = useState<{
      secret: string;
      provisioning_uri: string;
    } | null>(null),
    [qr, setQr] = useState(""),
    [code, setCode] = useState(""),
    [codes, setCodes] = useState<string[]>([]),
    [enabled, setEnabled] = useState<boolean | null>(null),
    [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api<Me>("/auth/me")
      .then((me) => {
        if (active) setEnabled(me.totp_enabled);
      })
      .catch((caught) => {
        if (active) setError(errorMessage(caught));
      });
    return () => {
      active = false;
    };
  }, []);

  async function begin() {
    if (enabled) return;
    setError("");
    try {
      const s = await api<{ secret: string; provisioning_uri: string }>(
        "/auth/totp/setup",
        { method: "POST" },
      );
      setSetup(s);
      setQr(
        await QRCode.toDataURL(s.provisioning_uri, {
          width: 220,
          margin: 1,
          color: { dark: "#24102f", light: "#ffffff" },
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  async function verify() {
    setError("");
    try {
      const r = await api<{ recovery_codes: string[] }>("/auth/totp/verify", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      setCodes(r.recovery_codes);
      setSetup(null);
      setEnabled(true);
      window.dispatchEvent(
        new CustomEvent("totp-status-changed", { detail: { enabled: true } }),
      );
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  if (codes.length)
    return (
      <div className="recovery-codes">
        <div className="recovery-warning">
          <KeyRound />
          <div>
            <strong>把恢复码放在一个安全的地方</strong>
            <span>它们只出现这一次。建议写下来或放进可信的密码管理器。</span>
          </div>
        </div>
        <div>
          {codes.map((x) => (
            <code key={x}>{x}</code>
          ))}
        </div>
        <Button
          variant="secondary"
          onClick={() => navigator.clipboard.writeText(codes.join("\n"))}
        >
          <Copy />
          复制全部
        </Button>
      </div>
    );
  if (setup)
    return (
      <div className="totp-setup">
        <Image src={qr} alt="TOTP 二维码" width={220} height={220} unoptimized />
        <div>
          <strong>用验证器扫描</strong>
          <p>用常用的验证器扫一扫就好；如果不方便扫描，也可以手工输入下面这串字符：</p>
          <code>{setup.secret}</code>
          <Field label="6 位动态验证码">
            <input
              value={code}
              onChange={(e) =>
                setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
              }
              inputMode="numeric"
            />
          </Field>
          <Button onClick={verify} disabled={code.length !== 6}>
            <Check />
            验证并启用
          </Button>
          {error ? <span className="danger-text">{error}</span> : null}
        </div>
      </div>
    );
  if (enabled === null)
    return error ? (
      <div className="totp-idle">
        <div>
          <ShieldCheck />
          <div>
            <strong>暂时无法读取双重验证状态</strong>
            <span>{error}</span>
          </div>
        </div>
        <Button variant="secondary" onClick={() => window.location.reload()}>
          重新读取
        </Button>
      </div>
    ) : (
      <Skeleton height={78} />
    );
  if (enabled)
    return (
      <div className="totp-idle">
        <div>
          <ShieldCheck />
          <div>
            <strong>双重验证已启用</strong>
            <span>服务器已保存绑定状态；刷新页面或重新登录后仍会保持启用。</span>
          </div>
        </div>
        <Badge tone="info">已启用</Badge>
      </div>
    );
  return (
    <div className="totp-idle">
      <div>
        <ShieldCheck />
        <div>
          <strong>设置动态验证码</strong>
          <span>
            绑定后，登录时除了密码还要输入手机验证器里的动态码，账号会更安心。
          </span>
        </div>
      </div>
      <Button variant="secondary" onClick={begin}>
        <KeyRound />
        开始绑定
      </Button>
      {error ? <span className="danger-text">{error}</span> : null}
    </div>
  );
}
export default function SettingsPage() {
  return (
    <Protected>
      <SettingsContent />
    </Protected>
  );
}
