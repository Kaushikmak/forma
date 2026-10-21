import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";

export interface WorkerSupervisorOptions {
  workerScript: string;
  redisUrl: string;
  prefix: string;
  storageDir: string;
  lanes?: string[];
  groupName?: string;
}

export class WorkerSupervisor {
  private children = new Map<string, ChildProcess>();
  private restartTimers = new Map<string, NodeJS.Timeout>();
  private isShuttingDown = false;
  private options: WorkerSupervisorOptions;
  private isStarted = false;

  constructor(options: WorkerSupervisorOptions) {
    this.options = options;
  }

  public start(): void {
    if (this.isStarted) return;
    this.isStarted = true;
    this.isShuttingDown = false;

    const lanes = this.options.lanes || ["image", "video"];
    for (const lane of lanes) {
      this.spawnWorkerForLane(lane);
    }

    const cleanup = () => this.stop();
    process.once("SIGINT", cleanup);
    process.once("SIGTERM", cleanup);
    process.once("exit", cleanup);
  }

  private maskUrl(url: string): string {
    return url.replace(/:\/\/([^:]+):([^@]+)@/, "://$1:***@");
  }

  private spawnWorkerForLane(lane: string): void {
    if (this.isShuttingDown) return;

    const groupName = this.options.groupName || "mosaic-workers";
    const scriptPath = path.resolve(this.options.workerScript);

    if (!fs.existsSync(scriptPath)) {
      console.warn(`[Worker Supervisor] Worker script not found at ${scriptPath}`);
      return;
    }

    const args = [
      scriptPath,
      "--consume",
      lane,
      "--prefix",
      this.options.prefix,
      "--group-name",
      groupName,
      "--consumer-name",
      `worker-${lane}-${process.pid}`,
      "--storage-root",
      this.options.storageDir,
    ];

    const maskedUrl = this.maskUrl(this.options.redisUrl);
    console.log(
      `[Worker Supervisor] Launching Python worker consumer for lane [${lane}] (${maskedUrl})...`
    );

    const child = spawn("python3", args, {
      env: {
        ...process.env,
        PYTHONPATH: path.dirname(scriptPath),
        REDIS_URL: this.options.redisUrl,
        REDIS_PREFIX: this.options.prefix,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });

    this.children.set(lane, child);

    child.stdout?.on("data", (chunk: Buffer) => {
      const msg = chunk.toString().trim();
      if (msg) {
        console.log(`[Worker:${lane}] ${this.maskUrl(msg)}`);
      }
    });

    child.stderr?.on("data", (chunk: Buffer) => {
      const msg = chunk.toString().trim();
      if (msg) {
        console.warn(`[Worker:${lane}] ${this.maskUrl(msg)}`);
      }
    });

    child.on("close", (code, signal) => {
      this.children.delete(lane);
      if (!this.isShuttingDown) {
        console.warn(
          `[Worker Supervisor] Worker for lane [${lane}] exited (code: ${code}, signal: ${signal}). Auto-restarting in 2s...`
        );
        const timer = setTimeout(() => {
          this.spawnWorkerForLane(lane);
        }, 2000);
        this.restartTimers.set(lane, timer);
      }
    });

    child.on("error", (err) => {
      console.warn(`[Worker Supervisor] Failed to spawn worker for lane [${lane}]:`, err);
    });
  }

  public stop(): void {
    this.isShuttingDown = true;
    this.isStarted = false;

    for (const timer of this.restartTimers.values()) {
      clearTimeout(timer);
    }
    this.restartTimers.clear();

    for (const child of this.children.values()) {
      try {
        child.kill("SIGTERM");
        setTimeout(() => {
          try {
            child.kill("SIGKILL");
          } catch {}
        }, 3000).unref();
      } catch {
        // ignore
      }
    }
    this.children.clear();
  }

  public isRunning(): boolean {
    for (const child of this.children.values()) {
      if (!child.killed) return true;
    }
    return false;
  }

  public getChild(): ChildProcess | null {
    for (const child of this.children.values()) {
      return child;
    }
    return null;
  }
}
