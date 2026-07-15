# 小白算盘 V1.1

依据产品计划书实现的可运行全栈网站。产品名始终为“小白算盘”；Agent 名为“怀特理财顾问”，视觉 IP 是无项圈、七尾、具有专业守护者气场的白色狐狸形象。

登录、TOTP、资产清算、截图识别、财务计算、汇率、国际金价、趋势归因、独立财务目标、可保存的智能计划、目标资金防重算、未来义务、理财规则、产品 X 光、放心花、钱事裁决、财务电量、AI 助手、SMTP 提醒、导出、完整加密备份恢复和数据清除都有后端与持久化实现。

## 结构

- `apps/web`：Next.js 16 / React 19 前端与 PWA
- `apps/api`：FastAPI、SQLAlchemy、SQLite/PostgreSQL、定时提醒和财务计算
- `apps/openai-gateway`：独立的 OpenAI Responses API 海外微网关
- `apps/web/public/brand/huai-te-*.png`：怀特理财顾问的五张正式场景原图
- `apps/web/public/brand/huai-te-*.webp`：网站实际加载的压缩版场景图
- `docker-compose.yml`：PostgreSQL、Redis、API、网关和 Web 的生产化编排起点
- `esa.jsonc`：阿里云 ESA Pages 静态前端构建配置
- `DEPLOY_ESA.md`：ESA Pages + ECS/ACK API + PostgreSQL 的正式部署说明

## 安全配置

不要把密码、TOTP、阿里云 Key 或 OpenAI Key 写进源码、浏览器变量或聊天记录。

1. 复制 `.env.example` 为 `.env.local`。
2. 本项目已支持直接读取阿里云 CSV；`ALIYUN_CREDENTIALS_CSV` 必须指向仅服务器可读的文件。Key 不会复制到前端。
3. 聊天中出现过的 OpenAI Key 应视为已暴露：先在 OpenAI 控制台撤销，再把新建的受限 Key 仅作为 `OPENAI_API_KEY` 注入 `openai-gateway`。
4. 正式环境必须使用独立的高强度 `JWT_SIGNING_KEY`、`DATA_ENCRYPTION_KEY` 和 `GATEWAY_SHARED_SECRET`。
5. 中国大陆或地区不明时，应用会优先使用千问北京；OpenAI 通过独立网关，并在账号地区设置为支持地区后启用。

## 本机启动（Windows PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r apps\api\requirements.txt
.\.venv\Scripts\pip.exe install -r apps\openai-gateway\requirements.txt
cd apps\web
pnpm install
cd ..\..
```

首次创建登录账号（系统没有公开注册入口）：

```powershell
$env:PYTHONPATH="apps/api"
.\.venv\Scripts\python.exe apps\api\scripts\create_owner.py --email you@example.com
```

分别启动三个进程：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\openai-gateway --host 127.0.0.1 --port 8100
cd apps\web; pnpm dev
```

访问 `http://localhost:3000`。首次登录后应立即绑定 TOTP 并离线保存一次性恢复码。

部署到阿里云前请阅读 [`DEPLOY_ESA.md`](./DEPLOY_ESA.md)。ESA Pages 发布静态前端，FastAPI、定时邮件、模型调用与数据库需要运行在 ECS/ACK 等动态源站。

也可以在配置好 `.env.local` 后运行：

```powershell
docker compose up --build
```

使用 Docker 时，建议将阿里云 Key 直接作为部署平台 Secret 注入 `DASHSCOPE_API_KEY`，或把受保护 CSV 只读挂载到容器内并更新路径。

## 真实性边界

- 财务合计全部由 `Decimal` 确定性计算，模型不能改写最终金额。
- 股票/基金使用当前市值，浮盈只展示，不会重复计入资产。
- 外币通过 Frankfurter / ECB 参考汇率换算；过期或不可用时会先请你确认，再使用缓存值。
- 实物黄金按克重读取实时国际 XAU/USD 现货价，再按参考汇率折算人民币每克价格；报价来源、时间和计算过程均保留。
- 放心花与钱事裁决先由确定性规则保护应急金、近期义务、目标占用和负债缓冲；Agent 负责解释，不能篡改金额与三档结论。
- 截图先在浏览器画布遮挡并重新编码；服务器只在内存中调用千问 OCR/视觉模型，完成后释放图片，仅保留哈希和删除审计。
- 资产 K 线只使用真实已确认快照，不插值、不伪造日内波动。
- 加密备份恢复会先验证 SHA-256 和 Fernet 完整性，再以单个事务替换财务数据；账号、密码、TOTP 和可信设备不被覆盖。
- OpenAI 请求设置 `store: false`，只接收脱敏聚合上下文；失败时可回退千问。

## 验证

```powershell
$env:PYTHONPATH="apps/api"
.\.venv\Scripts\python.exe -m pytest apps\api\tests -q

cd apps\web
$env:E2E_OWNER_EMAIL="isolated-test-owner@example.test"
$env:E2E_OWNER_PASSWORD="use-a-local-test-password"
pnpm typecheck
pnpm build
pnpm e2e
```

API 测试会由 `apps/api/tests/conftest.py` 强制使用独立的 `data/xiaobai-test.db`，不会连接本地正式库。端到端测试会使用系统 Chrome检查桌面与手机视口；涉及写入的关键流程用例仍只应针对隔离测试账号运行。
