"use client";
import { api, ApiError, errorMessage } from "@/lib/api";
import { Button, Field } from "@/components/ui";
import {
  ArrowRight,
  KeyRound,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/auth/me")
      .then(() => router.replace("/dashboard"))
      .catch(() => {});
  }, [router]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          identifier,
          password,
          totp_code: code || null,
          device_name: navigator.userAgent.includes("Mobile")
            ? "手机浏览器"
            : "电脑浏览器",
        }),
      });
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError && err.status === 428) {
        setNeedsTotp(true);
        setError("请输入验证器中的 6 位动态验证码");
      } else setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }
  return (
    <main className="login-page">
      <section className="login-visual">
        <Image
          src="/brand/huai-te-portrait-v1.webp"
          alt="小白算盘怀特理财顾问"
          fill
          priority
          sizes="(max-width: 900px) 100vw, 58vw"
        />
        <div className="login-visual-overlay" />
        <div className="login-copy">
          <div className="login-mark">
            <Sparkles size={17} /> 小白算盘
          </div>
          <h1>
            把散落的资产，
            <br />
            算成一张清楚的底牌。
          </h1>
          <p>
            怀特会陪你把数字一项项理顺，也会把复杂的理财问题讲得更好懂。
          </p>
        </div>
      </section>
      <section className="login-panel">
        <div className="login-form-wrap">
          <div className="login-brand-mobile">
            <div className="brand-sigil">
              <Sparkles />
            </div>
            <div>
              <strong>小白算盘</strong>
              <span>你的个人资产空间</span>
            </div>
          </div>
          <div className="login-heading">
            <span className="eyebrow">WELCOME BACK</span>
            <h2>欢迎回来</h2>
            <p>很高兴又见到你，今天也可以轻松一点开始。</p>
          </div>
          <form onSubmit={submit} className="login-form">
            <Field label="账号 / 邮箱 / 手机号">
              <div className="input-icon">
                <KeyRound />
                <input
                  autoComplete="username"
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  placeholder="例如 RENSHU"
                  required
                />
              </div>
            </Field>
            <Field label="密码">
              <div className="input-icon">
                <LockKeyhole />
                <input
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="输入密码"
                  required
                />
              </div>
            </Field>
            {needsTotp ? (
              <Field
                label="动态验证码"
                hint="也可在登录 API 中使用一次性恢复码"
              >
                <input
                  className="totp-input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) =>
                    setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                  }
                  placeholder="000 000"
                  autoFocus
                  required
                />
              </Field>
            ) : null}
            {error ? <div className="login-error">{error}</div> : null}
            <Button loading={loading} className="login-submit">
              进入我的资产空间 <ArrowRight size={17} />
            </Button>
          </form>
          <div className="login-security">
            <ShieldCheck />
            <div>
              <strong>安心登录</strong>
              <span>密码和动态验证码只用于验证身份，不会出现在页面记录里。</span>
            </div>
          </div>
          <p className="login-footnote">
            小白算盘提供个人资产整理和教育性分析，不构成持牌投资建议。
          </p>
        </div>
      </section>
    </main>
  );
}
