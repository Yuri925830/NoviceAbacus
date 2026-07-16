"use client";

import { Protected } from "@/components/app-shell";
import {
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Modal,
  Skeleton,
} from "@/components/ui";
import { api, apiUrl, errorMessage, formatDate } from "@/lib/api";
import {
  Archive,
  Bell,
  Check,
  Download,
  FileCheck2,
  HardDriveDownload,
  ImageOff,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type Backup = {
  id: string;
  file_name: string;
  sha256: string;
  size_bytes: number;
  status: string;
  created_at: string;
};
type Audit = {
  id: string;
  event: string;
  severity: string;
  metadata: Record<string, unknown>;
  created_at: string;
};
type Notice = {
  id: string;
  kind: string;
  title: string;
  body: string;
  goal_id?: string | null;
  read_at?: string;
  created_at: string;
};
type Images = {
  all_recent_deleted: boolean;
  records: Array<{
    id: string;
    filename: string;
    size_bytes: number;
    status: string;
    created_at: string;
    deleted_at?: string;
  }>;
};

function DataContent() {
  const [backups, setBackups] = useState<Backup[] | null>(null);
  const [audits, setAudits] = useState<Audit[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [images, setImages] = useState<Images | null>(null);
  const [loading, setLoading] = useState(false);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [restoreId, setRestoreId] = useState<string | null>(null);
  const [auth, setAuth] = useState({ password: "", totp_code: "" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const router = useRouter();

  async function load() {
    setError("");
    try {
      const [backupRows, auditRows, noticeRows, imageRows] = await Promise.all([
        api<Backup[]>("/backups"),
        api<Audit[]>("/audit?limit=50"),
        api<Notice[]>("/notifications"),
        api<Images>("/images/deletion-status"),
      ]);
      setBackups(backupRows);
      setAudits(auditRows);
      setNotices(noticeRows);
      setImages(imageRows);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function createBackup() {
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await api("/backups", { method: "POST" });
      setSuccess("加密备份已创建并完成 SHA-256 完整性记录。");
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  async function markRead(id: string) {
    setError("");
    try {
      await api(`/notifications/${id}/read`, { method: "POST" });
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function restore(event: FormEvent) {
    event.preventDefault();
    if (
      !restoreId ||
      !confirm("最后确认：当前财务数据将被此备份替换，账号与安全会话不变。")
    )
      return;
    setLoading(true);
    setError("");
    setSuccess("");
    try {
      await api(`/backups/${restoreId}/restore`, {
        method: "POST",
        body: JSON.stringify(auth),
      });
      setRestoreId(null);
      setAuth({ password: "", totp_code: "" });
      setSuccess("备份已恢复，清算、目标、设置和审计记录均已重新载入。");
      await load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  async function purge(event: FormEvent) {
    event.preventDefault();
    if (
      !confirm(
        "最后确认：此操作会清除所有财务快照、趋势、目标、报价和本地加密备份。",
      )
    )
      return;
    setLoading(true);
    setError("");
    try {
      await api("/data/purge", { method: "POST", body: JSON.stringify(auth) });
      setPurgeOpen(false);
      router.push("/dashboard");
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  if (!backups && error) return <Card className="card-pad"><Empty title="暂时无法读取数据与安全状态" body={error} action={<Button onClick={load}>重新加载</Button>} /></Card>;
  if (!backups)
    return (
      <>
        <div className="page-head">
          <div>
            <div className="eyebrow">DATA SOVEREIGNTY</div>
            <h1>数据与安全</h1>
          </div>
        </div>
        <Skeleton height={410} />
      </>
    );

  return (
    <>
      <div className="page-head">
        <div>
          <div className="eyebrow">DATA SOVEREIGNTY</div>
          <h1>数据与安全</h1>
          <p>想留一份备份、换设备恢复，或整理旧数据，都可以在这里完成。</p>
        </div>
        <div className="page-actions">
          <Button variant="secondary" onClick={load}>
            <RefreshCw />
            刷新状态
          </Button>
          <Button loading={loading} onClick={createBackup}>
            <Archive />
            创建加密备份
          </Button>
        </div>
      </div>
      <Card className="data-vault-banner">
        <div>
          <Badge tone="purple">怀特 · 数据安全</Badge>
          <h2>给重要的数据留一份安心的备份。</h2>
          <p>每份备份都会加密并检查完整性，需要时可以稳稳地恢复回来。</p>
        </div>
      </Card>
      {error ? <div className="inline-error">{error}</div> : null}
      {success ? <div className="inline-message">{success}</div> : null}
      <div className="section-grid">
        <Card className="card-pad col-7">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <HardDriveDownload />
              </div>
              <div>
                <h2>加密备份</h2>
                <p>资产、目标和设置会打包加密，同时留下完整性校验记录。</p>
              </div>
            </div>
            <Badge tone="purple">应用层加密</Badge>
          </div>
          {backups.length ? (
            <div className="backup-list">
              {backups.map((row) => (
                <div key={row.id}>
                  <div className="backup-icon">
                    <Archive />
                  </div>
                  <div>
                    <strong>{row.file_name}</strong>
                    <span>
                      {formatDate(row.created_at)} ·{" "}
                      {(row.size_bytes / 1024).toFixed(1)} KB
                    </span>
                    <code>{row.sha256.slice(0, 18)}…</code>
                  </div>
                  <Badge
                    tone={row.status === "AVAILABLE" ? "purple" : "danger"}
                  >
                    {row.status}
                  </Badge>
                  <div className="backup-actions">
                    <Button
                      variant="secondary"
                      disabled={row.status !== "AVAILABLE"}
                      onClick={() => setRestoreId(row.id)}
                    >
                      <RotateCcw />
                      恢复
                    </Button>
                    <a
                      className="button button-secondary"
                      href={apiUrl(`/backups/${row.id}/download`)}
                    >
                      <Download />
                      下载
                    </a>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              title="还没有备份"
              body="点一下“创建加密备份”，就能给现在的资产快照、目标和设置留一份副本。"
            />
          )}
        </Card>
        <Card className="card-pad col-5">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <ImageOff />
              </div>
              <div>
                <h2>截图删除状态</h2>
                <p>这里可以看看最近几次图片识别是否已经收尾。</p>
              </div>
            </div>
          </div>
          <div
            className={`deletion-status ${images?.all_recent_deleted ? "ok" : "alert"}`}
          >
            {images?.all_recent_deleted ? <ShieldCheck /> : <ShieldAlert />}
            <div>
              <strong>
                {images?.all_recent_deleted
                  ? "最近图片均已删除"
                  : "存在待处理图片"}
              </strong>
              <span>{images?.records.length || 0} 条最近记录</span>
            </div>
          </div>
          <div className="deletion-list">
            {images?.records.slice(0, 5).map((row) => (
              <div key={row.id}>
                <span>{row.filename}</span>
                <Badge tone={row.status === "DELETED" ? "purple" : "warning"}>
                  {row.status}
                </Badge>
              </div>
            ))}
          </div>
          <p className="privacy-fineprint">
            图片只在内存中完成识别，任务结束立即释放；数据库仅保留哈希、大小与删除审计，不保存图片内容。
          </p>
        </Card>
        <Card className="card-pad col-7">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <Bell />
              </div>
              <div>
                <h2>站内通知</h2>
                <p>清算快到时间，或备份遇到问题时，会在这里提醒你。</p>
              </div>
            </div>
          </div>
          {notices.length ? (
            <div className="notice-list">
              {notices.map((notice) => (
                <button
                  key={notice.id}
                  className={notice.read_at ? "read" : ""}
                  onClick={() => notice.goal_id ? router.push(`/goals?goal=${notice.goal_id}`) : !notice.read_at && markRead(notice.id)}
                >
                  <span>{notice.read_at ? <Check /> : <Bell />}</span>
                  <div>
                    <strong>{notice.title}</strong>
                    <p>{notice.body}</p>
                    <small>{formatDate(notice.created_at)}</small>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <Empty
              title="暂时没有通知"
              body="现在没有需要操心的事情。有新的清算提醒或备份消息时，我会放在这里。"
            />
          )}
        </Card>
        <Card className="card-pad col-5">
          <div className="card-head">
            <div className="card-title-row">
              <div className="card-icon">
                <FileCheck2 />
              </div>
              <div>
                <h2>最近审计</h2>
                <p>只留下登录、设置和数据操作的时间线，敏感内容不会写进记录。</p>
              </div>
            </div>
          </div>
          <div className="audit-list">
            {audits.slice(0, 12).map((row) => (
              <div key={row.id}>
                <i className={`audit-${row.severity.toLowerCase()}`} />
                <div>
                  <strong>{auditLabel(row.event)}</strong>
                  <span>{formatDate(row.created_at)}</span>
                </div>
                <Badge
                  tone={
                    row.severity === "HIGH"
                      ? "danger"
                      : row.severity === "WARNING"
                        ? "warning"
                        : "neutral"
                  }
                >
                  {row.severity}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
        <Card className="danger-zone col-12">
          <div>
            <ShieldAlert />
            <div>
              <h2>清理财务数据</h2>
              <p>
                如果你决定重新开始，这里可以清空财务数据。提交前会再次验证身份，避免误触。
              </p>
            </div>
          </div>
          <Button variant="danger" onClick={() => setPurgeOpen(true)}>
            <Trash2 />
            清除全部财务数据
          </Button>
        </Card>
      </div>

      <Modal
        open={Boolean(restoreId)}
        onClose={() => setRestoreId(null)}
        title="二次验证并恢复备份"
      >
        <div className="purge-warning">
          <RotateCcw />
          <div>
            <strong>恢复前，再确认一次</strong>
            <p>
              这份备份会替换现在的资产、目标和设置；账号、密码、动态验证和已登录设备不会受影响。确认完整无误后，系统才会正式恢复。
            </p>
          </div>
        </div>
        <ReauthForm
          auth={auth}
          setAuth={setAuth}
          loading={loading}
          onSubmit={restore}
          submitLabel="确认恢复"
          icon={<RotateCcw />}
          onCancel={() => setRestoreId(null)}
        />
      </Modal>
      <Modal
        open={purgeOpen}
        onClose={() => setPurgeOpen(false)}
        title="二次验证并清除全部数据"
      >
        <div className="purge-warning">
          <ShieldAlert />
          <div>
            <strong>清空后无法撤回</strong>
            <p>
              清算、资产、目标、报价、事件、通知和本机备份都会被清空。如果还有想留下的内容，请先创建并下载一份备份。
            </p>
          </div>
        </div>
        <ReauthForm
          auth={auth}
          setAuth={setAuth}
          loading={loading}
          onSubmit={purge}
          submitLabel="永久清除"
          icon={<Trash2 />}
          danger
          onCancel={() => setPurgeOpen(false)}
        />
      </Modal>
    </>
  );
}

function ReauthForm({
  auth,
  setAuth,
  loading,
  onSubmit,
  submitLabel,
  icon,
  danger = false,
  onCancel,
}: {
  auth: { password: string; totp_code: string };
  setAuth: (value: { password: string; totp_code: string }) => void;
  loading: boolean;
  onSubmit: (event: FormEvent) => void;
  submitLabel: string;
  icon: React.ReactNode;
  danger?: boolean;
  onCancel: () => void;
}) {
  return (
    <form onSubmit={onSubmit}>
      <div className="form-grid">
        <Field label="当前密码">
          <input
            type="password"
            value={auth.password}
            onChange={(event) =>
              setAuth({ ...auth, password: event.target.value })
            }
            required
          />
        </Field>
        <Field label="TOTP 动态验证码" hint="尚未启用 TOTP 时可留空">
          <input
            inputMode="numeric"
            value={auth.totp_code}
            onChange={(event) =>
              setAuth({
                ...auth,
                totp_code: event.target.value.replace(/\D/g, "").slice(0, 6),
              })
            }
          />
        </Field>
      </div>
      <div className="form-actions">
        <Button variant="ghost" type="button" onClick={onCancel}>
          取消
        </Button>
        <Button
          variant={danger ? "danger" : "primary"}
          loading={loading}
          type="submit"
        >
          {icon}
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

function auditLabel(value: string) {
  return (
    (
      {
        LOGIN_SUCCEEDED: "登录成功",
        LOGIN_FAILED: "登录失败",
        LOGOUT: "退出登录",
        TOTP_ENABLED: "已启用双重验证",
        CLEARING_STARTED: "开始清算",
        SCREENSHOT_RECOGNIZED: "截图识别完成",
        CLEARING_CONFIRMED: "清算已确认",
        CLEARING_DELETED: "清算已删除",
        MODEL_QWEN_CALL: "千问模型调用",
        MODEL_OPENAI_CALL: "OpenAI 模型调用",
        DATA_EXPORTED: "导出数据",
        BACKUP_CREATED: "创建加密备份",
        BACKUP_DOWNLOADED: "下载备份",
        BACKUP_RESTORED: "恢复加密备份",
        BACKUP_RESTORE_FAILED: "备份恢复失败",
        OWNER_SETTINGS_UPDATED: "更新设置",
      } as Record<string, string>
    )[value] || value
  );
}

export default function DataPage() {
  return (
    <Protected>
      <DataContent />
    </Protected>
  );
}
