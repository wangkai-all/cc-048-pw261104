import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "./api";
import { Icon } from "./Icon";
import type { Ruleset } from "./types";

const NAV = [
  { path: "/", label: "导入换算", icon: "upload" },
  { path: "/batches", label: "批次", icon: "layers" },
  { path: "/rules", label: "规则", icon: "sliders" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const [ruleset, setRuleset] = useState<Ruleset | null>(null);

  useEffect(() => {
    let live = true;
    api
      .get<Ruleset>("/api/rulesets/latest")
      .then((data) => live && setRuleset(data))
      .catch(() => live && setRuleset(null));
    return () => {
      live = false;
    };
  }, [location.pathname]);

  const active = (path: string) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">U</div>
          <div>
            <div className="brand-name">单位换算台</div>
            <div className="brand-sub">精确换算 · 规则留痕</div>
          </div>
        </div>
        <nav className="nav" aria-label="主导航">
          <div className="nav-label">工作区</div>
          {NAV.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item ${active(item.path) ? "active" : ""}`}
              aria-current={active(item.path) ? "page" : undefined}
            >
              <Icon name={item.icon} size={16} className="icon" />
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-foot">
          {ruleset ? (
            <div className="version-chip" title={`规则集 ${ruleset.name}`}>
              <Icon name="lock" size={13} />
              <span>
                规则 <b>v{ruleset.version}</b>
              </span>
            </div>
          ) : (
            <div className="version-chip">
              <Icon name="alert" size={13} />
              <span>尚无规则</span>
            </div>
          )}
          <div className="muted" style={{ fontSize: 11, paddingLeft: 2 }}>
            Decimal / 有理数计算<br />
            舍入只在输出时发生
          </div>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}

export function PageHead({
  eyebrow,
  title,
  sub,
  actions,
}: {
  eyebrow?: string;
  title: React.ReactNode;
  sub?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h1>{title}</h1>
        {sub ? <div className="sub">{sub}</div> : null}
      </div>
      {actions ? <div className="row" style={{ flexWrap: "wrap" }}>{actions}</div> : null}
    </div>
  );
}

export function useDebounced<T>(value: T, delay = 280) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useOnEscape(handler: () => void) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") ref.current();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);
}
