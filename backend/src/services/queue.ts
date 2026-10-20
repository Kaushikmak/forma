import { EventEmitter } from "events";
import { spawn, ChildProcess } from "child_process";
import fs from "fs";
import path from "path";
import readline from "readline";
import { Redis } from "ioredis";
import { DatabaseService } from "./db.js";
import { JobEnvelope, JobState, TerminalStatus } from "../types/contract.js";
import { StorageService } from "./storage.js";
import { QuotaService } from "./quota.js";

export interface QueueService {
  enqueue(lane: "image" | "video", envelope: JobEnvelope): Promise<void>;
  getJobState(jobId: string): Promise<JobState | null>;
  updateJobState(jobId: string, updates: Partial<JobState>): Promise<void>;
  cancelJob(jobId: string): Promise<void>;
  subscribeJobEvents(
    jobId: string,
    listener: (event: JobState) => void,
  ): () => void;
  publishJobEvent(jobId: string, event: JobState): void;
}

export class LocalQueueService implements QueueService {
  private jobs = new Map<string, JobState>();
  private activeProcesses = new Map<string, ChildProcess>();
  private emitter = new EventEmitter();
  private storage: StorageService;
  private pythonWorkerScript: string;
  private storageRootDir: string;
  private db?: DatabaseService;
  private quotaService?: QuotaService;

  constructor(
    storage: StorageService,
    storageRootDir: string,
    workerScriptPath?: string,
    db?: DatabaseService,
    quotaService?: QuotaService,
  ) {
    this.storage = storage;
    this.storageRootDir = path.resolve(storageRootDir);
    this.pythonWorkerScript = workerScriptPath
      ? path.resolve(workerScriptPath)
      : fs.existsSync(path.resolve(process.cwd(), "lego_core/worker.py"))
        ? path.resolve(process.cwd(), "lego_core/worker.py")
        : path.resolve(process.cwd(), "../lego_core/worker.py");
    this.db = db;
    this.quotaService = quotaService;
  }

  async getJobState(jobId: string): Promise<JobState | null> {
    const memoryJob = this.jobs.get(jobId);
    if (memoryJob) return memoryJob;
    if (this.db) {
      const dbJob = await this.db.getJob(jobId);
      if (dbJob) {
        this.jobs.set(jobId, dbJob);
        return dbJob;
      }
    }
    return null;
  }

  async updateJobState(
    jobId: string,
    updates: Partial<JobState>,
  ): Promise<void> {
    const current = this.jobs.get(jobId) || {
      jobId,
      status: "queued",
      progress: 0,
      updatedAt: Date.now(),
      attempts: 1,
    };

    const updated: JobState = {
      ...current,
      ...updates,
      updatedAt: Date.now(),
    };

    if (
      this.quotaService &&
      !current.refunded &&
      current.deviceId &&
      ["failed", "rejected", "cancelled"].includes(updated.status)
    ) {
      updated.refunded = true;
      const mediaKind = current.mediaKind === "video" ? "video" : "image";
      this.quotaService
        .refundCredit(current.deviceId, mediaKind)
        .catch((err) => {
          console.warn("[Queue] Error refunding quota on job failure:", err);
        });
    }

    this.jobs.set(jobId, updated);
    this.publishJobEvent(jobId, updated);

    if (this.db) {
      try {
        await this.db.saveJob(updated);
      } catch (err) {
        console.warn("[Queue] Failed to persist job update to DB:", err);
      }
    }
  }

  async cancelJob(jobId: string): Promise<void> {
    const child = this.activeProcesses.get(jobId);
    if (child) {
      try {
        child.kill("SIGTERM");
      } catch {
        // process might have already exited
      }
      this.activeProcesses.delete(jobId);
    }

    await this.updateJobState(jobId, {
      status: "cancelled",
      errorCode: "CANCELLED",
      errorMessage: "Job was cancelled by client.",
    });
  }

