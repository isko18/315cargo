// Единый набор линейных SVG-иконок (стиль Lucide, stroke 1.75).
// Никаких эмодзи в структурных элементах — иконки управляются через currentColor.
import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 20, children, ...rest }: P & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconScan = (p: P) => (
  <Svg {...p}>
    <path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" />
    <path d="M7 8v8M10 8v8M13 8v8M17 8v8" />
  </Svg>
);

export const IconIssue = (p: P) => (
  <Svg {...p}>
    <path d="M21 8v8a2 2 0 0 1-1 1.73l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8a2 2 0 0 1 1-1.73l7-4a2 2 0 0 1 2 0l7 4" />
    <path d="m9 12 2 2 4-4" />
  </Svg>
);

export const IconStaff = (p: P) => (
  <Svg {...p}>
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
  </Svg>
);

export const IconTariff = (p: P) => (
  <Svg {...p}>
    <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
  </Svg>
);

export const IconAnalytics = (p: P) => (
  <Svg {...p}>
    <path d="M3 3v18h18" />
    <rect x="7" y="12" width="3" height="6" rx="0.5" />
    <rect x="12" y="8" width="3" height="10" rx="0.5" />
    <rect x="17" y="5" width="3" height="13" rx="0.5" />
  </Svg>
);

export const IconOverview = (p: P) => (
  <Svg {...p}>
    <path d="M3 21h18M6 21V9l6-4 6 4v12" />
    <path d="M9 21v-6h6v6M9.5 12h.01M14 12h.01" />
  </Svg>
);

export const IconLogout = (p: P) => (
  <Svg {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
  </Svg>
);

export const IconMenu = (p: P) => (
  <Svg {...p}>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </Svg>
);

export const IconClose = (p: P) => (
  <Svg {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Svg>
);

export const IconSearch = (p: P) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m21 21-4.3-4.3" />
  </Svg>
);

export const IconCamera = (p: P) => (
  <Svg {...p}>
    <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3Z" />
    <circle cx="12" cy="13" r="3.5" />
  </Svg>
);

export const IconPlus = (p: P) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const IconCheck = (p: P) => (
  <Svg {...p}>
    <path d="M20 6 9 17l-5-5" />
  </Svg>
);

export const IconAlert = (p: P) => (
  <Svg {...p}>
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" />
    <path d="M12 9v4M12 17h.01" />
  </Svg>
);

export const IconBox = (p: P) => (
  <Svg {...p}>
    <path d="M21 8v8a2 2 0 0 1-1 1.73l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8a2 2 0 0 1 1-1.73l7-4a2 2 0 0 1 2 0l7 4A2 2 0 0 1 21 8Z" />
    <path d="m3.3 7 8.7 5 8.7-5M12 22V12" />
  </Svg>
);

export const IconRevenue = (p: P) => (
  <Svg {...p}>
    <path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
  </Svg>
);

export const IconWeight = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="5" r="2.5" />
    <path d="M6.5 9h11l2.5 11H4L6.5 9Z" />
  </Svg>
);

export const IconDownload = (p: P) => (
  <Svg {...p}>
    <path d="M12 3v12M7 10l5 5 5-5M5 21h14" />
  </Svg>
);

export const IconSort = (p: P) => (
  <Svg {...p}>
    <path d="m8 9 4-4 4 4M16 15l-4 4-4-4" />
  </Svg>
);

export const IconSortAsc = (p: P) => (
  <Svg {...p}>
    <path d="m12 5 5 6H7l5-6Z" />
  </Svg>
);

export const IconSortDesc = (p: P) => (
  <Svg {...p}>
    <path d="m12 19 5-6H7l5 6Z" />
  </Svg>
);

export const IconGlobe = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c2.5 2.6 3.8 5.7 3.8 9S14.5 18.4 12 21c-2.5-2.6-3.8-5.7-3.8-9S9.5 5.6 12 3Z" />
  </Svg>
);

export const IconWarehouse = (p: P) => (
  <Svg {...p}>
    <path d="M3 21V8l9-5 9 5v13" />
    <path d="M3 21h18M7 21v-7h10v7M7 14h10" />
  </Svg>
);

export const IconFilter = (p: P) => (
  <Svg {...p}>
    <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3Z" />
  </Svg>
);

export const IconTruck = (p: P) => (
  <Svg {...p}>
    <path d="M14 17V5a1 1 0 0 0-1-1H2a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h1" />
    <path d="M14 8h4l3 3v5a1 1 0 0 1-1 1h-1" />
    <circle cx="6.5" cy="17.5" r="1.5" />
    <circle cx="17.5" cy="17.5" r="1.5" />
  </Svg>
);

export const IconPin = (p: P) => (
  <Svg {...p}>
    <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0" />
    <circle cx="12" cy="10" r="3" />
  </Svg>
);

export const IconSidebar = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M9 4v16" />
  </Svg>
);

export const IconHistory = (p: P) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 3v5h5" />
    <path d="M12 7v5l3 2" />
  </Svg>
);

export const IconEye = (p: P) => (
  <Svg {...p}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);

export const IconEyeOff = (p: P) => (
  <Svg {...p}>
    <path d="M9.9 4.24A9.1 9.1 0 0 1 12 4c6.5 0 10 7 10 7a13.2 13.2 0 0 1-2.16 2.94M6.6 6.6A13.3 13.3 0 0 0 2 11s3.5 7 10 7a9.1 9.1 0 0 0 4.5-1.16" />
    <path d="M10 10a3 3 0 0 0 4 4" />
    <path d="m2 2 20 20" />
  </Svg>
);
