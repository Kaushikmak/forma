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
  private child: ChildProcess | null = null;
  private isShuttingDown = false;
  private restartTimer: NodeJS.Timeout | null = null;
  private options: WorkerSupervisorOptions;
  private isStarted = false;

  constructor(options: WorkerSupervisorOptions) {
    this.options = options;
  }

  public start(): void {
    if (this.isStarted) return;
    this.isStarted = true;
    this.isShuttingDown = false;
    this.spawnWorker();

    const cleanup = () => this.stop();
    process.once("SIGINT", cleanup);
    process.once("SIGTERM", cleanup);
    process.once("exit", cleanup);
  }

  private maskUrl(url: string): string {
    return url.replace(/:\/\/([^:]+):([^@]+)@/, "://$1:***@");
  }

  private spawnWorker(): void {
    if (this.isShuttingDown) return;

    const lanes = this.options.lanes?.join(",") || "image,video";
    const groupName = this.options.groupName || "mosaic-workers";
    const scriptPath = path.resolve(this.options.workerScript);

    if (!fs.existsSync(scriptPath)) {
      console.warn(`[Worker Supervisor] Worker script not found at ${scriptPath}`);
      return;
    }

    const args = [
      scriptPath,
      "--consume",
      lanes,
      "--prefix",
      this.options.prefix,
      "--group-name",
      groupName,
      "--storage-root",
      this.options.storageDir,
    ];

    const maskedUrl = this.maskUrl(this.options.redisUrl);
    console.log(
      `[Worker Supervisor] Launching Python worker consumer for lanes [${lanes}] (${maskedUrl})...`
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

    this.child = child;

    child.stdout?.on("data", (chunk: Buffer) => {
      const msg = chunk.toString().trim();
      if (msg) {
        console.log(`[Worker] ${this.maskUrl(msg)}`);
      }
    });

    child.stderr?.on("data", (chunk: Buffer) => {
      const msg = chunk.toString().trim();
      if (msg) {
        console.warn(`[Worker] ${this.maskUrl(msg)}`);
      }
    });

    child.on("close", (code, signal) => {
      this.child = null;
      if (!this.isShuttingDown) {
        console.warn(
          `[Worker Supervisor] Worker exited (code: ${code}, signal: ${signal}). Auto-restarting in 2s...`
        );
        this.restartTimer = setTimeout(() => {
          this.spawnWorker();
        }, 2000);
      }
    });

    child.on("error", (err) => {
      console.warn(`[Worker Supervisor] Failed to spawn worker:`, err);
    });
  }

  public stop(): void {
    this.isShuttingDown = true;
    this.isStarted = false;

    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }

    if (this.child) {
      try {
        this.child.kill("SIGTERM");
      } catch {
        // ignore
      }
      this.child = null;
    }
  }

  public isRunning(): boolean {
    return this.child !== null && !this.child.killed;
  }

  public getChild(): ChildProcess | null {
    return this.child;
  }
}