  subscribeJobEvents(
    jobId: string,
    listener: (event: JobState) => void,
  ): () => void {
    const eventName = `job:${jobId}`;
    this.emitter.on(eventName, listener);
    return () => {
      this.emitter.off(eventName, listener);
    };
  }

  publishJobEvent(jobId: string, event: JobState): void {
    this.emitter.emit(`job:${jobId}`, event);
  }

  async enqueue(
    _lane: "image" | "video",
    envelope: JobEnvelope,
  ): Promise<void> {
    const initialState: JobState = {
      jobId: envelope.jobId,
      status: "queued",
      progress: 0,
      updatedAt: Date.now(),
      attempts: 1,
      deviceId: envelope.deviceId,
      mediaKind: envelope.mediaKind,
    };

    this.jobs.set(envelope.jobId, initialState);
    this.publishJobEvent(envelope.jobId, initialState);
    if (this.db) {
      try {
        await this.db.saveJob(initialState);
      } catch (err) {
        console.warn("[Queue] Failed to save initial job to DB:", err);
      }
    }

    setImmediate(() => {
      this.executeJob(envelope);
    });
  }

  private async executeJob(envelope: JobEnvelope): Promise<void> {
    const jobId = envelope.jobId;

    try {
      if (typeof this.storage.ensureLocalFile === "function") {
        try {
          await this.storage.ensureLocalFile(
            envelope.input.bucket,
            envelope.input.key,
          );
        } catch (err) {
          await this.updateJobState(jobId, {
            status: "rejected",
            errorCode: "INPUT_MISSING",
            errorMessage: `Failed to retrieve input file from storage: ${err instanceof Error ? err.message : String(err)}`,
          });
          return;
        }
      }

      const child = spawn(
        "python3",
        [
          this.pythonWorkerScript,
          "--job",
          JSON.stringify(envelope),
          "--storage-root",
          this.storageRootDir,
        ],
        {
          env: {
            ...process.env,
            PYTHONPATH: path.dirname(this.pythonWorkerScript),
          },
        },
      );

      this.activeProcesses.set(jobId, child);

      const rl = readline.createInterface({
        input: child.stdout,
        crlfDelay: Infinity,
      });

      rl.on("line", async (line) => {
        try {
          const event = JSON.parse(line.trim());
          if (event && event.status) {
            let resultUrl = event.resultKey
              ? `/api/outputs/${jobId}/${path.basename(event.resultKey)}`
              : undefined;

            // If job completed, upload result to remote storage
            if (event.status === "done" && event.resultKey) {
              const localResultPath = path.join(
                this.storageRootDir,
                event.resultKey,
              );
              if (fs.existsSync(localResultPath)) {
                try {
                  const fileBuffer =
                    await fs.promises.readFile(localResultPath);
                  await this.storage.save(
                    envelope.output.bucket,
                    event.resultKey,
                    fileBuffer,
                    event.contentType,
                  );

                  if (typeof this.storage.createSignedUrl === "function") {
                    resultUrl = await this.storage.createSignedUrl(
                      envelope.output.bucket,
                      event.resultKey,
                      86400,
                    );
                  }
                } catch (saveErr) {
                  console.warn(
                    "[Queue] Error uploading result to destination bucket:",
                    saveErr,
                  );
                }
              }
            }

            await this.updateJobState(jobId, {
              status: event.status,
              progress:
                typeof event.progress === "number" ? event.progress : undefined,
              mediaKind: event.mediaKind,
              inputWidth: event.inputWidth,
              inputHeight: event.inputHeight,
              resultBucket: event.resultBucket,
              resultKey: event.resultKey,
              resultUrl,
              contentType: event.contentType,
              width: event.width,
              height: event.height,
              frames: event.frames,
              durationSec: event.durationSec,
              bytes: event.bytes,
              processingMs: event.processingMs,
              errorCode: event.errorCode,
              errorMessage: event.errorMessage,
            });
          }
        } catch {
          // ignore non-json log lines
        }
      });

      let stderrOutput = "";
      child.stderr.on("data", (chunk) => {
        stderrOutput += chunk.toString();
      });

      child.on("close", async (code) => {
        this.activeProcesses.delete(jobId);
        const currentState = this.jobs.get(jobId);

        if (
          currentState &&
          ["done", "failed", "rejected", "cancelled", "expired"].includes(
            currentState.status,
          )
        ) {
          return;
        }

        if (code !== 0) {
          await this.updateJobState(jobId, {
            status: "failed",
            errorCode: "INTERNAL",
            errorMessage: `Worker process exited with code ${code}. Stderr: ${stderrOutput.slice(-200)}`,
          });
        }
      });

      child.on("error", async (err) => {
        this.activeProcesses.delete(jobId);
        await this.updateJobState(jobId, {
          status: "failed",
          errorCode: "INTERNAL",
          errorMessage: `Worker execution error: ${err.message}`,
        });
      });
    } catch (err) {
      this.activeProcesses.delete(jobId);
      await this.updateJobState(jobId, {
        status: "failed",
        errorCode: "INTERNAL",
        errorMessage: `Failed to launch job worker: ${err instanceof Error ? err.message : String(err)}`,
      });
    }
  }
}

