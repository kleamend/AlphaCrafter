"use client";

import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { Copy, Eraser } from "lucide-react";

import { terminalLineIn } from "@/lib/motion-system";
import { getCopy, type Locale } from "@/lib/i18n";
import type { TerminalLine } from "@/lib/schemas";

import styles from "./LiveTerminal.module.css";

export type LiveTerminalProps = {
  lines: TerminalLine[];
  onClear: () => void;
  className?: string;
  locale?: Locale;
};

type StreamFilter = "all" | "stdout" | "stderr" | "system";

function formatTime(at: string): string {
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return at;
  const hh = date.getHours().toString().padStart(2, "0");
  const mm = date.getMinutes().toString().padStart(2, "0");
  const ss = date.getSeconds().toString().padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function LiveTerminal({ lines, onClear, className, locale = "en" }: LiveTerminalProps) {
  const copy = getCopy(locale).terminal;
  const filterOptions: ReadonlyArray<{ value: StreamFilter; label: string }> = [
    { value: "all", label: copy.all },
    { value: "stdout", label: copy.stdout },
    { value: "stderr", label: copy.stderr },
    { value: "system", label: copy.system },
  ];
  const [filter, setFilter] = useState<StreamFilter>("all");
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const trimmed = query.trim().toLowerCase();
    return lines.filter((line) => {
      if (filter !== "all" && line.stream !== filter) return false;
      if (trimmed.length === 0) return true;
      return line.text.toLowerCase().includes(trimmed);
    });
  }, [lines, filter, query]);

  const containerClass = [styles.terminal, className].filter(Boolean).join(" ");

  const handleCopy = async () => {
    if (visible.length === 0) return;
    const text = visible
      .map((line) => `[${formatTime(line.at)}] ${line.stream} ${line.text}`)
      .join("\n");
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch {
        // Fall through to legacy path.
      }
    }
    if (typeof document !== "undefined") {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand("copy");
      } catch {
        // Ignore — best-effort copy.
      }
      document.body.removeChild(textarea);
    }
  };

  return (
    <section className={containerClass} aria-label="Live terminal">
      <header className={styles.header}>
        <h2 className={styles.title}>{copy.title}</h2>
        <p className={styles.hint}>
          {copy.hint}
        </p>
      </header>

      <div className={styles.toolbar}>
        <select
          className={styles.filter}
          value={filter}
          onChange={(event) => setFilter(event.target.value as StreamFilter)}
          aria-label="Filter by stream"
        >
          {filterOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <input
          className={styles.search}
          type="search"
          placeholder={copy.search}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label={copy.search}
        />
        <button
          type="button"
          className={styles.actionButton}
          onClick={handleCopy}
          disabled={visible.length === 0}
        >
          <Copy size={12} strokeWidth={2} aria-hidden="true" />
          {copy.copy}
        </button>
        <button
          type="button"
          className={styles.actionButton}
          onClick={onClear}
          disabled={lines.length === 0}
        >
          <Eraser size={12} strokeWidth={2} aria-hidden="true" />
          {copy.clear}
        </button>
      </div>

      <div className={styles.body} role="log" aria-live="polite">
        {visible.length === 0 ? (
          <span className={styles.empty}>
            {lines.length === 0 ? copy.empty : copy.noMatch}
          </span>
        ) : (
          visible.map((line) => (
            <motion.div
              key={line.id}
              className={styles.line}
              variants={terminalLineIn}
              initial="hidden"
              animate="visible"
            >
              <span className={styles.timestamp}>{formatTime(line.at)}</span>
              <span
                className={[styles.streamTag, styles[`stream_${line.stream}`]].join(" ")}
              >
                {line.stream}
              </span>
              <span
                className={[styles.text, styles[`text_${line.stream}`]].join(" ")}
              >
                {line.stream === "stderr" ? (
                  <span className={styles.errPrefix}>ERR</span>
                ) : null}
                {line.text}
              </span>
            </motion.div>
          ))
        )}
      </div>

      <span className={styles.footer}>
        {copy.showing} {visible.length} {copy.of} {lines.length} {copy.lines}
      </span>
    </section>
  );
}

export default LiveTerminal;
