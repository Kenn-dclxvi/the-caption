import express from "express";
import csv from "csv-parser";
import fs from "node:fs";
import path from "node:path";
import { createServer as createViteServer } from "vite";

type FundRow = Record<string, string>;

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
const CSV_PATH = path.resolve(APP_ROOT, "../../../data/collection/market_units.csv");
const EXTERNAL_ASSETS_PATH = path.resolve(APP_ROOT, "../../../data/external_assets.json");
const PORTFOLIO_BASIS_PATH = path.resolve(APP_ROOT, "../../../data/portfolio_basis.json");
const DIST_PATH = path.join(APP_ROOT, "dist");
const FUND_HEADERS = [
  "name",
  "asset_class",
  "currency",
  "units",
  "source_symbol",
  "audit_match_key",
  "csv_url"
] as const;

function ensureParentDir(filePath: string): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function escapeCsvValue(value: string): string {
  if (/[",\n\r]/.test(value)) {
    return `"${value.replace(/"/g, "\"\"")}"`;
  }
  return value;
}

function normalizeFundRow(input: FundRow): FundRow {
  const row: FundRow = {};
  for (const header of FUND_HEADERS) {
    row[header] = String(input[header] ?? "").trim();
  }
  return row;
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
  app.use(express.json({ limit: "1mb" }));

  app.get("/api/funds", (_req, res) => {
    if (!fs.existsSync(CSV_PATH)) {
      return res.json([]);
    }

    const rows: FundRow[] = [];
    fs.createReadStream(CSV_PATH)
      .pipe(csv())
      .on("data", (row: FundRow) => rows.push(normalizeFundRow(row)))
      .on("end", () => res.json(rows))
      .on("error", (error: Error) => res.status(500).json({ error: error.message }));
  });

  app.post("/api/funds", (req, res) => {
    if (!Array.isArray(req.body)) {
      return res.status(400).json({ error: "Data must be an array." });
    }

    ensureParentDir(CSV_PATH);
    const rows = req.body.map((row) => normalizeFundRow(row as FundRow));
    const csvContent = [
      FUND_HEADERS.join(","),
      ...rows.map((row) => FUND_HEADERS.map((header) => escapeCsvValue(row[header])).join(","))
    ].join("\n");

    try {
      fs.writeFileSync(CSV_PATH, `${csvContent}\n`, "utf-8");
      return res.json({ success: true, path: CSV_PATH, count: rows.length });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      return res.status(500).json({ error: message });
    }
  });

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

  app.get("/api/health", (_req, res) => {
    res.json({
      ok: true,
      csvPath: CSV_PATH,
      externalAssetsPath: EXTERNAL_ASSETS_PATH,
      portfolioBasisPath: PORTFOLIO_BASIS_PATH
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

  app.listen(PORT, HOST, () => {
    console.log(`THE CAPTION: http://localhost:${PORT}`);
    console.log(`Market Units CSV Path: ${CSV_PATH}`);
    console.log(`External Assets Path: ${EXTERNAL_ASSETS_PATH}`);
    console.log(`Portfolio Basis Path: ${PORTFOLIO_BASIS_PATH}`);
  });
}

void startServer();
