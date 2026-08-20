# Rescene Web · 模型聚合助手（网页版）

在线访问：<https://cyhub1122.github.io/ResceneWeb/>

## 功能

- 聚合 **Kilo**（api.kilo.ai）与 **Zen**（opencode.ai）两大 AI 网关
- 全免费模型直用；付费模型可填 Zen API Key
- 流式输出、离线模型兜底、本地保存会话

## 连接模式

| 网关 | 浏览器直连 | 说明 |
|------|-----------|------|
| Zen（opencode.ai） | ✅ 支持 | 已开放 CORS，开箱即用 |
| Kilo（api.kilo.ai） | ❌ 不支持 | 必须走 CORS 代理 |

页面「设置」中可切换连接模式：

- **直连**：仅 Zen 可用
- **本地代理**：运行 `server.py`（本机使用），或部署 `worker/worker.js` 到 Cloudflare Worker（网页分享使用）

## 部署 Cloudflare Worker（推荐，免费）

Kilo 网关在浏览器端被 CORS 拦截，需要部署一个免费代理：

1. 打开 <https://dash.cloudflare.com> → 左侧 **Workers & Pages** → **创建应用程序** → **创建 Worker**
2. 删除默认模板，把 [`worker/worker.js`](worker/worker.js) 的全部内容粘贴进去
3. 点 **部署**，得到地址，形如 `https://你的子域.workers.dev`
4. 打开 Rescene Web → 设置 → 代理地址填入该 Worker 地址 → 连接模式选「本地代理」

部署后即可正常使用 Kilo 网关的全部免费模型。

## 本地开发

```bash
python3 server.py        # 本地起静态服务 + CORS 代理，端口 8000
# 浏览器访问 http://127.0.0.1:8000
```
