import type { CSSProperties } from 'react';

export type IconName =
  | 'dashboard'
  | 'rates'
  | 'import'
  | 'compare'
  | 'package'
  | 'mail'
  | 'carriers'
  | 'review'
  | 'settings'
  | 'search'
  | 'bell'
  | 'help'
  | 'arrow-right'
  | 'arrow-up'
  | 'arrow-down'
  | 'close'
  | 'filter'
  | 'plus'
  | 'download'
  | 'ship'
  | 'globe'
  | 'trend-up'
  | 'alert'
  | 'check'
  | 'clock'
  | 'eye'
  | 'more'
  | 'trash'
  | 'shield'
  | 'sparkles'
  | 'refresh'
  | 'user'
  | 'logout';

interface IconProps {
  name: IconName;
  size?: number;
  color?: string;
  className?: string;
  style?: CSSProperties;
}

export default function Icon({
  name,
  size = 16,
  color = 'currentColor',
  className,
  style,
}: IconProps) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none' as const,
    stroke: color,
    strokeWidth: 1.5,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    className,
    style,
  };

  switch (name) {
    case 'dashboard':
      return (
        <svg {...common}>
          <rect x="3" y="3" width="7" height="9" rx="1.5" />
          <rect x="14" y="3" width="7" height="5" rx="1.5" />
          <rect x="14" y="12" width="7" height="9" rx="1.5" />
          <rect x="3" y="16" width="7" height="5" rx="1.5" />
        </svg>
      );
    case 'rates':
      return (
        <svg {...common}>
          <path d="M3 6h18M3 12h18M3 18h18" />
          <circle cx="7" cy="6" r="1.5" fill={color} />
          <circle cx="14" cy="12" r="1.5" fill={color} />
          <circle cx="10" cy="18" r="1.5" fill={color} />
        </svg>
      );
    case 'import':
      return (
        <svg {...common}>
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <path d="M7 10l5 5 5-5" />
          <path d="M12 15V3" />
        </svg>
      );
    case 'compare':
      return (
        <svg {...common}>
          <path d="M8 3v18M16 3v18M3 8h5M16 8h5M3 16h5M16 16h5" />
        </svg>
      );
    case 'package':
      return (
        <svg {...common}>
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
          <path d="M3.27 6.96L12 12l8.73-5.04M12 22.08V12" />
        </svg>
      );
    case 'mail':
      return (
        <svg {...common}>
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="M3 7l9 6 9-6" />
        </svg>
      );
    case 'carriers':
      return (
        <svg {...common}>
          <path d="M2 20h20" />
          <path d="M4 20V10l8-4 8 4v10" />
          <path d="M9 20v-6h6v6" />
        </svg>
      );
    case 'review':
      return (
        <svg {...common}>
          <path d="M9 11l3 3L22 4" />
          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
        </svg>
      );
    case 'settings':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      );
    case 'search':
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
      );
    case 'bell':
      return (
        <svg {...common}>
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
      );
    case 'help':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <circle cx="12" cy="17" r=".5" fill={color} />
        </svg>
      );
    case 'arrow-right':
      return (
        <svg {...common}>
          <path d="M5 12h14M13 5l7 7-7 7" />
        </svg>
      );
    case 'arrow-up':
      return (
        <svg {...common}>
          <path d="M12 19V5M5 12l7-7 7 7" />
        </svg>
      );
    case 'arrow-down':
      return (
        <svg {...common}>
          <path d="M12 5v14M19 12l-7 7-7-7" />
        </svg>
      );
    case 'close':
      return (
        <svg {...common}>
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      );
    case 'filter':
      return (
        <svg {...common}>
          <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" />
        </svg>
      );
    case 'plus':
      return (
        <svg {...common}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      );
    case 'download':
      return (
        <svg {...common}>
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <path d="M7 10l5 5 5-5" />
          <path d="M12 15V3" />
        </svg>
      );
    case 'ship':
      return (
        <svg {...common}>
          <path d="M2 20a3 3 0 0 0 5 0 3 3 0 0 0 5 0 3 3 0 0 0 5 0 3 3 0 0 0 5 0" />
          <path d="M3 16l1.5-5h15L21 16" />
          <path d="M12 11V4" />
          <path d="M6 11V7h12v4" />
        </svg>
      );
    case 'globe':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="10" />
          <path d="M2 12h20M12 2a15 15 0 0 1 4 10 15 15 0 0 1-4 10 15 15 0 0 1-4-10 15 15 0 0 1 4-10z" />
        </svg>
      );
    case 'trend-up':
      return (
        <svg {...common}>
          <path d="M23 6l-9.5 9.5-5-5L1 18" />
          <path d="M17 6h6v6" />
        </svg>
      );
    case 'alert':
      return (
        <svg {...common}>
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <path d="M12 9v4M12 17h.01" />
        </svg>
      );
    case 'check':
      return (
        <svg {...common}>
          <path d="M20 6L9 17l-5-5" />
        </svg>
      );
    case 'clock':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
      );
    case 'eye':
      return (
        <svg {...common}>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case 'more':
      return (
        <svg {...common}>
          <circle cx="5" cy="12" r="1" fill={color} />
          <circle cx="12" cy="12" r="1" fill={color} />
          <circle cx="19" cy="12" r="1" fill={color} />
        </svg>
      );
    case 'trash':
      return (
        <svg {...common}>
          <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
        </svg>
      );
    case 'shield':
      return (
        <svg {...common}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      );
    case 'sparkles':
      return (
        <svg {...common}>
          <path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2zM19 14l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM5 14l1 2 2 1-2 1-1 2-1-2-2-1 2-1z" />
        </svg>
      );
    case 'refresh':
      return (
        <svg {...common}>
          <path d="M23 4v6h-6M1 20v-6h6" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
      );
    case 'user':
      return (
        <svg {...common}>
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      );
    case 'logout':
      return (
        <svg {...common}>
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
          <path d="M16 17l5-5-5-5M21 12H9" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <rect x="4" y="4" width="16" height="16" rx="2" />
        </svg>
      );
  }
}
