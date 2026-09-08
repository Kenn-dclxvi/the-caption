import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";
import type { Request, Response } from "express";

interface WorkerResult {
  id?: string;
  status: number;
  headers: Record<string, string>;
  body: unknown;
}

function unavailable(): WorkerResult {
  return {
    status: 503,
    headers: { "Content-Type": "application/problem+json", "Cache-Control": "no-store", "Retry-After": "5" },
    body: { type: "about:blank", title: "Service Unavailable", status: 503,
      code: "input_store_unavailable", instance: `urn:uuid:${randomUUID()}`,
      detail: "APIに接続できません。結果不明の保存は同じ要求で再確認してください。" },
  };
}

/** HTTP stays in Express; validation, authorization and persistence live in Python. */
export class InputApiGateway {
  private worker: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, { resolve: (result: WorkerResult) => void; timer: ReturnType<typeof setTimeout> }>();

  constructor(private readonly repositoryRoot: string, private readonly csvPath: string) {}

  private start(): ChildProcessWithoutNullStreams {
    if (this.worker) return this.worker;
    const localPython = path.join(this.repositoryRoot, ".venv", "bin", "python");
    const python = process.env.CAPTION_API_PYTHON || (fs.existsSync(localPython) ? localPython : "python3");
    const worker = spawn(python, ["-u", "-m", "src.app.entrypoints.input_api_worker", "--csv-path", this.csvPath], {
      cwd: this.repositoryRoot,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.worker = worker;
    worker.stderr.resume(); // Credentials and private paths never enter HTTP responses/logs.
    const lines = readline.createInterface({ input: worker.stdout });
    lines.on("line", (line) => {
      try {
        const result = JSON.parse(line) as WorkerResult;
        const waiting = typeof result.id === "string" ? this.pending.get(result.id) : undefined;
        if (waiting && Number.isInteger(result.status) && result.status >= 100 && result.status <= 599) {
          clearTimeout(waiting.timer);
          this.pending.delete(result.id!);
          waiting.resolve(result);
        }
      } catch {
        worker.kill();
      }
    });
    const failed = () => {
      if (this.worker !== worker) return;
      this.worker = null;
      for (const entry of this.pending.values()) {
        clearTimeout(entry.timer);
        entry.resolve(unavailable());
      }
      this.pending.clear();
      lines.close();
    };
    worker.on("error", failed);
    worker.on("exit", failed);
    worker.stdin.on("error", failed);
    return worker;
  }

  call(req: Request, extra: Record<string, unknown> = {}): Promise<WorkerResult> {
    if (this.pending.size >= 32) return Promise.resolve(unavailable());
    let body: string;
    try {
      body = Buffer.isBuffer(req.body)
        ? new TextDecoder("utf-8", { fatal: true }).decode(req.body)
        : req.body === undefined ? "" : JSON.stringify(req.body);
    } catch {
      return Promise.resolve({ status: 400, headers: { "Content-Type": "application/problem+json", "Cache-Control": "no-store" },
        body: { type: "about:blank", title: "Bad Request", status: 400, code: "invalid_request",
          instance: `urn:uuid:${randomUUID()}`, detail: "UTF-8のJSONを送信してください。" } });
    }
    const worker = this.start();
    const id = randomUUID();
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        resolve(unavailable()); // Do not abort a possibly committed write or invent a new key.
      }, 30_000);
      this.pending.set(id, { resolve, timer });
      const packet = { id, method: req.method, path: req.path, headers: req.headers, body,
        local_peer: ["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(req.socket.remoteAddress || ""),
        secure: req.secure, peer: req.ip || req.socket.remoteAddress || "local", ...extra };
      worker.stdin.write(JSON.stringify(packet) + "\n", (error) => {
        if (error) {
          const item = this.pending.get(id);
          if (item) {
            clearTimeout(item.timer);
            this.pending.delete(id);
            item.resolve(unavailable());
          }
        }
      });
    });
  }

  send(res: Response, result: WorkerResult): void {
    for (const [name, value] of Object.entries(result.headers)) res.setHeader(name, value);
    res.status(result.status);
    if (result.body === null || result.status === 204) res.end();
    else res.json(result.body);
  }

  close(): void {
    this.worker?.kill();
  }
}
