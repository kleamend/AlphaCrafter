import styles from "./page.module.css";

export default function HomePage() {
  return (
    <main className={styles.pageShell}>
      <section className={styles.scaffoldPanel}>
        <p className={styles.kicker}>AlphaCrafter Local Console</p>
        <h1>Miner, Screener, Trader</h1>
        <p>Next.js console scaffold is ready.</p>
      </section>
    </main>
  );
}
