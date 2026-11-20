import { Container } from "@cloudflare/containers";

export class Europa extends Container {
  defaultPort = 8000;
  // Stop after 10 idle minutes, so you only pay for memory while it's in use. Next request starts it again (a few seconds).
  sleepAfter = "10m";
  envVars = {
    EUROPA_RATE_LIMIT_RPS: "5",
    // Set with `npx wrangler secret put EUROPA_API_KEYS` to require a bearer token (optional).
  };

  constructor(ctx, env) {
    super(ctx, env);
    if (env.EUROPA_API_KEYS) this.envVars = { ...this.envVars, EUROPA_API_KEYS: env.EUROPA_API_KEYS };
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/") {
      return new Response(
        "Europa MCP server: European open data for AI assistants.\n" +
          `Connector URL: ${url.origin}/mcp\nhttps://github.com/jadikar-arch/euro-data-mcp\n`,
        { headers: { "content-type": "text/plain; charset=utf-8" } },
      );
    }
    // Pass the real client IP on, so the server's per-client rate limit isn't one shared bucket.
    const headers = new Headers(request.headers);
    const ip = request.headers.get("cf-connecting-ip");
    if (ip) headers.set("x-forwarded-for", ip);
    return env.EUROPA.getByName("main").fetch(new Request(request, { headers }));
  },
};
