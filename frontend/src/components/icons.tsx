import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;
const base = (props: P) => ({
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  ...props,
});

export const LogoMark = (props: P) => (
  <svg viewBox="0 0 24 24" aria-hidden {...props}>
    <rect width="24" height="24" rx="6" fill="var(--color-accent)" />
    <path d="M4 7h4.5c2.2 0 2.9 1.4 3.8 3.6l1.2 3c.7 1.8 1.4 2.4 3 2.4H20" fill="none" stroke="#0a0a0b" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="12.4" cy="10.6" r="1.9" fill="#0a0a0b" />
  </svg>
);

export const IconGrid = (p: P) => (
  <svg {...base(p)}>
    <rect x="4" y="4" width="16" height="16" rx="3" />
    <path d="M4 10h16M10 4v16" />
  </svg>
);
export const IconTimeline = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 6c4 0 5 3 8 6s5 6 10 6" />
    <circle cx="11" cy="12" r="1.6" fill="currentColor" />
  </svg>
);
export const IconSim = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 17l5-6 4 3 8-9" />
    <path d="M3 12c3-1 5 0 8 1s6 1 10-1" strokeDasharray="2 3" />
  </svg>
);
export const IconCheck = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M8 12.5l2.6 2.5L16 9.5" />
  </svg>
);
export const IconPlus = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);
export const IconMinus = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 12h14" />
  </svg>
);
export const IconPlay = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 5.5v13l10.5-6.5z" />
  </svg>
);
export const IconPause = (p: P) => (
  <svg {...base(p)}>
    <path d="M8 5v14M16 5v14" />
  </svg>
);
export const IconBack10 = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 12a8 8 0 108-8H8" />
    <path d="M10 1.8L7.6 4 10 6.2" />
    <text x="12" y="15.2" fontSize="6.5" textAnchor="middle" fill="currentColor" stroke="none" fontFamily="inherit">10</text>
  </svg>
);
export const IconFwd10 = (p: P) => (
  <svg {...base(p)}>
    <path d="M20 12a8 8 0 11-8-8h4" />
    <path d="M14 1.8L16.4 4 14 6.2" />
    <text x="12" y="15.2" fontSize="6.5" textAnchor="middle" fill="currentColor" stroke="none" fontFamily="inherit">10</text>
  </svg>
);
export const IconScissors = (p: P) => (
  <svg {...base(p)}>
    <circle cx="6" cy="6" r="2.6" />
    <circle cx="6" cy="18" r="2.6" />
    <path d="M8.2 7.6L20 17M8.2 16.4L20 7" />
  </svg>
);
export const IconMove = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 8h13M14 4.5L17.5 8 14 11.5M20 16H7M10 12.5L6.5 16 10 19.5" />
  </svg>
);
export const IconShorten = (p: P) => (
  <svg {...base(p)}>
    <path d="M3 12h6M15 12h6M6 9l3 3-3 3M18 9l-3 3 3 3" />
  </svg>
);
export const IconRewrite = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 20h4L19 9a2.8 2.8 0 00-4-4L4 16z" />
  </svg>
);
export const IconHook = (p: P) => (
  <svg {...base(p)}>
    <path d="M13 3L5 13h6l-1 8 8-10h-6z" />
  </svg>
);
export const IconVisual = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="5" width="18" height="14" rx="3" />
    <circle cx="9" cy="10" r="1.8" />
    <path d="M21 16l-5-5-8 8" />
  </svg>
);
export const IconKeep = (p: P) => (
  <svg {...base(p)}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </svg>
);
export const IconExpand = (p: P) => (
  <svg {...base(p)}>
    <path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7" />
  </svg>
);
export const IconChevron = (p: P) => (
  <svg {...base(p)}>
    <path d="M9 6l6 6-6 6" />
  </svg>
);
export const IconClose = (p: P) => (
  <svg {...base(p)}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);
export const IconFile = (p: P) => (
  <svg {...base(p)}>
    <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" />
    <path d="M14 3v5h5M9 13h6M9 17h4" />
  </svg>
);
export const IconLogout = (p: P) => (
  <svg {...base(p)}>
    <path d="M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3M10 16l-4-4 4-4M6 12h10" />
  </svg>
);
export const IconRestart = (p: P) => (
  <svg {...base(p)}>
    <path d="M20 12a8 8 0 11-2.6-5.9" />
    <path d="M20 4v4.5h-4.5" />
  </svg>
);
export const IconDownload = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 4v12M7 11l5 5 5-5M4 18v1a1 1 0 001 1h14a1 1 0 001-1v-1" />
  </svg>
);
export const IconVideo = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="6" width="13" height="12" rx="3" />
    <path d="M16 10.5l5-3v9l-5-3" />
  </svg>
);
export const IconUpload = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 16V4M7 9l5-5 5 5M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
  </svg>
);
