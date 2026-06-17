"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

import { panelEnter, staggerDeck } from "@/lib/motion-system";

import styles from "./ConsoleClient.module.css";

export type ConsoleShellProps = {
  hero: ReactNode;
  statusRail: ReactNode;
  flow: ReactNode;
  errorBanner: ReactNode | null;
  body: ReactNode;
};

// Top-level shell that boots the console panels with staggerDeck + panelEnter.
export function ConsoleShell({ hero, statusRail, flow, errorBanner, body }: ConsoleShellProps) {
  return (
    <motion.div
      className={styles.console}
      variants={staggerDeck}
      initial="hidden"
      animate="visible"
    >
      <motion.div className={styles.heroSection} variants={panelEnter}>
        {hero}
        {statusRail}
      </motion.div>

      <motion.div className={styles.flowRow} variants={panelEnter}>
        {flow}
      </motion.div>

      {errorBanner ? (
        <motion.div
          className={styles.errorBanner}
          role="alert"
          variants={panelEnter}
        >
          {errorBanner}
        </motion.div>
      ) : null}

      <motion.div className={styles.body} variants={panelEnter}>
        {body}
      </motion.div>
    </motion.div>
  );
}

export default ConsoleShell;
