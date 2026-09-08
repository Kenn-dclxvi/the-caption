import express from "express";
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { createServer as createViteServer } from "vite";
import { InputApiGateway } from "./inputApiGateway";

interface ExternalAssetItem {
  category: string;
  amount: number;
  name: string;
}

interface ExternalAssetsRecord {
  items: ExternalAssetItem[];
}

type ExternalAssetsMap = Record<string, ExternalAssetsRecord>;

interface PortfolioBasisRecord {
  total_acquisition_cost_jpy: number;
}

type PortfolioBasisMap = Record<string, PortfolioBasisRecord>;

const PORT = Number(process.env.PORT || 3001);
const HOST = process.env.HOST || "127.0.0.1";
const APP_ROOT = process.cwd();
const REPOSITORY_ROOT = path.resolve(APP_ROOT, "../../..");
const DATA_ROOT = process.env.CAPTION_DATA_DIR ? path.resolve(process.env.CAPTION_DATA_DIR) : path.join(REPOSITORY_ROOT, "data");
const CSV_PATH = path.join(DATA_ROOT, "collection/market_units.csv");
const EXTERNAL_ASSETS_PATH = path.join(DATA_ROOT, "external_assets.json");
const PORTFOLIO_BASIS_PATH = path.join(DATA_ROOT, "portfolio_basis.json");
const DIST_PATH = path.join(APP_ROOT, "dist");

function ensureParentDir(filePath: string): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function sortMonthKeys(a: string, b: string): number {
  if (a === "default") {
    return 1;
  }
  if (b === "default") {
    return -1;
  }
  return b.localeCompare(a);
}

function normalizeExternalAssetItem(input: unknown): ExternalAssetItem {
  const item = typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
  const amount = Number(item.amount ?? 0);

  return {
    category: String(item.category ?? "").trim(),
    amount: Number.isFinite(amount) ? amount : 0,
    name: String(item.name ?? "").trim()
  };
}

function normalizeExternalAssets(input: unknown): ExternalAssetsMap {
  const payload = typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
  const normalized: ExternalAssetsMap = {};

  for (const key of Object.keys(payload).sort(sortMonthKeys)) {
    const entry = payload[key];
    const itemsSource =
      typeof entry === "object" && entry !== null && Array.isArray((entry as Record<string, unknown>).items)
        ? ((entry as Record<string, unknown>).items as unknown[])
        : [];

    normalized[key] = {
      items: itemsSource.map((item) => normalizeExternalAssetItem(item))
    };
  }

  return normalized;
}

function normalizePortfolioBasisRecord(input: unknown): PortfolioBasisRecord {
  const record = typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
  const cost = Number(record.total_acquisition_cost_jpy ?? 0);

  return {
    total_acquisition_cost_jpy: Number.isFinite(cost) && cost > 0 ? cost : 0
  };
}

function normalizePortfolioBasis(input: unknown): PortfolioBasisMap {
  const payload = typeof input === "object" && input !== null ? (input as Record<string, unknown>) : {};
  const normalized: PortfolioBasisMap = {};

  for (const key of Object.keys(payload).sort(sortMonthKeys)) {
    normalized[key] = normalizePortfolioBasisRecord(payload[key]);
  }

  return normalized;
}

async function startServer(): Promise<void> {
  const app = express();
  app.disable("etag"); // A normalized PUT must not acquire Express' automatic validator.
  app.set("trust proxy", "loopback");
  const gateway = new InputApiGateway(REPOSITORY_ROOT, CSV_PATH);
  const forward: express.RequestHandler = async (req, res) => {
    // Mounted middleware strips the prefix from req.path; the worker needs canonical paths.
    gateway.send(res, await gateway.call(req, { path: req.originalUrl.split("?", 1)[0] }));
  };
  for (const prefix of ["/api/v1", "/api/session", "/api/funds", "/api/health"]) {
    app.use(prefix, express.raw({ type: () => true, limit: "2mb" }), forward);
  }
  app.use(express.json({ limit: "1mb" }));
  for (const resource of ["external-assets", "portfolio-basis"]) {
    app.use(`/api/${resource}`, async (req, res, next) => {
      const permissions = [`${resource}:read`];
      if (req.method !== "GET") {
        permissions.push(`${resource}:replace`);
        const empty = resource === "external-assets"
          ? Object.values(normalizeExternalAssets(req.body)).every((record) => record.items.length === 0)
          : Object.keys(normalizePortfolioBasis(req.body)).length === 0;
        if (empty) permissions.push(`${resource}:clear`);
      }
      const result = await gateway.call(req, { kind: "authorize", permissions });
      if (result.status !== 204) gateway.send(res, result);
      else { res.setHeader("Cache-Control", "no-store"); next(); }
    });
  }

  app.get("/api/external-assets", (_req, res) => {
    if (!fs.existsSync(EXTERNAL_ASSETS_PATH)) {
      return res.json({});
    }

    try {
      const raw = fs.readFileSync(EXTERNAL_ASSETS_PATH, "utf-8");
      const parsed = JSON.parse(raw) as unknown;
      return res.json(normalizeExternalAssets(parsed));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      return res.status(500).json({ error: message });
    }
  });

  app.post("/api/external-assets", (req, res) => {
    if (typeof req.body !== "object" || req.body === null || Array.isArray(req.body)) {
      return res.status(400).json({ error: "Data must be a JSON object keyed by month." });
    }

    ensureParentDir(EXTERNAL_ASSETS_PATH);
    const normalized = normalizeExternalAssets(req.body);

    try {
      fs.writeFileSync(EXTERNAL_ASSETS_PATH, `${JSON.stringify(normalized, null, 2)}\n`, "utf-8");
      return res.json({
        success: true,
        path: EXTERNAL_ASSETS_PATH,
        count: Object.values(normalized).reduce((sum, record) => sum + record.items.length, 0)
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      return res.status(500).json({ error: message });
    }
  });

  app.get("/api/portfolio-basis", (_req, res) => {
    if (!fs.existsSync(PORTFOLIO_BASIS_PATH)) {
      return res.json({});
    }

    try {
      const raw = fs.readFileSync(PORTFOLIO_BASIS_PATH, "utf-8");
      const parsed = JSON.parse(raw) as unknown;
      return res.json(normalizePortfolioBasis(parsed));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      return res.status(500).json({ error: message });
    }
  });

  app.post("/api/portfolio-basis", (req, res) => {
    if (typeof req.body !== "object" || req.body === null || Array.isArray(req.body)) {
      return res.status(400).json({ error: "Data must be a JSON object keyed by month." });
    }

    ensureParentDir(PORTFOLIO_BASIS_PATH);
    const normalized = normalizePortfolioBasis(req.body);

    try {
      fs.writeFileSync(PORTFOLIO_BASIS_PATH, `${JSON.stringify(normalized, null, 2)}\n`, "utf-8");
      return res.json({
        success: true,
        path: PORTFOLIO_BASIS_PATH,
        count: Object.keys(normalized).length
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      return res.status(500).json({ error: message });
    }
  });

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