export class RedisQueueService implements QueueService {
  private redis: Redis;
  private subRedis: Redis;
  private prefix: string;
  private db?: DatabaseService;
  private storage?: StorageService;
  private storageRootDir?: string;
  private quotaService?: QuotaService;
  private emitter = new EventEmitter();

  constructor(
    redisClient: Redis,
    prefix: string = "mosaic",
    db?: DatabaseService,
    storage?: StorageService,
    storageRootDir?: string,
    quotaService?: QuotaService,
  ) {
    this.redis = redisClient;
    this.subRedis = redisClient.duplicate();
    this.prefix = prefix;
    this.db = db;
    this.storage = storage;
    this.storageRootDir = storageRootDir
      ? path.resolve(storageRootDir)
      : undefined;
    this.quotaService = quotaService;

    // Listen on Pub/Sub messages and emit locally for SSE handlers
    this.subRedis.on("message", async (channel: string, message: string) => {
      try {
        const event = JSON.parse(message);
        const match = channel.match(
          new RegExp(`^${this.prefix}:job:(.+):events$`),
        );
        if (match && match[1]) {
          const jobId = match[1];

          // If job done and resultKey exists, ensure resultUrl and remote upload if needed
          if (event.status === "done" && event.resultKey && this.storage) {
            const bucket = event.resultBucket || "Results";
            if (this.storageRootDir) {
              const localResultPath = path.join(
                this.storageRootDir,
                event.resultKey,
              );
              if (fs.existsSync(localResultPath)) {
                try {
                  const fileBuffer =
                    await fs.promises.readFile(localResultPath);
                  await this.storage.save(
                    bucket,
                    event.resultKey,
                    fileBuffer,
                    event.contentType,
                  );
                } catch (saveErr) {
                  console.warn(
                    "[RedisQueue] Error uploading result to destination bucket:",
                    saveErr,
                  );
                }
              }
            }

            if (typeof (this.storage as any).createSignedUrl === "function") {
              try {
                event.resultUrl = await (this.storage as any).createSignedUrl(
                  bucket,
                  event.resultKey,
                  86400,
                );
                const hashKey = `${this.prefix}:job:${jobId}`;
                await this.redis.hset(hashKey, { resultUrl: event.resultUrl });
              } catch (urlErr) {
                console.warn(
                  "[RedisQueue] Error generating signed URL:",
                  urlErr,
                );
              }
            }
          }

          if (!event.resultUrl && event.resultKey) {
            event.resultUrl = `/api/outputs/${jobId}/${path.basename(event.resultKey)}`;
          }

          this.emitter.emit(`job:${jobId}`, event);

          if (this.db) {
            try {
              await this.db.saveJob(event);
            } catch (err) {
              console.warn(
                `[RedisQueue] Failed to persist event to DB for job ${jobId}:`,
                err,
              );
            }
          }
        }
      } catch {
        // ignore malformed message
      }
    });
  }

