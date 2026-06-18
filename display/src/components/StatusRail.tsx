import {
  Activity,
  CheckCircle2,
  CircleDot,
  Cog,
  ServerCog,
  TriangleAlert,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import styles from "./StatusRail.module.css";

export type StatusKind = "ok" | "warn" | "down" | "idle";

export type StatusItem = {
  id: string;
  label: string;
  status: string;
  kind: StatusKind;
  icon: LucideIcon;
};

const DEFAULT_ITEMS: StatusItem[] = [
  {
    id: "environment",
    label: "Environment",
    status: "Pending check",
    kind: "idle",
    icon: ServerCog,
  },
  {
    id: "session",
    label: "Session",
    status: "No session",
    kind: "idle",
    icon: Activity,
  },
  {
    id: "process",
    label: "Process",
    status: "Idle",
    kind: "idle",
    icon: Cog,
  },
  {
    id: "logs",
    label: "Logs",
    status: "Not streaming",
    kind: "idle",
    icon: CircleDot,
  },
];

// State indicator shown next to each rail item. Pure color was the only
// differentiator before, which failed WCAG 1.4.1 (color is not the sole
// means of conveying status). Now we pair the kind with a recognizable
// shape so color-blind users and screen-reader users get the same info.
function KindGlyph({ kind }: { kind: StatusKind }) {
  const label =
    kind === "ok" ? "ok" : kind === "warn" ? "warning" : kind === "down" ? "error" : "idle";
  const Icon =
    kind === "ok"
      ? CheckCircle2
      : kind === "warn"
        ? TriangleAlert
        : kind === "down"
          ? XCircle
          : CircleDot;
  return (
    <span className={styles.kindGlyph} aria-label={label} role="img">
      <Icon size={12} strokeWidth={2.5} aria-hidden="true" />
    </span>
  );
}

export type StatusRailProps = {
  items?: StatusItem[];
  className?: string;
  ariaLabel?: string;
};

export function StatusRail({ items, className, ariaLabel = "System status" }: StatusRailProps) {
  const list = items && items.length > 0 ? items : DEFAULT_ITEMS;
  const containerClass = [styles.rail, className].filter(Boolean).join(" ");

  return (
    <ul className={containerClass} aria-label={ariaLabel}>
      {list.map((item) => {
        const Icon = item.icon;
        return (
          <li
            key={item.id}
            className={[styles.item, styles[`kind_${item.kind}`]].join(" ")}
          >
            <span className={styles.iconWrap} aria-hidden="true">
              <Icon size={16} strokeWidth={1.75} />
            </span>
            <span className={styles.text}>
              <span className={styles.label}>{item.label}</span>
              <span className={styles.status}>{item.status}</span>
            </span>
            <KindGlyph kind={item.kind} />
          </li>
        );
      })}
    </ul>
  );
}

export default StatusRail;
