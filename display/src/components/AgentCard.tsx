"use client";

import { motion } from "framer-motion";
import Image from "next/image";

import { getAgentMeta, type AgentMeta } from "@/lib/agent-meta";
import { getAgentCopy, type Locale } from "@/lib/i18n";
import { agentDock } from "@/lib/motion-system";
import type { AgentPhase } from "@/lib/schemas";

import styles from "./AgentCard.module.css";

export type AgentCardProps = {
  agentId: AgentPhase;
  active: boolean;
  compact?: boolean;
  activeTools?: ReadonlyArray<string>;
  locale?: Locale;
};

export function AgentCard({
  agentId,
  active,
  compact = false,
  activeTools,
  locale = "en",
}: AgentCardProps) {
  const meta: AgentMeta = getAgentMeta(agentId);
  const copy = getAgentCopy(locale, agentId);
  const labels = locale === "zh"
    ? { responsibilities: "职责", tools: "工具" }
    : { responsibilities: "Responsibilities", tools: "Tools" };
  const activeToolSet = new Set(activeTools ?? []);
  const className = [
    styles.card,
    styles[`accent_${agentId}`],
    active ? styles.active : styles.idle,
    compact ? styles.compact : styles.full,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <motion.article
      className={className}
      aria-current={active ? "step" : undefined}
      data-agent={agentId}
      data-compact={compact ? "true" : "false"}
      variants={agentDock}
      animate={active ? "active" : "idle"}
    >
      <div className={styles.identity}>
        <div className={styles.iconFrame} aria-hidden={!active}>
          <Image
            src={meta.icon.src}
            alt={meta.icon.alt}
            width={meta.icon.width}
            height={meta.icon.height}
            className={styles.iconImage}
            priority={active}
          />
        </div>
        <div className={styles.titleBlock}>
          <span className={styles.kicker}>{copy.stage}</span>
          <h3 className={styles.role}>{copy.role}</h3>
          {!compact ? <p className={styles.tagline}>{copy.tagline}</p> : null}
        </div>
      </div>

      {!compact ? (
        <div className={styles.responsibilities}>
          <h4 className={styles.sectionTitle}>{labels.responsibilities}</h4>
          <ul className={styles.responsibilityList}>
            {copy.responsibilities.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className={styles.compactSummary}>{copy.tagline}</p>
      )}

      <div className={styles.toolsBlock}>
        <h4 className={styles.sectionTitle}>{labels.tools}</h4>
        <ul className={styles.toolChips} aria-label={`${copy.role} ${labels.tools}`}>
          {meta.tools.map((tool) => {
            const isPulsing = active && activeToolSet.has(tool);
            return (
              <li
                key={tool}
                className={[
                  styles.toolChip,
                  isPulsing ? styles.toolChipPulsing : null,
                ]
                  .filter(Boolean)
                  .join(" ")}
                data-active={isPulsing ? "true" : "false"}
              >
                {tool}
              </li>
            );
          })}
        </ul>
      </div>
    </motion.article>
  );
}

export default AgentCard;