  async enqueue(lane: "image" | "video", envelope: JobEnvelope): Promise<void> {
    const jobId = envelope.jobId;
    const now = Date.now();
    const hashKey = `${this.prefix}:job:${jobId}`;

    // Pre-cache input locally if storage provides ensureLocalFile
    if (
      this.storage &&
      typeof (this.storage as any).ensureLocalFile === "function"
    ) {
      try {
        await (this.storage as any).ensureLocalFile(
          envelope.input.bucket,
          envelope.input.key,
        );
      } catch (err) {
        console.warn("[RedisQueue] Pre-cache input warning:", err);
      }
    }
    // Initialize job state hash in Redis with TTL (20 minutes)
    await this.redis.hset(hashKey, {
      jobId,
      status: "queued",
      progress: "0",
      updatedAt: String(now),
      attempts: "0",
      cancel: "0",
      deviceId: envelope.deviceId || "",
      mediaKind: envelope.mediaKind || "",
    });
    await this.redis.expire(hashKey, 20 * 60);

    // Add message to Redis Stream
    const streamKey = `${this.prefix}:jobs:${lane}`;
    await this.redis.xadd(streamKey, "*", "data", JSON.stringify(envelope));

    // Emit initial event to PubSub & memory emitter
    const initialState: JobState = {
      jobId,
      status: "queued",
      progress: 0,
      updatedAt: now,
      attempts: 0,
      deviceId: envelope.deviceId,
      mediaKind: envelope.mediaKind,
    };
    this.publishJobEvent(jobId, initialState);

    // Persist to DB if available
    if (this.db) {
      try {
        await this.db.saveJob(initialState);
      } catch (err) {
        console.warn("[RedisQueue] Failed to save initial job to DB:", err);
      }
    }
  }

  async getJobState(jobId: string): Promise<JobState | null> {
    const hashKey = `${this.prefix}:job:${jobId}`;
    const hash = await this.redis.hgetall(hashKey);

    if (!hash || Object.keys(hash).length === 0) {
      if (this.db) {
        return await this.db.getJob(jobId);
      }
      return null;
    }

    const state: JobState = {
      jobId: hash.jobId || jobId,
      status: (hash.status as any) || "queued",
      progress: hash.progress !== undefined ? parseInt(hash.progress, 10) : 0,
      updatedAt:
        hash.updatedAt !== undefined
          ? parseInt(hash.updatedAt, 10)
          : Date.now(),
      attempts: hash.attempts !== undefined ? parseInt(hash.attempts, 10) : 0,
      cancel: hash.cancel ? parseInt(hash.cancel, 10) : 0,
      deviceId: hash.deviceId || undefined,
      mediaKind: (hash.mediaKind as any) || undefined,
      refunded: hash.refunded === "1",
      inputWidth: hash.inputWidth ? parseInt(hash.inputWidth, 10) : undefined,
      inputHeight: hash.inputHeight
        ? parseInt(hash.inputHeight, 10)
        : undefined,
      resultBucket: hash.resultBucket || undefined,
      resultKey: hash.resultKey || undefined,
      resultUrl:
        hash.resultUrl ||
        (hash.resultKey
          ? `/api/outputs/${jobId}/${path.basename(hash.resultKey)}`
          : undefined),
      contentType: hash.contentType || undefined,
      width: hash.width ? parseInt(hash.width, 10) : undefined,
      height: hash.height ? parseInt(hash.height, 10) : undefined,
      frames: hash.frames ? parseInt(hash.frames, 10) : undefined,
      durationSec: hash.durationSec ? parseFloat(hash.durationSec) : undefined,
      bytes: hash.bytes ? parseInt(hash.bytes, 10) : undefined,
      processingMs: hash.processingMs
        ? parseInt(hash.processingMs, 10)
        : undefined,
      errorCode: (hash.errorCode as any) || undefined,
      errorMessage: hash.errorMessage || undefined,
    };

    return state;
  }

