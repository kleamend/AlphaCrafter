"use client";

import { motion } from "framer-motion";
import { Languages, PlayCircle, Radio } from "lucide-react";

import { panelEnter } from "@/lib/motion-system";
import {
  LOCALE_LABELS,
  getCopy,
  type ConsoleMode,
  type Locale,
} from "@/lib/i18n";

import styles from "./ConsoleClient.module.css";

export type TopbarProps = {
  locale: Locale;
  onLocaleChange: (locale: Locale) => void;
  mode: ConsoleMode;
  onModeChange: (mode: ConsoleMode) => void;
};

const MODE_ICON: Record<ConsoleMode, typeof Radio> = {
  real: Radio,
  demo: PlayCircle,
};

export function Topbar({ locale, onLocaleChange, mode, onModeChange }: TopbarProps) {
  const copy = getCopy(locale).topbar;

  return (
    <motion.header className={styles.topbar} variants={panelEnter}>
      <div className={styles.brandBlock}>
        <span className={styles.brandMark} aria-hidden="true">AC</span>
        <div>
          <p className={styles.brandLabel}>{copy.product}</p>
          <h1 className={styles.brandTitle}>{copy.product}</h1>
        </div>
      </div>

      <div className={styles.topbarControls}>
        <div className={styles.segmented} role="tablist" aria-label="Console mode">
          {(["real", "demo"] as const).map((entry) => {
            const Icon = MODE_ICON[entry];
            return (
              <button
                key={entry}
                type="button"
                role="tab"
                className={[styles.segmentButton, mode === entry ? styles.segmentActive : ""].join(" ")}
                onClick={() => onModeChange(entry)}
                aria-selected={mode === entry}
                aria-label={entry === "real" ? copy.realMode : copy.demoMode}
              >
                <Icon size={15} aria-hidden="true" />
                {entry === "real" ? copy.realMode : copy.demoMode}
              </button>
            );
          })}
        </div>

        <div className={styles.languageSwitch} aria-label={copy.language}>
          <Languages size={15} aria-hidden="true" />
          {(["zh", "en"] as const).map((entry) => (
            <button
              key={entry}
              type="button"
              className={[styles.langButton, locale === entry ? styles.langActive : ""].join(" ")}
              onClick={() => onLocaleChange(entry)}
              aria-pressed={locale === entry}
            >
              {LOCALE_LABELS[entry]}
            </button>
          ))}
        </div>
      </div>
    </motion.header>
  );
}

export default Topbar;
