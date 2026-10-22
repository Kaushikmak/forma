import crypto from "crypto";
import { Request, Response } from "express";
import { z } from "zod";
import { DatabaseService } from "../services/db.js";
import { QueueService } from "../services/queue.js";
import { StorageService } from "../services/storage.js";
import { QuotaService } from "../services/quota.js";
import { JobEnvelope, JobState, JobStatus } from "../types/contract.js";
import { assetSlots } from "./upload.controller.js";

const LegoParamsSchema = z.object({
  style: z.literal("lego").default("lego"),
  width: z.number().int().min(16).max(256).default(64),
  tileSize: z.union([z.literal(8), z.literal(12), z.literal(16), z.literal(24), z.literal(32)]).default(16),
  palette: z
    .enum([
      "classic",
      "extended",
      "monochrome",
      "pastel",
      "crayon",
      "earth",
      "cool",
      "warm",
    ])
    .default("classic"),
  quality: z.enum(["standard", "high", "maximum"]).default("high"),
  fps: z.enum(["original", "24", "30", "60"]).default("original"),
  bitrateMbps: z.number().min(0.5).max(20.0).optional(),
});

const AsciiParamsSchema = z.object({
  style: z.literal("ascii").default("ascii"),
  width: z.number().int().min(16).max(256).default(64),
  tileSize: z
    .union([
      z.literal(8),
      z.literal(12),
      z.literal(16),
      z.literal(24),
      z.literal(32),
    ])
    .default(16),
  cellSize: z
    .union([
      z.literal(8),
      z.literal(12),
      z.literal(16),
      z.literal(24),
      z.literal(32),
    ])
    .optional(),
  palette: z
    .enum([
      "mild",
      "vibrant",
      "dark",
      "matrix",
      "amber",
      "cyberpunk",
      "monochrome",
      "retro",
      "pastel",
      "nord",
      "gameboy",
      "classic",
      "extended",
      "crayon",
      "earth",
      "cool",
      "warm",
    ])
    .default("mild"),
  ramp: z.string().default("default"),
  quality: z.enum(["standard", "high", "maximum"]).default("high"),
  fps: z.enum(["original", "24", "30", "60"]).default("original"),
  strength: z.number().min(0.0).max(1.0).optional(),
  contrast: z.number().optional(),
  saturation: z.number().optional(),
  gamma: z.number().optional(),
  skipWhite: z.number().int().optional(),
  autoLevels: z.boolean().optional(),
  invert: z.boolean().optional(),
  smooth: z.number().optional(),
  writeTxt: z.boolean().optional(),
  bitrateMbps: z.number().min(0.5).max(20.0).optional(),
});

const JobParamsSchema = z.union([LegoParamsSchema, AsciiParamsSchema]);

const CreateJobSchema = z.object({
  style: z.string().optional(),
  assetId: z.string().min(1).optional(),
  input: z
    .object({
      storageKey: z.string().min(1),
      assetId: z.string().optional(),
    })
    .optional(),
  params: JobParamsSchema.default({
    style: "lego",
    width: 64,
    tileSize: 16,
    palette: "classic",
    quality: "high",
    fps: "original",
  }),
  limits: z
    .object({
      maxBytes: z.number().optional(),
      maxPixels: z.number().optional(),
      maxFrames: z.number().optional(),
      maxDurationSec: z.number().optional(),
      maxFps: z.number().optional(),
      timeoutSec: z.number().optional(),
    })
    .optional(),
});

