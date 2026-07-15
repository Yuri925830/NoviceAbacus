import { expect, test } from "@playwright/test";

const ownerEmail = process.env.E2E_OWNER_EMAIL;
const ownerPassword = process.env.E2E_OWNER_PASSWORD;

test.beforeAll(() => {
  if (!ownerEmail || !ownerPassword)
    throw new Error(
      "Set E2E_OWNER_EMAIL and E2E_OWNER_PASSWORD for an isolated local test OWNER.",
    );
});

test("OWNER can sign in, clear assets, and see the real dashboard", async ({
  page,
}) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "欢迎回来" })).toBeVisible();
  await expect(page.getByAltText("小白算盘怀特理财顾问")).toBeVisible();
  await page.screenshot({ path: "../../artifacts/login.png", fullPage: true });

  await page.getByLabel("邮箱或手机号").fill(ownerEmail!);
  await page.getByLabel("密码").fill(ownerPassword!);
  await page.getByRole("button", { name: /进入我的资产空间/ }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const purge = await page.request.post("/backend/data/purge", {
    data: { password: ownerPassword, totp_code: null },
  });
  expect(purge.ok()).toBeTruthy();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "从第一张资产底牌开始" }),
  ).toBeVisible();

  await page.getByRole("link", { name: /开始第一次清算/ }).click();
  await expect(
    page.getByRole("heading", { name: "完成一次真实清算" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/clearing.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "手工添加", exact: true })
    .first()
    .click();
  await page.getByLabel("名称").fill("韩国活期");
  await page.getByLabel("币种").selectOption("CNY");
  await page.getByLabel("当前金额 / 本金").fill("125000");
  await page.getByRole("button", { name: /加入本次清算/ }).click();
  await expect(page.getByText("韩国活期")).toBeVisible();
  await page.getByRole("button", { name: /确认本次清算/ }).click();
  await expect(
    page.getByRole("heading", { name: "这次资产底牌已确认" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "回到驾驶舱" }).click();
  await expect(
    page.getByRole("heading", { name: "你的资产底牌" }),
  ).toBeVisible();
  await expect(page.getByText("¥125,000.00").first()).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/dashboard.png",
    fullPage: true,
  });

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "系统设置" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "OWNER 与模型路由" }),
  ).toBeVisible();
  await page.getByLabel("当前使用地区").selectOption("KR");
  await page.getByRole("button", { name: "保存", exact: true }).first().click();
  await expect(page.getByText("已配置，额度不足")).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/settings.png",
    fullPage: true,
  });

  await page.goto("/assistant");
  await expect(page.getByRole("heading", { name: "问怀特" })).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/assistant.png",
    fullPage: true,
  });

  await page.goto("/trend");
  await expect(
    page.getByRole("heading", { name: "资产 K 线与趋势" }),
  ).toBeVisible();
  await page.screenshot({ path: "../../artifacts/trend.png", fullPage: true });

  await page.goto("/data");
  await expect(
    page.getByRole("heading", {
      name: "你的底牌，可以带走，也可以验证后恢复。",
    }),
  ).toBeVisible();
  await page.screenshot({ path: "../../artifacts/data.png", fullPage: true });
});

test("core experience remains usable on a phone viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(page.getByAltText("小白算盘怀特理财顾问")).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/login-mobile.png",
    fullPage: true,
  });
  await page.getByLabel("邮箱或手机号").fill(ownerEmail!);
  await page.getByLabel("密码").fill(ownerPassword!);
  await page.getByRole("button", { name: /进入我的资产空间/ }).click();
  await expect(
    page.getByRole("heading", { name: "你的资产底牌" }),
  ).toBeVisible();
  await expect(page.getByText("¥125,000.00").first()).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/dashboard-mobile.png",
    fullPage: true,
  });

  await page.goto("/assistant");
  await expect(page.getByRole("heading", { name: "问怀特" })).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/assistant-mobile.png",
    fullPage: true,
  });

  await page.goto("/clearing");
  await expect(
    page.getByRole("heading", { name: "完成一次真实清算" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/clearing-mobile.png",
    fullPage: true,
  });

  await page.goto("/trend");
  await expect(
    page.getByRole("heading", { name: "资产 K 线与趋势" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/trend-mobile.png",
    fullPage: true,
  });

  await page.goto("/data");
  await expect(
    page.getByRole("heading", {
      name: "你的底牌，可以带走，也可以验证后恢复。",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/data-mobile.png",
    fullPage: true,
  });
});
