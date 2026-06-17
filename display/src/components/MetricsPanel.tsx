"use client";

import { useMemo } from "react";

import type {
  ParsedBacktestLog,
  ParsedMetricPoint,
  ParsedSnapshotLog,
  ParsedSnapshotPoint,
} from "@/lib/schemas";
import { type Locale } from "@/lib/i18n";

import styles from "./MetricsPanel.module.css";

export type MetricsPanelProps = {
  snapshots: ParsedSnapshotLog | null;
  backtests: ParsedBacktestLog | null;
  locale?: Locale;
};

const SPARK_WIDTH = 120;
const SPARK_HEIGHT = 36;
const SPARK_PADDING = 2;

type NumericSnapshotKey = {
  [K in keyof ParsedSnapshotPoint]: ParsedSnapshotPoint[K] extends number | null ? K : never;
}[keyof ParsedSnapshotPoint];

const ACCOUNT_METRICS: ReadonlyArray<{
  id: NumericSnapshotKey;
  label: string;
  format: "currency" | "percent";
}> = [
  { id: "netAssets", label: "Net assets", format: "currency" },
  { id: "totalAssets", label: "Total assets", format: "currency" },
  { id: "availableCash", label: "Available cash", format: "currency" },
  { id: "marketValue", label: "Market value", format: "currency" },
  { id: "grossPositionRate", label: "Gross position", format: "percent" },
  { id: "netPositionRate", label: "Net position", format: "percent" },
];

const BACKTEST_METRIC_ALIASES: Record<string, string> = {
  "Sharpe Ratio": "Sharpe",
  "Calmar Ratio": "Calmar",
  "Total Return (%)": "Return",
  "Max Drawdown (%)": "Max Drawdown",
};

function formatCurrency(value: number | null): string {
  if (value === null) return "—";
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(2)}K`;
  return value.toFixed(2);
}

function formatPercent(value: number | null): string {
  if (value === null) return "—";
  const pct = Math.abs(value) <= 1 ? value * 100 : value;
  return `${pct.toFixed(2)}%`;
}

function pickBacktest(metrics: ParsedMetricPoint[], label: string): number | null {
  for (const metric of metrics) {
    if (metric.label === label) return metric.value;
  }
  return null;
}

function buildSparkPath(values: number[]): { path: string; tone: "up" | "down" | "flat" } {
  if (values.length < 2) return { path: "", tone: "flat" };
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const usableWidth = SPARK_WIDTH - SPARK_PADDING * 2;
  const usableHeight = SPARK_HEIGHT - SPARK_PADDING * 2;
  const stepX = values.length === 1 ? 0 : usableWidth / (values.length - 1);
  const points = values.map((value, index) => {
    const x = SPARK_PADDING + stepX * index;
    const y = SPARK_PADDING + usableHeight - ((value - min) / range) * usableHeight;
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  const tone = values[values.length - 1]! >= values[0]! ? "up" : "down";
  return { path: points.join(" "), tone };
}

function Sparkline({ values }: { values: number[] }) {
  const { path, tone } = useMemo(() => buildSparkPath(values), [values]);
  if (!path) {
    return (
      <span className={styles.sparkEmpty} aria-label="No sparkline data">
        no points
      </span>
    );
  }
  return (
    <svg
      className={[styles.spark, styles[`spark_${tone}`]].join(" ")}
      width={SPARK_WIDTH}
      height={SPARK_HEIGHT}
      viewBox={`0 0 ${SPARK_WIDTH} ${SPARK_HEIGHT}`}
      role="img"
      aria-label="Net assets sparkline"
    >
      <path d={path} fill="none" stroke="currentColor" strokeWidth={1.5} />
    </svg>
  );
}

type MetricCell = {
  id: string;
  label: string;
  value: string;
  tone: "up" | "down" | "flat";
};

function toneFor(value: number | null): MetricCell["tone"] {
  if (value === null) return "flat";
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "flat";
}

export function MetricsPanel({ snapshots, backtests, locale = "en" }: MetricsPanelProps) {
  const isZh = locale === "zh";
  const latest = snapshots?.latest ?? null;
  const points = useMemo(() => snapshots?.points ?? [], [snapshots]);
  const backtestMetrics = useMemo(() => backtests?.metrics ?? [], [backtests]);

  const sparkValues = useMemo(
    () =>
      points
        .map((point) => point.netAssets)
        .filter((value): value is number => value !== null),
    [points]
  );

  const accountCells: MetricCell[] = ACCOUNT_METRICS.map((metric) => {
    const value = latest ? latest[metric.id] : null;
    const formatted =
      metric.format === "currency" ? formatCurrency(value) : formatPercent(value);
    return {
      id: metric.id,
      label: metric.label,
      value: formatted,
      tone: toneFor(value),
    };
  });

  const backtestCells: MetricCell[] = Object.entries(BACKTEST_METRIC_ALIASES).map(
    ([label, displayName]) => {
      const value = pickBacktest(backtestMetrics, label);
      return {
        id: label,
        label: displayName,
        value: formatPercent(value),
        tone: toneFor(value),
      };
    }
  );

  const allCells = [...accountCells, ...backtestCells];

  return (
    <section className={styles.panel} aria-label="Metrics panel">
      <header className={styles.header}>
        <h2 className={styles.title}>{isZh ? "指标" : "Metrics"}</h2>
        <p className={styles.hint}>
          {isZh
            ? "最新账户快照和核心回测比率。净资产火花线会在至少两个快照后绘制。"
            : "Latest account snapshot and headline backtest ratios. Sparkline shows net assets history when at least two snapshots exist."}
        </p>
      </header>

      <div className={styles.sparkRow}>
        <div className={styles.sparkLabel}>
          <span className={styles.sparkKicker}>{isZh ? "净资产" : "Net assets"}</span>
          <span className={styles.sparkLatest}>
            {formatCurrency(latest?.netAssets ?? null)}
          </span>
        </div>
        {sparkValues.length >= 2 ? (
          <Sparkline values={sparkValues} />
        ) : (
          <span className={styles.sparkEmpty}>
            {points.length === 0
              ? (isZh ? "还没有快照数据，首轮循环后会绘制。" : "No snapshot data yet - sparkline will render after the first cycle.")
              : (isZh ? "目前只有单个快照，火花线至少需要两个点。" : "Single snapshot recorded - sparkline needs at least two points.")}
          </span>
        )}
      </div>

      <ul className={styles.grid} role="list">
        {allCells.map((cell) => (
          <li key={cell.id} className={[styles.cell, styles[`tone_${cell.tone}`]].join(" ")}>
            <span className={styles.cellLabel}>{cell.label}</span>
            <span className={styles.cellValue}>{cell.value}</span>
          </li>
        ))}
      </ul>

      {backtests?.latestAt ? (
        <span className={styles.footer}>
          {isZh ? "回测指标更新于" : "Backtest metrics updated"} {new Date(backtests.latestAt).toLocaleString()}
        </span>
      ) : (
        <span className={styles.footer}>
          {isZh
            ? "Trader 输出回测结果后，这里会填充回测指标。"
            : "Backtest metrics populate after the Trader agent emits a backtest result."}
        </span>
      )}
    </section>
  );
}

export default MetricsPanel;
