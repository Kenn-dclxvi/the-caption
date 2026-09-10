import express from "express";
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { createServer as createViteServer } from "vite";
import { InputApiGateway } from "./inputApiGateway";

const PORT = Number(process.env.PORT || 3001);
const HOST = process.env.HOST || "127.0.0.1";
const APP_ROOT = process.cwd();
const REPOSITORY_ROOT = path.resolve(APP_ROOT, "../../..");
const DATA_ROOT = process.env.CAPTION_DATA_DIR ? path.resolve(process.env.CAPTION_DATA_DIR) : path.join(REPOSITORY_ROOT, "data");
const CSV_PATH = path.join(DATA_ROOT, "collection/market_units.csv");
const EXTERNAL_ASSETS_PATH = path.join(DATA_ROOT, "external_assets.json");
const PORTFOLIO_BASIS_PATH = path.join(DATA_ROOT, "portfolio_basis.json");
const DIST_PATH = path.join(APP_ROOT, "dist");

async function startServer(): Promise<void> {
  const app = express();
  app.disable("etag"); // A normalized PUT must not acquire Express' automatic validator.
  app.set("trust proxy", "loopback");
  const gateway = new InputApiGateway(REPOSITORY_ROOT, CSV_PATH);
  const forward: express.RequestHandler = async (req, res) => {
    // Mounted middleware strips the prefix from req.path; the worker needs canonical paths.
    gateway.send(res, await gateway.call(req, { path: req.originalUrl.split("?", 1)[0] }));
  };
  for (const prefix of ["/api/v1", "/api/session", "/api/funds", "/api/health", "/api/external-assets", "/api/portfolio-basis"]) {
    app.use(prefix, express.raw({ type: () => true, limit: "2mb" }), forward);
  }
  app.use((error: { status?: number }, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    const status = error.status === 413 ? 413 : 400;
    res.status(status).type("application/problem+json").set("Cache-Control", "no-store").json({
      type: "about:blank", title: status === 413 ? "Content Too Large" : "Bad Request", status,
      code: status === 413 ? "payload_too_large" : "invalid_request", instance: `urn:uuid:${randomUUID()}`,
      detail: status === 413 ? "入力サイズの上限を超えています。" : "正しいJSONを送信してください。",
    });
  });

  if (process.env.NODE_ENV === "production") {
    app.use(express.static(DIST_PATH));
    app.get(/.*/, (_req, res) => res.sendFile(path.join(DIST_PATH, "index.html")));
  } else {
    const vite = await createViteServer({
      root: APP_ROOT,
      server: { middlewareMode: true }
    });
    app.use(vite.middlewares);
  }

  const server = app.listen(PORT, HOST, () => {
    console.log(`THE CAPTION: http://localhost:${PORT}`);
    console.log(`Market Units CSV Path: ${CSV_PATH}`);
    console.log(`External Assets Path: ${EXTERNAL_ASSETS_PATH}`);
    console.log(`Portfolio Basis Path: ${PORTFOLIO_BASIS_PATH}`);
  });
  for (const signal of ["SIGTERM", "SIGINT"] as const) {
    process.once(signal, () => { gateway.close(); server.close(() => process.exit(0)); });
  }
}

void startServer();
