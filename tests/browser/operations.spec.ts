import { test, expect } from "@playwright/test";

test("database traffic, aircraft selection, overlays and persisted replay", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Switch to light mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await page.getByRole("button", { name: "Flights", exact: true }).click();
  await expect(page.getByTestId("flight-row").first()).toBeVisible({
    timeout: 30000,
  });
  await expect(page.locator(".aircraft-icon, .traffic-cluster").first()).toBeVisible();
  await page.getByTestId("flight-row").first().click();
  await expect(
    page.getByLabel("Flight details", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".aircraft-photo img")).toBeVisible();
  await expect(page.getByText("Planned airway route")).toBeVisible();
  await expect(page.getByText("Persisted flown track")).toBeVisible();
  await page.getByRole("button", { name: "Replay recorded positions" }).click();
  await expect(page.getByLabel("Replay position")).toBeVisible();
  await page.getByLabel("Replay position").fill("1");
  await expect(page.getByText("HISTORICAL REPLAY")).toBeVisible();
  await page.getByRole("button", { name: "Return to current" }).click();
  await page
    .getByRole("button", { name: "Intelligence", exact: false })
    .click();
  await expect(page.getByText("CONTRIBUTING FACTORS")).toBeVisible();
  await page.getByRole("button", { name: "Find alternate airports" }).click();
  await expect(page.locator(".alternate").first()).toBeVisible();
  await page.getByRole("button", { name: "Close flight details" }).click();
  await page.getByRole("button", { name: "Layers", exact: true }).click();
  await page.getByLabel("Weather", { exact: true }).uncheck();
  await expect(page.getByLabel("Weather", { exact: true })).not.toBeChecked();
});

test("shared scenario persists across pages and resolves", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await expect(page.locator(".aircraft-icon, .traffic-cluster").first()).toBeVisible({
    timeout: 30000,
  });
  await page
    .getByRole("button", { name: "Disruption lab", exact: true })
    .click();
  await page.getByLabel("Disruption type").selectOption("AIRPORT_CLOSURE");
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/disruptions/simulate") &&
      r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Simulate disruption" }).click();
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const event = await response.json();
  try {
    await expect(
      page.getByText(`SCENARIO #${event.disruption_id} · RESULTS`),
    ).toBeVisible();
    const another = await context.newPage();
    await another.goto("/");
    await another.getByRole("button", { name: "Flights", exact: true }).click();
    await expect(another.locator(".affected-text").first()).toBeVisible({
      timeout: 30000,
    });
    await another.close();
  } finally {
    await page
      .getByRole("button", {
        name: `Resolve scenario ${event.disruption_id}`,
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("button", {
        name: `Resolve scenario ${event.disruption_id}`,
        exact: true,
      }),
    ).toHaveCount(0);
  }
});

test("copilot returns database results and mobile controls remain usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".aircraft-icon, .traffic-cluster").first()).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole("button", { name: "Flights", exact: true }).click();
  await expect(page.getByLabel("Search flights or airports")).toBeVisible();
  await page.getByLabel("Search flights or airports").fill("MAA");
  await expect(page.getByTestId("flight-row").first()).toBeVisible();
  await page.getByTestId("flight-row").first().click();
  await expect(
    page.getByLabel("Flight details", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Close flight details" }).click();
  await page
    .getByRole("button", { name: "Operations copilot", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Which flights are high risk?", exact: true })
    .click();
  await expect(page.getByText("DATABASE RESULT")).toBeVisible({
    timeout: 30000,
  });
  await expect(page.locator(".query-item").first()).toBeVisible();
  expect(
    await page
      .locator("body")
      .evaluate((el) => el.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
});
