import { useEffect, useState } from "react";
import { Icon } from "./Icon";

export function Toast({
  message,
  tone = "info",
  onDone,
}: {
  message: string;
  tone?: "info" | "error";
  onDone: () => void;
}) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, tone === "error" ? 6000 : 3200);
    return () => window.clearTimeout(timer);
  }, [message, tone, onDone]);
  return (
    <div className={`toast ${tone === "error" ? "error" : ""}`} role="status" aria-live="polite">
      {message}
    </div>
  );
}

export function useToast() {
  const [toast, setToast] = useState<{ message: string; tone: "info" | "error" } | null>(null);
  return {
    toast,
    show: (message: string, tone: "info" | "error" = "info") => setToast({ message, tone }),
    node: toast ? (
      <Toast message={toast.message} tone={toast.tone} onDone={() => setToast(null)} />
    ) : null,
  };
}

export function Loading({ label = "正在读取…" }: { label?: string }) {
  return (
    <div className="loading-block">
      <span className="spinner" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: React.ReactNode }) {
  return (
    <div className="empty">
      <b>{title}</b>
      {hint ? <div>{hint}</div> : null}
    </div>
  );
}

export function Notice({
  tone = "info",
  children,
  icon = "info",
}: {
  tone?: "info" | "warn" | "danger" | "good";
  children: React.ReactNode;
  icon?: string;
}) {
  return (
    <div className={`notice notice-${tone}`}>
      <Icon name={icon} className="icon" size={15} />
      <div>{children}</div>
    </div>
  );
}
