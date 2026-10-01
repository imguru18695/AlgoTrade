const ICONS = {
  dashboard: <><rect x="3" y="3" width="7.5" height="7.5" rx="1.6"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.6"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.6"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.6"/></>,
  management: <><path d="M12 3 20 7.5 12 12 4 7.5 Z"/><path d="M4 12 12 16.5 20 12"/><path d="M4 16.5 12 21 20 16.5"/></>,
  logs: <><circle cx="4.5" cy="6" r="1.1"/><circle cx="4.5" cy="12" r="1.1"/><circle cx="4.5" cy="18" r="1.1"/><line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/></>,
  strategy: <><line x1="6.5" y1="3.5" x2="6.5" y2="20.5"/><rect x="4" y="8" width="5" height="7" rx="1"/><line x1="17.5" y1="3.5" x2="17.5" y2="20.5"/><rect x="15" y="6" width="5" height="8" rx="1"/></>,
  execution: <path d="M13 2.5 5.5 13 H11 L10 21.5 18.5 10.5 H12.5 L13 2.5 Z"/>,
  pnl: <><path d="M4 16 9.5 10 13.5 14 20 6.5"/><path d="M14.5 6.5 H20 V12"/></>,
  basket: <><path d="M4.5 9.5 H19.5 L17.8 20 H6.2 Z"/><path d="M8.5 9.5 9.3 4.5 H14.7 L15.5 9.5"/></>,
  positions: <><circle cx="12" cy="12" r="8.2"/><circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none"/></>,
  warning: <><path d="M12 3.3 21 19.8 H3 Z"/><line x1="12" y1="9.7" x2="12" y2="14.2"/><circle cx="12" cy="17" r="1" fill="currentColor" stroke="none"/></>,
  notepad: <><path d="M6 2.5h9l3 3v16a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-18a1 1 0 0 1 1-1z"/><path d="M15 2.5v3h3"/><line x1="7.5" y1="10.5" x2="16.5" y2="10.5"/><line x1="7.5" y1="14" x2="16.5" y2="14"/><line x1="7.5" y1="17.5" x2="13.5" y2="17.5"/></>,
}

export function Icon({ name, size = 18 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      {ICONS[name]}
    </svg>
  )
}
