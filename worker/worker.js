/**
 * Rescene Web · Cloudflare Worker CORS 代理
 *
 * 与 server.py 的本地代理等价：转发 /proxy/{kilo|zen}{path} 到上游 AI 网关，
 * 解决浏览器跨域(CORS)限制，并原样透传 SSE 流式响应。
 *
 * 部署方式（任选其一）：
 *   A. Cloudflare Dashboard（推荐，无需安装任何东西）
 *      1. 登录 https://dash.cloudflare.com → Workers & Pages → 创建应用程序 → 创建 Worker
 *      2. 把本文件全部内容粘贴进编辑器 → 部署
 *      3. 得到地址形如 https://your-worker.你的子域.workers.dev
 *   B. Wrangler CLI（可选）
 *      npm i -g wrangler && wrangler deploy（需要 Cloudflare 账号登录）
 *
 * 部署完成后，把 Worker 地址填进 Rescene Web「设置 → 代理地址」，
 * 连接模式选「本地代理」即可（kilo.ai 必须走代理；opencode.ai 可直连）。
 */
const UPSTREAM = {
  kilo: "https://api.kilo.ai/api/gateway/v1",
  zen:  "https://opencode.ai/zen/v1",
};

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS, PUT, DELETE",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Upstream, Accept",
  "Access-Control-Max-Age": "86400",
};

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // CORS 预检
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }

    // 仅接受 /proxy/{provider}/{rest} 格式
    const parts = url.pathname.split("/");
    if (parts.length >= 4 && parts[1] === "proxy") {
      const provider = parts[2];
      const base = UPSTREAM[provider];
      if (base) {
        const rest = "/" + parts.slice(3).join("/") + (url.search || "");
        const target = base + rest;
        const headers = new Headers(request.headers);
        headers.delete("host");
        if (!headers.has("accept")) {
          headers.set("accept", "text/event-stream, application/json");
        }
        try {
          const resp = await fetch(target, {
            method: request.method,
            headers,
            body: request.body,
            redirect: "follow",
          });
          const out = new Response(resp.body, {
            status: resp.status,
            statusText: resp.statusText,
            headers: resp.headers,
          });
          out.headers.set("Access-Control-Allow-Origin", "*");
          out.headers.set("Cache-Control", "no-cache");
          return out;
        } catch (e) {
          return new Response(JSON.stringify({ error: "upstream error", detail: String(e) }), {
            status: 502,
            headers: { "Content-Type": "application/json", ...CORS },
          });
        }
      }
    }

    return new Response("not found", { status: 404, headers: CORS });
  },
};
