# 小白算盘部署到阿里云 ESA

这套代码已经按“静态前端 + 独立 API”的正式部署方式拆好：

- `app.example.com`：阿里云 ESA Pages，构建 `apps/web` 并发布 `apps/web/out`
- `api.example.com`：FastAPI，运行在阿里云 ECS、ACK 或其他可持续运行 Python 与持久化数据库的环境
- `openai-gateway:8100`：与 API 放在同一私有容器网络，不直接暴露给公网
- PostgreSQL：建议使用阿里云 RDS PostgreSQL，或至少使用有持久化磁盘与备份策略的 PostgreSQL

ESA Pages 负责 Next.js 静态页面和全球访问；登录、资产识别、清算、智能顾问、邮件、备份等动态能力由 API 域名提供。仅把前端推到 ESA Pages，无法运行 FastAPI、定时任务和数据库。

## 1. 推送前检查

`.env.local`、阿里云 CSV、OpenAI Key、163 邮箱授权密码都已被 `.gitignore` 排除。提交前仍建议运行：

```powershell
git status --short
git check-ignore .env.local
```

确认输出中没有任何真实密钥文件。

## 2. ESA Pages 构建

仓库根目录已有 `esa.jsonc`。在 ESA Pages 连接 GitHub 仓库后，使用以下构建变量：

```text
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
```

配置文件会执行：

```text
corepack enable && cd apps/web && pnpm install --frozen-lockfile
cd apps/web && ESA_STATIC_EXPORT=true pnpm build
```

发布目录为 `apps/web/out`。本机也可以先做同样的静态构建：

```powershell
cd apps\web
$env:ESA_STATIC_EXPORT="true"
$env:NEXT_PUBLIC_API_BASE_URL="https://api.example.com"
pnpm build
```

## 3. API 与数据库

把 `apps/api/Dockerfile` 与 `apps/openai-gateway/Dockerfile` 部署到 ECS/ACK。环境变量从 `.env.production.example` 复制到阿里云 Secret 或容器环境中，不要提交真实值。

重要值：

```text
APP_ENV=production
APP_BASE_URL=https://app.example.com
CORS_ORIGINS=["https://app.example.com"]
DATABASE_URL=postgresql+psycopg://...
OPENAI_GATEWAY_URL=http://openai-gateway:8100
```

前端与 API 最好使用同一根域名下的两个子域，例如 `app.example.com` 和 `api.example.com`。这样安全 Cookie、跨域凭据与浏览器隐私策略更稳定。

API 容器至少需要：

- 8000 端口由反向代理或 ESA 动态加速回源
- 持久化数据库
- 可写的 `/app/data/backups`，或把备份改接对象存储
- 到阿里云百炼、汇率源、SMTP 和私有 OpenAI 网关的出站网络
- HTTPS，且只允许 `CORS_ORIGINS` 中的前端域名携带凭据

## 4. 域名

在 ESA Pages 给静态项目绑定 `app.example.com`。`api.example.com` 指向 ECS/负载均衡源站，也可以接入 ESA 的动态内容加速。API 域名不要指向 Pages 的静态发布目录。

上线后依次验证：

1. `https://api.example.com/health` 返回 `status: ok`
2. `https://app.example.com` 能登录
3. 上传一张测试资产截图，页面出现识别进度和候选项目
4. 怀特在没有清算数据时也能回答一般理财问题
5. 新建财务目标，生成并保存智能计划
6. 创建加密备份并下载
7. 保存一次清算提醒，并确认 163 邮箱能收到测试邮件
8. 新建第二次清算，确认上次资产已自动带入并可逐项编辑、删除或新增
9. 录入实物黄金克重，确认页面显示国际 XAU/USD 报价、人民币每克价格与报价时间
10. 在资产 K 线打开趋势解读，并完成一次“三问清算”归因修正
11. 在自由净资产页面保存资金归属，确认同一项资产无法超额分给多个目标
12. 上传一份产品截图或 PDF，确认 X 光结果包含费用、期限、赎回限制、最坏情形和现金续航变化
13. 在“放心花”填写月收入、必要生活费与当前开销，确认首页出现真实财务电量和本月放心花额度
14. 输入一笔消费决定，确认金额变化时电量实时预演，并且正式裁决只出现“放心做 / 可以做，但要调整 / 现在先别做”之一
15. 创建加密备份后恢复到隔离环境，确认目标计划、资金归属、未来义务、理财规则、产品 X 光和钱事裁决历史都被完整恢复

## 5. 正式上线前的安全动作

任何曾出现在聊天、截图或终端输出里的 API Key、邮箱授权密码和初始登录密码，都应在正式上线前轮换。生产环境建议把登录密码换成高强度密码并启用 TOTP；当前六位数字密码只适合本机短期测试。
