import { DatabaseService, DeviceQuotaRecord } from "./db.js";

export interface QuotaOptions {
  windowMs?: number; // default: 30 minutes (30 * 60 * 1000)
  imageLimit?: number; // default: 30
  videoLimit?: number; // default: 10
  ipImageLimit?: number; // default: 60
  ipVideoLimit?: number; // default: 20
  ipMaxDevices?: number; // default: 5
}

export interface QuotaInfo {
  deviceId: string;
  images: {
    limit: number;
    used: number;
    remaining: number;
  };
  videos: {
    limit: number;
    used: number;
    remaining: number;
  };
  windowStart: number;
  resetAt: number;
  resetsInSeconds: number;
}

export interface ConsumeResult {
  allowed: boolean;
  remaining: number;
  resetAt: number;
  reason?: string;
  quota: QuotaInfo;
}

export class QuotaService {
  private db: DatabaseService;
  private windowMs: number;
  private imageLimit: number;
  private videoLimit: number;
  private ipImageLimit: number;
  private ipVideoLimit: number;
  private ipMaxDevices: number;

  constructor(db: DatabaseService, options?: QuotaOptions) {
    this.db = db;
    this.windowMs = options?.windowMs ?? 30 * 60 * 1000;
    this.imageLimit = options?.imageLimit ?? 30;
    this.videoLimit = options?.videoLimit ?? 10;
    this.ipImageLimit = options?.ipImageLimit ?? 60;
    this.ipVideoLimit = options?.ipVideoLimit ?? 20;
    this.ipMaxDevices = options?.ipMaxDevices ?? 5;
  }

  async getQuota(deviceId: string, ipAddress: string): Promise<QuotaInfo> {
    const now = Date.now();
    let record = await this.db.getDeviceQuota(deviceId);

    if (!record || now - record.windowStart >= this.windowMs) {
      record = {
        deviceId,
        ipAddress,
        windowStart: now,
        imagesUsed: 0,
        videosUsed: 0,
        updatedAt: now,
      };
      await this.db.saveDeviceQuota(record);
    }

    const resetAt = record.windowStart + this.windowMs;
    const resetsInSeconds = Math.max(0, Math.ceil((resetAt - now) / 1000));

    return {
      deviceId,
      images: {
        limit: this.imageLimit,
        used: record.imagesUsed,
        remaining: Math.max(0, this.imageLimit - record.imagesUsed),
      },
      videos: {
        limit: this.videoLimit,
        used: record.videosUsed,
        remaining: Math.max(0, this.videoLimit - record.videosUsed),
      },
      windowStart: record.windowStart,
      resetAt,
      resetsInSeconds,
    };
  }

  async consumeCredit(
    deviceId: string,
    ipAddress: string,
    mediaKind: "image" | "video",
  ): Promise<ConsumeResult> {
    const now = Date.now();

    // Check IP guard
    const cutoff = now - this.windowMs;
    const ipUsage = await this.db.getIpUsage(ipAddress, cutoff);

    let record = await this.db.getDeviceQuota(deviceId);
    const isNewDeviceForIp =
      !record || now - record.windowStart >= this.windowMs;

    if (isNewDeviceForIp && ipUsage.deviceCount >= this.ipMaxDevices) {
      const quota = await this.getQuota(deviceId, ipAddress);
      return {
        allowed: false,
        remaining: 0,
        resetAt: quota.resetAt,
        reason: `Network rate limit reached: too many devices active from your network in the last 30 minutes. Please wait before creating more jobs.`,
        quota,
      };
    }

    if (mediaKind === "image" && ipUsage.imagesUsed >= this.ipImageLimit) {
      const quota = await this.getQuota(deviceId, ipAddress);
      return {
        allowed: false,
        remaining: 0,
        resetAt: quota.resetAt,
        reason: `Network rate limit reached: image rendering limit exceeded for this network (max ${this.ipImageLimit} per 30 minutes).`,
        quota,
      };
    }

    if (mediaKind === "video" && ipUsage.videosUsed >= this.ipVideoLimit) {
      const quota = await this.getQuota(deviceId, ipAddress);
      return {
        allowed: false,
        remaining: 0,
        resetAt: quota.resetAt,
        reason: `Network rate limit reached: video rendering limit exceeded for this network (max ${this.ipVideoLimit} per 30 minutes).`,
        quota,
      };
    }

    // refresh or initialize device record
    if (!record || now - record.windowStart >= this.windowMs) {
      record = {
        deviceId,
        ipAddress,
        windowStart: now,
        imagesUsed: 0,
        videosUsed: 0,
        updatedAt: now,
      };
    } else {
      record.ipAddress = ipAddress;
    }

    const resetAt = record.windowStart + this.windowMs;
    const minsRemaining = Math.max(1, Math.ceil((resetAt - now) / 60000));

    // device quota
    if (mediaKind === "image") {
      if (record.imagesUsed >= this.imageLimit) {
        const quota = await this.getQuota(deviceId, ipAddress);
        return {
          allowed: false,
          remaining: 0,
          resetAt,
          reason: `Image quota reached (30 images per 30 minutes). Resets in ${minsRemaining} min${minsRemaining === 1 ? "" : "s"}.`,
          quota,
        };
      }
      record.imagesUsed += 1;
    } else {
      if (record.videosUsed >= this.videoLimit) {
        const quota = await this.getQuota(deviceId, ipAddress);
        return {
          allowed: false,
          remaining: 0,
          resetAt,
          reason: `Video quota reached (10 videos per 30 minutes). Resets in ${minsRemaining} min${minsRemaining === 1 ? "" : "s"}.`,
          quota,
        };
      }
      record.videosUsed += 1;
    }

    record.updatedAt = now;
    await this.db.saveDeviceQuota(record);

    const remaining =
      mediaKind === "image"
        ? Math.max(0, this.imageLimit - record.imagesUsed)
        : Math.max(0, this.videoLimit - record.videosUsed);

    const quota = await this.getQuota(deviceId, ipAddress);

    return {
      allowed: true,
      remaining,
      resetAt,
      quota,
    };
  }

  async refundCredit(
    deviceId: string,
    mediaKind: "image" | "video",
  ): Promise<void> {
    const record = await this.db.getDeviceQuota(deviceId);
    if (!record) return;

    if (mediaKind === "image") {
      record.imagesUsed = Math.max(0, record.imagesUsed - 1);
    } else {
      record.videosUsed = Math.max(0, record.videosUsed - 1);
    }
    record.updatedAt = Date.now();
    await this.db.saveDeviceQuota(record);
    console.log(
      `[QuotaService] Refunded 1 ${mediaKind} credit for device ${deviceId}`,
    );
  }
}
