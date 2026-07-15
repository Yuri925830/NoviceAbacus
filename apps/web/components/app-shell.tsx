"use client";
import { api } from "@/lib/api";
import type { Me } from "@/lib/types";
import { usePrivacy } from "./providers";
import {
  Bell,
  BatteryCharging,
  Bot,
  CalendarCheck,
  ChartCandlestick,
  CircleUserRound,
  Database,
  Eye,
  EyeOff,
  LayoutDashboard,
  Orbit,
  Scale,
  ScanSearch,
  BookOpenCheck,
  LogOut,
  Menu,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
  WalletCards,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

const navGroups = [
  {
    label: "现在先看这里",
    items: [
      { href: "/dashboard", label: "我的财务首页", icon: LayoutDashboard },
      { href: "/spending", label: "放心花", icon: BatteryCharging },
      { href: "/assistant", label: "问怀特", icon: Bot },
    ],
  },
  {
    label: "我的钱",
    items: [
      { href: "/clearing", label: "资产清算", icon: CalendarCheck },
      { href: "/assets", label: "资产明细", icon: WalletCards },
      { href: "/trend", label: "资产变化", icon: ChartCandlestick },
    ],
  },
  {
    label: "往前走",
    items: [
      { href: "/goals", label: "财务目标", icon: Target },
      { href: "/intelligence", label: "怀特决策舱", icon: Orbit },
    ],
  },
  {
    label: "安心守护",
    items: [
      { href: "/funding", label: "每笔钱的用途", icon: Scale },
      { href: "/constitution", label: "我的理财规则", icon: BookOpenCheck },
      { href: "/xray", label: "看懂理财产品", icon: ScanSearch },
    ],
  },
];
const utilityNav = [
  { href: "/data", label: "数据与安全", icon: Database },
  { href: "/settings", label: "系统设置", icon: Settings },
];
const nav = [...navGroups.flatMap((group) => group.items), ...utilityNav];

export function Protected({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api<Me>("/auth/me")
      .then(setMe)
      .catch(() => router.replace("/login"))
      .finally(() => setLoading(false));
  }, [router]);
  if (loading)
    return (
      <div className="app-loading">
        <div className="brand-sigil">
          <Sparkles />
        </div>
        <span>正在打开你的资产底牌…</span>
      </div>
    );
  if (!me) return null;
  return <AppShell me={me}>{children}</AppShell>;
}

function AppShell({ children, me }: { children: React.ReactNode; me: Me }) {
  const pathname = usePathname();
  const router = useRouter();
  const { hidden, toggle } = usePrivacy();
  const [open, setOpen] = useState(false);
  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    router.replace("/login");
  }
  return (
    <div className="app-frame">
      <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
        <div className="sidebar-brand">
          <div className="brand-sigil">
            <Sparkles size={19} />
          </div>
          <div>
            <strong>小白算盘</strong>
            <span>个人资产工作台</span>
          </div>
          <button
            className="sidebar-close"
            onClick={() => setOpen(false)}
            aria-label="关闭菜单"
          >
            <X />
          </button>
        </div>
        <nav className="sidebar-nav">
          {navGroups.map((group) => (
            <div className="sidebar-nav-group" key={group.label}>
              <small>{group.label}</small>
              {group.items.map(({ href, label, icon: Icon }) => (
                <Link
                  href={href}
                  key={href}
                  onClick={() => setOpen(false)}
                  className={pathname.startsWith(href) ? "active" : ""}
                >
                  <Icon size={19} />
                  <span>{label}</span>
                  {href === "/assistant" ? <i>AI</i> : null}
                </Link>
              ))}
            </div>
          ))}
          <div className="sidebar-nav-group sidebar-utility">
            {utilityNav.map(({ href, label, icon: Icon }) => (
              <Link
                href={href}
                key={href}
                onClick={() => setOpen(false)}
                className={pathname.startsWith(href) ? "active" : ""}
              >
                <Icon size={19} />
                <span>{label}</span>
              </Link>
            ))}
          </div>
        </nav>
        <div className="sidebar-foot">
          <ShieldCheck size={18} />
          <div>
            <strong>慢慢理清，也很好</strong>
            <span>你的资产、目标和每一次进步都在这里。</span>
          </div>
        </div>
      </aside>
      {open ? (
        <button
          className="sidebar-scrim"
          onClick={() => setOpen(false)}
          aria-label="关闭菜单"
        />
      ) : null}
      <main className="main-area">
        <header className="topbar">
          <button
            className="menu-button"
            onClick={() => setOpen(true)}
            aria-label="打开菜单"
          >
            <Menu />
          </button>
          <div className="topbar-crumb">
            <span>怀特在线</span>
            <strong>
              {nav.find((x) => pathname.startsWith(x.href))?.label ??
                "小白算盘"}
            </strong>
          </div>
          <div className="topbar-actions">
            <button
              className="top-action"
              onClick={toggle}
              title={hidden ? "显示金额" : "隐藏金额"}
            >
              {hidden ? <Eye size={18} /> : <EyeOff size={18} />}
              <span>{hidden ? "显示金额" : "隐藏金额"}</span>
            </button>
            <Link className="notification-button" href="/data" title="通知">
              <Bell size={19} />
              {me.unread_notifications > 0 ? (
                <b>{Math.min(me.unread_notifications, 99)}</b>
              ) : null}
            </Link>
            <div className="owner-chip">
              <CircleUserRound size={20} />
              <div>
                <strong>我的账号</strong>
                <span>{me.email}</span>
              </div>
            </div>
            <button className="icon-button" onClick={logout} title="退出">
              <LogOut size={19} />
            </button>
          </div>
        </header>
        <div className="page-wrap">
          {me.security_setup_required ? (
            <div className="security-banner">
              <ShieldCheck />
              <div>
                <strong>再添一把安全锁</strong>
                <span>
                  绑定动态验证码后，即使密码意外泄露，账号也多一层保护。
                </span>
              </div>
              <Link href="/settings">现在设置</Link>
            </div>
          ) : null}
          {children}
        </div>
        <nav className="mobile-nav">
          {nav
            .filter((item) =>
              ["/dashboard", "/clearing", "/spending", "/goals", "/assistant"].includes(
                item.href,
              ),
            )
            .map(({ href, label, icon: Icon }) => (
            <Link
              href={href}
              key={href}
              className={pathname.startsWith(href) ? "active" : ""}
            >
              <Icon />
              <span>{({
                "/dashboard": "首页",
                "/clearing": "清算",
                "/spending": "放心花",
                "/goals": "目标",
                "/assistant": "问怀特",
              } as Record<string, string>)[href] || label}</span>
            </Link>
            ))}
        </nav>
      </main>
    </div>
  );
}
