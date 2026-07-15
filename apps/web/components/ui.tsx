"use client";
import { LoaderCircle, X } from "lucide-react";
import { useEffect } from "react";

export function Button({
  children,
  className = "",
  variant = "primary",
  loading = false,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  loading?: boolean;
}) {
  return (
    <button
      className={`button button-${variant} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <LoaderCircle size={17} className="spin" /> : null}
      {children}
    </button>
  );
}
export function Card({
  children,
  className = "",
  ...props
}: React.HTMLAttributes<HTMLElement>) {
  return (
    <section className={`card ${className}`} {...props}>
      {children}
    </section>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "purple" | "danger" | "warning" | "info";
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function Empty({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-orbit" />
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}
export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  if (!open) return null;
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.currentTarget === e.target) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="关闭">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
export function Skeleton({ height = 120 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} />;
}
export function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`field ${className}`.trim()}>
      <span>{label}</span>
      {children}
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}
