import { expect, test } from "@playwright/test";

const accessToken = process.env.E2E_ACCESS_TOKEN;

const routes = [
  ["/dashboard", "你的资产底牌", "dashboard-latest"],
  ["/spending", "放心花", "spending"],
  ["/clearing", "资产清算", "clearing"],
  ["/assets", "资产与历史", "assets"],
  ["/intelligence", "怀特决策舱", "intelligence"],
  ["/trend", "资产 K 线", "trend"],
  ["/goals", "财务目标", "goals"],
  ["/funding", "自由净资产", "funding"],
  ["/constitution", "我的理财宪法", "constitution"],
  ["/xray", "理财产品 X 光", "xray"],
  ["/assistant", "和怀特聊聊", "assistant"],
] as const;

test.beforeEach(async ({ context }) => {
  test.skip(!accessToken, "E2E_ACCESS_TOKEN is required for this read-only visual audit.");
  await context.addCookies([
    {
      name: "xbs_access",
      value: accessToken!,
      domain: "127.0.0.1",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "xbs_access",
      value: accessToken!,
      domain: "localhost",
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
});

test("new financial intelligence pages render on desktop and phone", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));

  for (const [route, heading, filename] of routes) {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(route);
    await expect(page.getByRole("heading", { name: heading, exact: true }).first()).toBeVisible();
    await expect(page.locator(".skeleton")).toHaveCount(0, { timeout: 15_000 });
    await page.screenshot({ path: `../../artifacts/visual-${filename}.png`, fullPage: true });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByRole("heading", { name: heading, exact: true }).first()).toBeVisible();
    await expect(page.locator(".skeleton")).toHaveCount(0, { timeout: 15_000 });
    await page.screenshot({ path: `../../artifacts/visual-${filename}-mobile.png`, fullPage: true });
  }

  expect(pageErrors).toEqual([]);
});