  async updateJobState(
    jobId: string,
    updates: Partial<JobState>,
  ): Promise<void> {
    const hashKey = `${this.prefix}:job:${jobId}`;
    const serializedUpdates: Record<string, string> = {
      updatedAt: String(Date.now()),
    };

    for (const [key, value] of Object.entries(updates)) {
      if (value !== undefined) {
        serializedUpdates[key] = String(value);
      }
    }

    await this.redis.hset(hashKey, serializedUpdates);

    // Merge for event publication
    const current = await this.getJobState(jobId);
    if (current) {
      if (
        this.quotaService &&
        !current.refunded &&
        current.deviceId &&
        ["failed", "rejected", "cancelled"].includes(current.status)
      ) {
        await this.redis.hset(hashKey, { refunded: "1" });
        current.refunded = true;
        const mediaKind = current.mediaKind === "video" ? "video" : "image";
        this.quotaService
          .refundCredit(current.deviceId, mediaKind)
          .catch((err) => {
            console.warn(
              "[RedisQueue] Error refunding quota on job failure:",
              err,
            );
          });
      }

      this.publishJobEvent(jobId, current);
      if (this.db) {
        try {
          await this.db.saveJob(current);
        } catch (err) {
          console.warn("[RedisQueue] Failed to update job in DB:", err);
        }
      }
    }
  }

  async cancelJob(jobId: string): Promise<void> {
    const hashKey = `${this.prefix}:job:${jobId}`;
    await this.redis.hset(hashKey, {
      cancel: "1",
      status: "cancelled",
      errorCode: "CANCELLED",
      errorMessage: "Job was cancelled by client.",
      updatedAt: String(Date.now()),
    });

    const current = await this.getJobState(jobId);
    if (current) {
      if (this.quotaService && !current.refunded && current.deviceId) {
        await this.redis.hset(hashKey, { refunded: "1" });
        current.refunded = true;
        const mediaKind = current.mediaKind === "video" ? "video" : "image";
        this.quotaService
          .refundCredit(current.deviceId, mediaKind)
          .catch((err) => {
            console.warn(
              "[RedisQueue] Error refunding quota on cancellation:",
              err,
            );
          });
      }

      this.publishJobEvent(jobId, current);
      if (this.db) {
        try {
          await this.db.saveJob(current);
        } catch {
          // ignore
        }
      }
    }
  }

  subscribeJobEvents(
    jobId: string,
    listener: (event: JobState) => void,
  ): () => void {
    const channel = `${this.prefix}:job:${jobId}:events`;
    this.subRedis.subscribe(channel).catch((err) => {
      console.warn(`[RedisQueue] Error subscribing to ${channel}:`, err);
    });

    const eventName = `job:${jobId}`;
    this.emitter.on(eventName, listener);

    return () => {
      this.emitter.off(eventName, listener);
      if (this.emitter.listenerCount(eventName) === 0) {
        this.subRedis.unsubscribe(channel).catch(() => {});
      }
    };
  }

  publishJobEvent(jobId: string, event: JobState): void {
    const channel = `${this.prefix}:job:${jobId}:events`;
    this.redis.publish(channel, JSON.stringify(event)).catch((err) => {
      console.warn(`[RedisQueue] Failed to publish event on ${channel}:`, err);
    });
    this.emitter.emit(`job:${jobId}`, event);
  }

  async close(): Promise<void> {
    await this.subRedis.quit();
    await this.redis.quit();
  }
}