export function createJobsController(
  queue: QueueService,
  storage: StorageService,
  db?: DatabaseService,
  quotaService?: QuotaService
) {
  const uploadBucket = process.env.SUPABASE_UPLOAD_BUCKET || "upload";
  const resultsBucket = process.env.SUPABASE_RESULTS_BUCKET || "results";

  return {
    async createJob(req: Request, res: Response) {
      const parseResult = CreateJobSchema.safeParse(req.body);
      if (!parseResult.success) {
        res.status(400).json({
          status: "rejected",
          errorCode: "INVALID_PARAMS",
          errorMessage: parseResult.error.message,
        });
        return;
      }

      const { params = { style: "lego", width: 64, tileSize: 16, palette: "classic", quality: "high", fps: "original" }, limits } = parseResult.data;
      const assetId = parseResult.data.assetId || parseResult.data.input?.assetId || (parseResult.data.input?.storageKey ? parseResult.data.input.storageKey.split("/")[1] : "");

      if (!assetId) {
        res.status(400).json({
          status: "rejected",
          errorCode: "INVALID_PARAMS",
          errorMessage: "Missing assetId or input.storageKey.",
        });
        return;
      }

      const inputKey = `uploads/${assetId}/input`;

      // Check existence in upload bucket or fallback uploads bucket
      let exists = await storage.exists(uploadBucket, inputKey);
      let targetInputBucket = uploadBucket;
      if (!exists) {
        exists = await storage.exists("uploads", inputKey);
        if (exists) targetInputBucket = "uploads";
      }

      if (!exists) {
        res.status(404).json({
          status: "rejected",
          errorCode: "INPUT_MISSING",
          errorMessage: `Uploaded asset not found: ${assetId}`,
        });
        return;
      }

      let slot = assetSlots.get(assetId);
      if (!slot && db) {
        const dbSlot = await db.getUploadSlot(assetId);
        if (dbSlot) slot = dbSlot;
      }

      const isVideo = slot?.mimeType.startsWith("video/");
      const lane = isVideo ? "video" : "image";
      const mediaKind = isVideo ? "video" : slot?.mimeType === "image/gif" ? "gif" : "image";
      const quotaKind: "image" | "video" = isVideo ? "video" : "image";

      // Resolve device ID & Client IP
      const headerDeviceId = req.headers["x-device-id"];
      const cookieDeviceId = req.headers.cookie
        ?.split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith("forma_device_id="))
        ?.split("=")[1];
      const deviceId =
        (typeof headerDeviceId === "string" && headerDeviceId.trim()) ||
        cookieDeviceId ||
        (req.body && typeof req.body.deviceId === "string" && req.body.deviceId.trim()) ||
        crypto.randomBytes(16).toString("hex");

      const clientIp =
        (typeof req.headers["x-forwarded-for"] === "string"
          ? req.headers["x-forwarded-for"].split(",")[0].trim()
          : req.ip) || "127.0.0.1";

      let currentQuota = undefined;
      if (quotaService) {
        const consumption = await quotaService.consumeCredit(deviceId, clientIp, quotaKind);
        if (!consumption.allowed) {
          res.status(429).json({
            status: "rejected",
            errorCode: "QUOTA_EXCEEDED",
            errorMessage: consumption.reason,
            quota: consumption.quota,
          });
          return;
        }
        currentQuota = consumption.quota;
      }

      const jobId = crypto.randomBytes(16).toString("hex");
      const now = Date.now();
      const expiresAt = now + 15 * 60 * 1000; // 15 mins expiration

      const envelope: JobEnvelope = {
        v: 1,
        jobId,
        style: (params.style as string) || "lego",
        params,
        deviceId,
        input: {
          bucket: targetInputBucket,
          key: inputKey,
        },
        output: {
          bucket: resultsBucket,
          prefix: `outputs/${jobId}/`,
        },
        mediaKind,
        limits,
        createdAt: now,
        expiresAt,
      };

      await queue.enqueue(lane, envelope);

      res.status(202).json({
        jobId,
        status: "queued",
        deviceId,
        quota: currentQuota,
      });
    },

    async getJob(req: Request, res: Response) {
      const jobId = req.params.id;
      let state = await queue.getJobState(jobId);

      if (!state && db) {
        state = await db.getJob(jobId);
      }

      if (!state) {
        res.status(404).json({ error: "Job not found" });
        return;
      }

      res.json(state);
    },

    async streamJobEvents(req: Request, res: Response) {
      const jobId = req.params.id;
      let initial = await queue.getJobState(jobId);
      if (!initial && db) {
        initial = await db.getJob(jobId);
      }

      // Set headers for Server-Sent Events (SSE)
      res.setHeader("Content-Type", "text/event-stream");
      res.setHeader("Cache-Control", "no-cache, no-transform");
      res.setHeader("Connection", "keep-alive");
      res.flushHeaders?.();

      const sendEvent = (state: JobState | Record<string, unknown>) => {
        res.write(`data: ${JSON.stringify(state)}\n\n`);
      };

      // Send current state if available
      if (initial) {
        sendEvent(initial);
        if (["done", "failed", "rejected", "cancelled", "expired"].includes(initial.status)) {
          setTimeout(() => {
            try {
              res.end();
            } catch {}
          }, 100);
          return;
        }
      }

      const unsubscribe = queue.subscribeJobEvents(jobId, (state) => {
        sendEvent(state);

        // Once terminal status is reached, close the stream
        if (["done", "failed", "rejected", "cancelled", "expired"].includes(state.status)) {
          unsubscribe();
          setTimeout(() => {
            try {
              res.end();
            } catch {}
          }, 100);
        }
      });

      req.on("close", () => {
        unsubscribe();
      });
    },

    async cancelJob(req: Request, res: Response) {
      const jobId = req.params.id;
      await queue.cancelJob(jobId);
      res.status(200).json({ ok: true, status: "cancelled", jobId });
    },
  };
}
