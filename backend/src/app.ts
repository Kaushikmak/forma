import cors from "cors";
import express, { Express } from "express";
import fs from "fs";
import path from "path";
import { createJobsController } from "./controllers/jobs.controller.js";
import { createOutputController } from "./controllers/output.controller.js";
import { getStyles } from "./controllers/styles.controller.js";
import { createUploadController } from "./controllers/upload.controller.js";
import {
  DatabaseService,
  MemoryDatabaseService,
  PostgresService,
} from "./services/db.js";
import {
  LocalQueueService,
  QueueService,
  RedisQueueService,
} from "./services/queue.js";
import {
  StorageService,
  SupabaseStorageService,
} from "./services/storage.js";
import { StorageCleanupService } from "./services/cleaner.js";
import { QuotaService } from "./services/quota.js";
import { WorkerSupervisor } from "./services/supervisor.js";
import { Redis } from "ioredis";
import crypto from "crypto";

export interface AppOptions {
  storageDir?: string;
  workerScript?: string;
  storageService?: StorageService;
  dbService?: DatabaseService;
  queueService?: QueueService;
  quotaService?: QuotaService;
  cleanerService?: StorageCleanupService;
  enableCleanupDaemon?: boolean;
  autoStartWorker?: boolean;
  supabaseUrl?: string;
  supabaseKey?: string;
  databaseUrl?: string;
  redisUrl?: string;
  redisPrefix?: string;
}

function resolveProjectRoot(): string {
  if (fs.existsSync(path.resolve(process.cwd(), "lego_core/worker.py"))) {
    return process.cwd();
  }
  if (fs.existsSync(path.resolve(process.cwd(), "../lego_core/worker.py"))) {
    return path.resolve(process.cwd(), "..");
  }
  return process.cwd();
}

