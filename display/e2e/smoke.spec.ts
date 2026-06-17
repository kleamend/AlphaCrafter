import { expect, test, type Page } from "@playwright/test";

const FORBIDDEN_VISIBLE_TEXT = [
  "Placeholder for the upcoming",
  "will mount here",
  "AI-powered",
  "revolutionary",
  "unlock your potential",
];

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const canScrollHorizontally = await page.evaluate(async () => {
    const beforeX = window.scrollX;
    window.scrollTo({ left: 4096, top: 0, behavior: "auto" });
    const afterX = window.scrollX;
    window.scrollTo({ left: 0, top: 0, behavior: "auto" });
    return afterX > beforeX + 1;
  });
  expect(canScrollHorizontally).toBe(false);
}

async function expectNoForbiddenText(page: Page): Promise<void> {
  const text = await page.locator("body").innerText();
  for (const phrase of FORBIDDEN_VISIBLE_TEXT) {
    expect(text.includes(phrase), `Forbidden visible text: ${phrase}`).toBe(false);
  }
}

async function expectOpsDeckFirstViewport(page: Page): Promise<void> {
  const deck = page.getByTestId("ops-deck");
  await expect(deck).toBeVisible();
  const box = await deck.boundingBox();
  expect(box, "ops deck must have a rendered box").not.toBeNull();
  expect(box!.y, "ops deck should be in the first viewport").toBeLessThan(260);
  expect(box!.height, "ops deck should carry the first-screen experience").toBeGreaterThan(600);
}

async function expectLargeAgentArtwork(page: Page, alt: RegExp): Promise<void> {
  const artwork = page.getByRole("img", { name: alt }).first();
  await expect(artwork).toBeVisible();
  const box = await artwork.boundingBox();
  expect(box, "active agent artwork should be rendered").not.toBeNull();
  expect(box!.height, "active agent artwork should use the large character asset").toBeGreaterThan(260);
}

test.describe("AlphaCrafter display experience", () => {
  test("opens on the Chinese ops deck with real controls and large character art", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expect(page).toHaveTitle(/AlphaCrafter/);
    await expectOpsDeckFirstViewport(page);
    await expect(page.getByRole("heading", { name: "AlphaCrafter Agent 作战台" }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "运行控制" })).toBeVisible();
    await expect(page.getByRole("button", { name: /启动/ })).toBeVisible();
    await expect(page.getByLabel(/Agent 流程/)).toBeVisible();
    await expectLargeAgentArtwork(page, /因子筛选员/);
    await expectNoForbiddenText(page);
  });

  test("supports Chinese and English switching", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const sessionsResponse = page.waitForResponse((response) =>
      response.url().includes("/api/sessions") && response.status() === 200
    );
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await sessionsResponse;
    await expect(page.getByRole("button", { name: /启动/ })).toBeVisible();
    await expect(page.getByRole("combobox", { name: "选择会话" })).toHaveValue("template_a");

    await page.getByRole("button", { name: "EN", exact: true }).click();
    await expect(page.getByText("AlphaCrafter Agent Ops Deck").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Run Control" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Start/ })).toBeVisible();

    await page.getByRole("button", { name: "中文", exact: true }).click();
    await expect(page.getByText("AlphaCrafter Agent 作战台").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "运行控制" })).toBeVisible();
  });

  test("demo mode is a mode inside the deck, not a separate page block", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    const sessionsResponse = page.waitForResponse((response) =>
      response.url().includes("/api/sessions") && response.status() === 200
    );
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await sessionsResponse;
    await expect(page.getByRole("button", { name: /启动/ })).toBeVisible();

    await page.getByRole("tab", { name: /引导演示/ }).click();
    const deck = page.getByTestId("ops-deck");
    await expect(deck.getByRole("heading", { name: "引导演示" })).toBeVisible();
    await expect(deck.getByRole("button", { name: /播放/ })).toBeVisible();
  });

  test("mobile layout keeps the deck usable without horizontal overflow", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expectOpsDeckFirstViewport(page);
    await expect(page.getByRole("heading", { name: "运行控制" })).toBeVisible();
    await expectLargeAgentArtwork(page, /因子筛选员/);
    await expectNoHorizontalOverflow(page);
    await expectNoForbiddenText(page);
  });
});

test.describe("Reduced motion behaviour", () => {
  test.use({ reducedMotion: "reduce" });

  test("core state remains readable without motion", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("ops-deck")).toBeVisible();
    await expect(page.getByRole("heading", { name: "运行控制" })).toBeVisible();
    await expect(page.getByLabel(/Agent 流程/).locator('[aria-current="step"]')).toContainText(/Screener/);
  });
});
