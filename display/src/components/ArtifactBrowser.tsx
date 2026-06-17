"use client";

import { useMemo, useState } from "react";
import { Copy, FileText, FolderOpen, X } from "lucide-react";

import { getCopy, type Locale } from "@/lib/i18n";
import type { ArtifactSummary, ArtifactsResponse } from "@/lib/schemas";

import styles from "./ArtifactBrowser.module.css";

export type ArtifactBrowserProps = {
  artifacts: ArtifactsResponse | null;
  locale?: Locale;
};

type GroupId = "strategy" | "factors" | "accountDate" | "logs";

type GroupDef = {
  id: GroupId;
  label: string;
  match: (kind: ArtifactSummary["kind"]) => boolean;
  emptyMessage: string;
};

function getGroupDefs(locale: Locale): ReadonlyArray<GroupDef> {
  const copy = getCopy(locale).artifacts;
  return [
    {
      id: "strategy",
      label: copy.strategy,
      match: (kind) => kind === "strategy",
      emptyMessage: copy.empty.strategy,
    },
    {
      id: "factors",
      label: copy.factors,
      match: (kind) => kind === "factor",
      emptyMessage: copy.empty.factors,
    },
    {
      id: "accountDate",
      label: copy.accountDate,
      match: (kind) => kind === "account" || kind === "date",
      emptyMessage: copy.empty.accountDate,
    },
    {
      id: "logs",
      label: copy.logs,
      match: (kind) => kind === "log",
      emptyMessage: copy.empty.logs,
    },
  ];
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatUpdated(at: string | null): string {
  if (!at) return "—";
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return at;
  return date.toLocaleString();
}

function copyText(value: string): void {
  if (typeof navigator !== "undefined" && navigator.clipboard) {
    void navigator.clipboard.writeText(value).catch(() => {
      /* noop */
    });
  }
}

export function ArtifactBrowser({ artifacts, locale = "en" }: ArtifactBrowserProps) {
  const copy = getCopy(locale).artifacts;
  const files = useMemo(() => artifacts?.files ?? [], [artifacts]);
  const groupDefs = useMemo(() => getGroupDefs(locale), [locale]);
  const grouped = useMemo(() => {
    return groupDefs.map((group) => ({
      ...group,
      files: files.filter((file) => group.match(file.kind)),
    }));
  }, [files, groupDefs]);

  const [activeId, setActiveId] = useState<string | null>(null);
  const active = activeId ? files.find((file) => file.id === activeId) ?? null : null;

  return (
    <section className={styles.panel} aria-label="Artifact browser">
      <header className={styles.header}>
        <h2 className={styles.title}>{copy.title}</h2>
        <p className={styles.hint}>{copy.hint}</p>
      </header>

      <div className={styles.body}>
        <ul className={styles.groups} role="list">
          {grouped.map((group) => (
            <li key={group.id} className={styles.group}>
              <div className={styles.groupHeader}>
                <FolderOpen size={12} strokeWidth={2} aria-hidden="true" />
                <span className={styles.groupLabel}>{group.label}</span>
                <span className={styles.groupCount}>{group.files.length}</span>
              </div>
              {group.files.length === 0 ? (
                <p className={styles.groupEmpty}>{group.emptyMessage}</p>
              ) : (
                <ul className={styles.fileList} role="list">
                  {group.files.map((file) => (
                    <li key={file.id}>
                      <button
                        type="button"
                        className={[
                          styles.fileRow,
                          file.id === activeId ? styles.fileRowActive : "",
                        ].join(" ")}
                        onClick={() => setActiveId(file.id)}
                      >
                        <FileText size={12} strokeWidth={1.75} aria-hidden="true" />
                        <span className={styles.fileLabel}>{file.label}</span>
                        <span className={styles.filePath}>{file.relativePath}</span>
                        <span className={styles.fileSize}>{formatBytes(file.sizeBytes)}</span>
                        <span className={styles.fileUpdated}>
                          {formatUpdated(file.updatedAt)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>

        {active ? (
          <aside className={styles.preview} aria-label="Artifact preview">
            <header className={styles.previewHeader}>
              <span className={styles.previewLabel}>{active.label}</span>
              <span className={styles.previewPath}>{active.relativePath}</span>
              <div className={styles.previewActions}>
                <button
                  type="button"
                  className={styles.previewButton}
                  onClick={() => copyText(active.preview)}
                >
                  <Copy size={12} strokeWidth={2} aria-hidden="true" />
                  {copy.copyPreview}
                </button>
                <button
                  type="button"
                  className={styles.previewButton}
                  onClick={() => setActiveId(null)}
                  aria-label={copy.closePreview}
                >
                  <X size={12} strokeWidth={2} aria-hidden="true" />
                </button>
              </div>
            </header>
            <pre className={styles.previewBody}>
              {active.preview || copy.emptyFile}
            </pre>
          </aside>
        ) : (
          <div className={styles.previewPlaceholder}>
            <span>{copy.selectFile}</span>
          </div>
        )}
      </div>
    </section>
  );
}

export default ArtifactBrowser;