export function createApp(options?: AppOptions): Express {
  const app = express();

  const projectRoot = resolveProjectRoot();
  const storageDir =
    options?.storageDir || path.resolve(projectRoot, ".forma_storage");
  const workerScript =
    options?.workerScript || path.resolve(projectRoot, "lego_core/worker.py");

  const supabaseUrl =
    options?.supabaseUrl ||
    process.env.SUPABASE_URL ||
    "https://pkohbeuqtfbbwbfkxear.supabase.co";
  const supabaseKey =
    options?.supabaseKey ||
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_ANON_KEY ||
    "mock-key";

  let storage: StorageService;
  if (options?.storageService) {
    storage = options.storageService;
  } else {
    storage = new SupabaseStorageService(supabaseUrl, supabaseKey, storageDir);
    console.log(`[Forma Backend] Supabase Storage connected (${supabaseUrl})`);
  }

  const databaseUrl =
    options?.databaseUrl !== undefined
      ? options.databaseUrl
      : process.env.DATABASE_URL;
  let db: DatabaseService;
  if (options?.dbService) {
    db = options.dbService;
  } else if (databaseUrl) {
    db = new PostgresService(databaseUrl);
    db.init()
      .then(() =>
        console.log(
          `[Forma Backend] Supabase PostgreSQL connected and schema verified`,
        ),
      )
      .catch((err) =>
        console.warn(
          `[Forma Backend] Supabase PostgreSQL connection warning:`,
          err,
        ),
      );
  } else {
    db = new MemoryDatabaseService();
  }

  const quota = options?.quotaService || new QuotaService(db);

  let queue: QueueService;
  let supervisor: WorkerSupervisor | null = null;
  if (options?.queueService) {
    queue = options.queueService;
  } else {
    const useRedis =
      options?.redisUrl !== undefined
        ? Boolean(options.redisUrl)
        : (process.env.QUEUE_DRIVER === "redis" && Boolean(process.env.REDIS_URL));
    if (useRedis) {
      const redisUrl =
        options?.redisUrl || process.env.REDIS_URL || "redis://localhost:6379";
      const redis = new Redis(redisUrl, {
        lazyConnect: false,
        maxRetriesPerRequest: 3,
      });
      const prefix =
        options?.redisPrefix || process.env.REDIS_PREFIX || "mosaic";
      queue = new RedisQueueService(redis, prefix, db, storage, storageDir, quota);
      const maskedUrl = redisUrl.replace(/:\/\/([^:]+):([^@]+)@/, "://$1:***@");
      console.log(
        `[Forma Backend] Redis queue connected (${maskedUrl}, prefix: ${prefix})`,
      );

      const shouldAutoStart =
        options?.autoStartWorker !== undefined
          ? options.autoStartWorker
          : process.env.AUTO_START_WORKER !== "false" && !process.env.VITEST;

      if (shouldAutoStart) {
        supervisor = new WorkerSupervisor({
          workerScript,
          redisUrl,
          prefix,
          storageDir,
        });
        supervisor.start();
      }
    } else {
      queue = new LocalQueueService(storage, storageDir, workerScript, db, quota);
      console.log(`[Forma Backend] Local process queue connected`);
    }
  }

  const uploadCtrl = createUploadController(storage, db);
  const jobsCtrl = createJobsController(queue, storage, db, quota);
  const outputCtrl = createOutputController(storage);

  // Storage & Database Cleanup Daemon
  const cleaner =
    options?.cleanerService ||
    new StorageCleanupService({
      storage,
      db,
      storageDir,
    });

  if (options?.enableCleanupDaemon !== false) {
    cleaner.start();
  }

  app.use(cors());

  app.get("/api/health", (_req, res) => {
    res.json({
      status: "ok",
      timestamp: Date.now(),
      storage: storage instanceof SupabaseStorageService ? "supabase" : "custom",
      database: db instanceof PostgresService ? "postgres" : "memory",
      queue: queue instanceof RedisQueueService ? "redis" : "local",
      workerSupervisor: supervisor
        ? supervisor.isRunning()
          ? "running"
          : "stopped"
        : "disabled",
      cleanup: cleaner.getStats(),
    });
  });

  app.get("/api/cleanup", (_req, res) => {
    res.json(cleaner.getStats());
  });

  app.post("/api/cleanup", async (_req, res) => {
    try {
      const stats = await cleaner.cleanupNow();
      res.json(stats);
    } catch (err: any) {
      res.status(500).json({ error: err.message || "Cleanup failed" });
    }
  });

  app.get("/api/styles", getStyles);

  app.get("/api/quota", async (req, res) => {
    const headerDeviceId = req.headers["x-device-id"];
    const cookieDeviceId = req.headers.cookie
      ?.split(";")
      .map((c) => c.trim())
      .find((c) => c.startsWith("forma_device_id="))
      ?.split("=")[1];
    const deviceId =
      (typeof headerDeviceId === "string" && headerDeviceId.trim()) ||
      cookieDeviceId ||
      (typeof req.query.deviceId === "string" && req.query.deviceId.trim()) ||
      crypto.randomBytes(16).toString("hex");

    const clientIp =
      (typeof req.headers["x-forwarded-for"] === "string"
        ? req.headers["x-forwarded-for"].split(",")[0].trim()
        : req.ip) || "127.0.0.1";

    try {
      const info = await quota.getQuota(deviceId, clientIp);
      res.setHeader(
        "Set-Cookie",
        `forma_device_id=${deviceId}; Path=/; Max-Age=31536000; SameSite=Lax`
      );
      res.json(info);
    } catch (err: any) {
      res.status(500).json({ error: err.message || "Failed to retrieve quota" });
    }
  });

  app.post("/api/upload-slot", express.json(), uploadCtrl.requestUploadSlot);
  app.put("/api/uploads/:id", uploadCtrl.handleDirectUpload);

  app.post("/api/jobs", express.json(), jobsCtrl.createJob);
  app.get("/api/jobs/:id", jobsCtrl.getJob);
  app.get("/api/jobs/:id/events", jobsCtrl.streamJobEvents);
  app.post("/api/jobs/:id/cancel", jobsCtrl.cancelJob);

  app.get("/api/outputs/:jobId/:filename", outputCtrl.getOutput);

  return app;
}
