import type { CSSProperties, ReactNode } from "react";

export function Icon({ name, size = 16, className, style }: { name: string; size?: number; className?: string; style?: CSSProperties }) {
  const paths: Record<string, ReactNode> = {
    upload: (
      <>
        <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
        <path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" />
      </>
    ),
    layers: (
      <>
        <path d="M12 3 3 8l9 5 9-5-9-5Z" />
        <path d="m3 12 9 5 9-5" />
        <path d="m3 16 9 5 9-5" />
      </>
    ),
    sliders: (
      <>
        <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" />
        <circle cx="16" cy="6" r="2" />
        <circle cx="10" cy="12" r="2" />
        <circle cx="18" cy="18" r="2" />
      </>
    ),
    scale: (
      <>
        <path d="M12 3v18M5 7h14" />
        <path d="m5 7-3 6a3 3 0 0 0 6 0L5 7Zm14 0-3 6a3 3 0 0 0 6 0l-3-6Z" />
      </>
    ),
    check: <path d="m4.5 12.5 4.5 4.5L19.5 6.5" />,
    x: <path d="M5 5l14 14M19 5 5 19" />,
    arrow: <path d="M4 12h15m0 0-6-6m6 6-6 6" />,
    chevron: <path d="m8 5 7 7-7 7" />,
    alert: (
      <>
        <path d="M12 3 2.5 20h19L12 3Z" />
        <path d="M12 9.5v4.5M12 17h.01" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v5.5M12 7.5h.01" />
      </>
    ),
    download: (
      <>
        <path d="M12 3v12m0 0 4.5-4.5M12 15l-4.5-4.5" />
        <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
      </>
    ),
    table: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="1.5" />
        <path d="M3 9.5h18M9 9.5V20" />
      </>
    ),
    compare: (
      <>
        <path d="M8 4 4 8l4 4M4 8h9a3 3 0 0 1 3 3v1" />
        <path d="m16 20 4-4-4-4M20 16h-9a3 3 0 0 1-3-3v-1" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5.5l3.5 2" />
      </>
    ),
    file: (
      <>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
        <path d="M14 3v5h5" />
      </>
    ),
    hash: (
      <>
        <path d="M9 3 7 21M17 3l-2 18M4 9h16M3 15h16" />
      </>
    ),
    lock: (
      <>
        <rect x="5" y="10" width="14" height="10" rx="2" />
        <path d="M8.5 10V7a3.5 3.5 0 1 1 7 0v3" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    trash: (
      <>
        <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
      </>
    ),
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m15.5 15.5 4.5 4.5" />
      </>
    ),
    filter: <path d="M3 5h18l-7 8v6l-4-2v-4L3 5Z" />,
    external: (
      <>
        <path d="M14 4h6v6" />
        <path d="M20 4 11 13" />
        <path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 4H10" />
      </>
    ),
    sparkle: (
      <>
        <path d="M12 3.5 13.8 9l5.5 1.8-5.5 1.8L12 18l-1.8-5.4L4.7 10.8 10.2 9 12 3.5Z" />
      </>
    ),
    gauge: (
      <>
        <path d="M4 17a8.5 8.5 0 1 1 16 0" />
        <path d="m12 17 4-5" />
      </>
    ),
  };
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.9}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={style}
    >
      {paths[name] ?? paths.info}
    </svg>
  );
}
