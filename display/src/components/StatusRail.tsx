import {
  Activity,
  CircleDot,
  Cog,
  ServerCog,
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
          </li>
        );
      })}
    </ul>
  );
}

export default StatusRail;
