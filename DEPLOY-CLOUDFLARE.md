# Cloudflare Workers + D1 部署

这是可运行后端的 Workers 版本，不能选择 Pages 静态站点。无需 VPS 或自有域名，可先使用 Cloudflare 分配的 `workers.dev` 地址。免费额度和地区可达性以账号与网络实际情况为准。

## 首次部署（Node.js 22+）

在仓库根目录执行：

```sh
npm ci
npx wrangler login
npx wrangler d1 create bili-study
```

把创建结果中的 `database_id` 写入根目录 `wrangler.jsonc`，替换全零占位符。保留绑定名 `DB`。数据库 ID 不是密码；可以提交。然后执行：

```sh
npm run db:remote
npx wrangler secret put STUDY_INVITE_CODE
npm run deploy
```

secret 命令会提示输入你自选的随机邀请码，不要将邀请码写进代码。部署命令返回真正的网站地址。首次打开，用邀请码注册，模型设置中填自己的 API Key 后开始学习。

如果 Cloudflare 提示先开启 workers.dev 子域名，请在 Workers & Pages 设置中创建子域名。若请求被限制或超出资源额度，查看控制台用量；不要误把所有错误都当成代码故障。

## 从 GitHub 自动部署

先完成上面的数据库创建和迁移。在 Cloudflare 的 Workers & Pages 中创建 **Worker** 并连接此仓库：

- 根目录：仓库根目录（留空或 `/`）。
- 构建命令：`npm run build`。
- 部署命令：`npx wrangler deploy`。
- 生产分支：`main`。
- `wrangler.jsonc` 中必须是你自己的 D1 database_id。
- 在 Worker 设置中配置加密 Secret `STUDY_INVITE_CODE`。

已有 Pages 项目不会自动转换成 Worker，需要新建 Worker。不要只把 `static` 当作产物上传。后续有数据库迁移时，发布前执行 `npm run db:remote`。

## 本地验证

```sh
npm ci
npm run build
npm run db:local
```

在根目录创建被 Git 忽略的 `.dev.vars`，内容为 `STUDY_INVITE_CODE=你自选的本地邀请码`，然后 `npm run dev`。打开命令输出的本地地址。单元测试：`npm test`。

## 功能与数据

- 账号、登录令牌哈希、学习记录、资料和任务保存在 D1，所有查询按用户隔离。会话 12 小时过期，退出会删除登录凭据。
- 密码使用 Web Crypto PBKDF2-SHA256（100,000 次迭代，独立随机盐）；认证按 IP 限流。此版本用于邀请测试，没有找回密码、邮件验证、管理员后台和完整滥用治理。
- 用户模型 API Key **只在当前页面内存中保存**，每次需要模型时经 HTTPS 发送给 Worker，再发给允许的模型服务。刷新/关闭页面需重填；不写入 D1、localStorage 或构建文件。运营者依然能接触处理中的密钥，不能称为端到端加密。
- 同一来源的页面可访问当前页面内存，请不要添加不可信第三方脚本。Worker 不记录请求正文，默认未启用请求日志。
- 默认允许 OpenAI、DeepSeek、阿里云兼容接口；可通过 `STUDY_ALLOWED_PROVIDERS` 设置完整 HTTPS 服务前缀。拒绝模型服务重定向。
- PDF 在浏览器提取文字，再向模型发送提取结果；支持有文字层的 PDF，不提供 OCR。解析资源同源托管，不使用外部 CDN。
- B 站字幕接口可能因登录、地区或风控受限；手动导入字幕始终可用。不包含下载视频、音频转写。
- 学习记录列表最多显示最近 200 条，资料列表最多显示每类最近 500 条。并发修改用版本条件写入，旧页面不会覆盖新进度；竞争请求可能已消耗模型调用费用。
- Python 本地版/Docker 版仍可用，但其原有账号和记录不会自动迁移到 D1。部署前后请分别备份、验证。

## 排查打不开

1. 确认网址属于刚部署的 Worker，而不是旧 Pages 或本机 `127.0.0.1`。
2. 打开 `/api/auth/me`，应返回 `multi_user: true` 和 `runtime: "cloudflare"`。
3. 数据库错误：核对 DB 绑定、database_id，并执行远程迁移。
4. 无法注册：核对 `STUDY_INVITE_CODE` Secret 和用户名/密码规则。
5. 页面可开但总结失败：配置 API Key，核对模型 ID、余额及服务商可达性。

Cloudflare 账号授权与 Secret 必须由部署者提供；源码改造完成不代表已发布公网网站。APK/Windows 在线客户端可填写最终 HTTPS 地址。

## 本次验证范围

已通过核心逻辑单元测试、本地 Wrangler + D1 的双账号隔离/登录/并发冲突/导出集成验证，以及 Worker 发布包 dry-run。没有使用真实用户 API Key 调用付费模型，未验证公网 B 站字幕可达性；浏览器 PDF 交互还需上线后用实际文件验收。本地集成测试命令为 `node cloudflare/tests/integration.mjs`，仅用于端口 8770、邀请码 `local-worker-test` 的隔离测试环境。
