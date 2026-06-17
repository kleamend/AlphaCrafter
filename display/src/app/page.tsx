import { ConsoleClient } from "@/components/ConsoleClient";

import styles from "./page.module.css";

export default function HomePage() {
  return (
    <main className={styles.pageShell}>
      <ConsoleClient />
    </main>
  );
}
