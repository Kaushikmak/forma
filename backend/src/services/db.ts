import pg from "pg";
import { JobState } from "../types/contract.js";

const { Pool } = pg;

export interface UploadSlotRecord {
  assetId: string;
  mimeType: string;
  fileSize: number;
  width?: number;
  height?: number;
  durationSec?: number;
  createdAt: number;
  expiresAt: number;
}

export interface DeviceQuotaRecord {
  deviceId: string;
  ipAddress: string;
  windowStart: number;
  imagesUsed: number;
  videosUsed: number;
  updatedAt: number;
}

export interface DatabaseService {
  init(): Promise<void>;
  saveUploadSlot(slot: UploadSlotRecord): Promise<void>;
  getUploadSlot(assetId: string): Promise<UploadSlotRecord | null>;
  saveJob(job: JobState): Promise<void>;
  getJob(jobId: string): Promise<JobState | null>;
  getDeviceQuota(deviceId: string): Promise<DeviceQuotaRecord | null>;
  saveDeviceQuota(quota: DeviceQuotaRecord): Promise<void>;
  getIpUsage(
    ipAddress: string,
    windowStartCutoff: number,
  ): Promise<{ deviceCount: number; imagesUsed: number; videosUsed: number }>;
  cleanOldRecords?(
    cutoffMs: number,
  ): Promise<{
    deletedSlots: number;
    deletedJobs: number;
    deletedQuotas?: number;
  }>;
  close(): Promise<void>;
}

export class PostgresService implements DatabaseService {
  private pool: pg.Pool;
  private connectionString: string;

  constructor(connectionString: string) {
    this.connectionString = connectionString;
    this.pool = new Pool({
      connectionString,
      ssl: connectionString.includes("supabase")
        ? { rejectUnauthorized: false }
        : undefined,
      connectionTimeoutMillis: 5000,
    });
  }

  private async getClient(): Promise<pg.PoolClient> {
    try {
      return await this.pool.connect();
    } catch (err: any) {
      if (
        (err.code === "ENETUNREACH" || err.message?.includes("ENETUNREACH")) &&
        this.connectionString.includes("supabase.co")
      ) {
        console.log(
          "[PostgresService] Direct IPv6 unreachable; switching to Supabase IPv4 Connection Pooler...",
        );
        const parsed = new URL(this.connectionString);
        const hostParts = parsed.hostname.split(".");
        const projectRef = hostParts[1] || "pkohbeuqtfbbwbfkxear";
        const poolerHost =
          process.env.SUPABASE_POOLER_HOST ||
          "aws-0-ap-northeast-1.pooler.supabase.com";
        const poolerUser = `${parsed.username}.${projectRef}`;
        await this.pool.end().catch(() => {});
        this.pool = new Pool({
          host: poolerHost,
          port: 5432,
          user: poolerUser,
          password: decodeURIComponent(parsed.password),
          database: parsed.pathname.slice(1) || "postgres",
          ssl: { rejectUnauthorized: false },
          connectionTimeoutMillis: 8000,
        });
        return await this.pool.connect();
      }
      throw err;
    }
  }

  async init(): Promise<void> {
    const client = await this.getClient();
    try {
      await client.query(`
        CREATE TABLE IF NOT EXISTS forma_upload_slots (
          asset_id TEXT PRIMARY KEY,
          mime_type TEXT NOT NULL,
          file_size BIGINT NOT NULL,
          width INTEGER,
          height INTEGER,
          duration_sec DOUBLE PRECISION,
          created_at BIGINT NOT NULL,
          expires_at BIGINT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS forma_jobs (
          job_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          progress INTEGER NOT NULL DEFAULT 0,
          updated_at BIGINT NOT NULL,
          attempts INTEGER NOT NULL DEFAULT 0,
          cancel INTEGER NOT NULL DEFAULT 0,
          media_kind TEXT,
          input_width INTEGER,
          input_height INTEGER,
          result_bucket TEXT,
          result_key TEXT,
          result_url TEXT,
          content_type TEXT,
          width INTEGER,
          height INTEGER,
          frames INTEGER,
          duration_sec DOUBLE PRECISION,
          bytes BIGINT,
          processing_ms INTEGER,
          error_code TEXT,
          error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS forma_device_quotas (
          device_id TEXT PRIMARY KEY,
          ip_address TEXT NOT NULL,
          window_start BIGINT NOT NULL,
          images_used INTEGER NOT NULL DEFAULT 0,
          videos_used INTEGER NOT NULL DEFAULT 0,
          updated_at BIGINT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_forma_device_quotas_ip ON forma_device_quotas(ip_address, window_start);
      `);
    } finally {
      client.release();
    }
  }

  async saveUploadSlot(slot: UploadSlotRecord): Promise<void> {
    await this.pool.query(
      `
      INSERT INTO forma_upload_slots (
        asset_id, mime_type, file_size, width, height, duration_sec, created_at, expires_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
      ON CONFLICT (asset_id) DO UPDATE SET
        mime_type = EXCLUDED.mime_type,
        file_size = EXCLUDED.file_size,
        width = EXCLUDED.width,
        height = EXCLUDED.height,
        duration_sec = EXCLUDED.duration_sec,
        expires_at = EXCLUDED.expires_at;
      `,
      [
        slot.assetId,
        slot.mimeType,
        slot.fileSize,
        slot.width ?? null,
        slot.height ?? null,
        slot.durationSec ?? null,
        slot.createdAt,
        slot.expiresAt,
      ],
    );
  }

  async getUploadSlot(assetId: string): Promise<UploadSlotRecord | null> {
    const res = await this.pool.query(
      `SELECT * FROM forma_upload_slots WHERE asset_id = $1`,
      [assetId],
    );
    if (res.rows.length === 0) return null;
    const r = res.rows[0];
    return {
      assetId: r.asset_id,
      mimeType: r.mime_type,
      fileSize: Number(r.file_size),
      width: r.width ?? undefined,
      height: r.height ?? undefined,
      durationSec: r.duration_sec ?? undefined,
      createdAt: Number(r.created_at),
      expiresAt: Number(r.expires_at),
    };
  }
  // TODO fix timestamp null bug
  async saveJob(job: JobState): Promise<void> {
    await this.pool.query(
      `
      INSERT INTO forma_jobs (
        job_id, status, progress, updated_at, attempts, cancel, media_kind,
        input_width, input_height, result_bucket, result_key, result_url,
        content_type, width, height, frames, duration_sec, bytes, processing_ms,
        error_code, error_message
      ) VALUES (
        $1, $2, $3, $4, $5, $6, $7,
        $8, $9, $10, $11, $12,
        $13, $14, $15, $16, $17, $18, $19,
        $20, $21
      )
      ON CONFLICT (job_id) DO UPDATE SET
        status = EXCLUDED.status,
        progress = EXCLUDED.progress,
        updated_at = EXCLUDED.updated_at,
        attempts = COALESCE(EXCLUDED.attempts, forma_jobs.attempts),
        cancel = COALESCE(EXCLUDED.cancel, forma_jobs.cancel),
        media_kind = COALESCE(EXCLUDED.media_kind, forma_jobs.media_kind),
        input_width = COALESCE(EXCLUDED.input_width, forma_jobs.input_width),
        input_height = COALESCE(EXCLUDED.input_height, forma_jobs.input_height),
        result_bucket = COALESCE(EXCLUDED.result_bucket, forma_jobs.result_bucket),
        result_key = COALESCE(EXCLUDED.result_key, forma_jobs.result_key),
        result_url = COALESCE(EXCLUDED.result_url, forma_jobs.result_url),
        content_type = COALESCE(EXCLUDED.content_type, forma_jobs.content_type),
        width = COALESCE(EXCLUDED.width, forma_jobs.width),
        height = COALESCE(EXCLUDED.height, forma_jobs.height),
        frames = COALESCE(EXCLUDED.frames, forma_jobs.frames),
        duration_sec = COALESCE(EXCLUDED.duration_sec, forma_jobs.duration_sec),
        bytes = COALESCE(EXCLUDED.bytes, forma_jobs.bytes),
        processing_ms = COALESCE(EXCLUDED.processing_ms, forma_jobs.processing_ms),
        error_code = COALESCE(EXCLUDED.error_code, forma_jobs.error_code),
        error_message = COALESCE(EXCLUDED.error_message, forma_jobs.error_message);
      `,
      [
        job.jobId,
        job.status,
        job.progress ?? 0,
        job.updatedAt || Date.now(),
        job.attempts ?? 0,
        job.cancel ?? 0,
        job.mediaKind ?? null,
        job.inputWidth ?? null,
        job.inputHeight ?? null,
        job.resultBucket ?? null,
        job.resultKey ?? null,
        job.resultUrl ?? null,
        job.contentType ?? null,
        job.width ?? null,
        job.height ?? null,
        job.frames ?? null,
        job.durationSec ?? null,
        job.bytes ?? null,
        job.processingMs ?? null,
        job.errorCode ?? null,
        job.errorMessage ?? null,
      ],
    );
  }

  async getJob(jobId: string): Promise<JobState | null> {
    const res = await this.pool.query(
      `SELECT * FROM forma_jobs WHERE job_id = $1`,
      [jobId],
    );
    if (res.rows.length === 0) return null;
    const r = res.rows[0];
    return {
      jobId: r.job_id,
      status: r.status,
      progress: r.progress,
      updatedAt: Number(r.updated_at),
      attempts: r.attempts,
      cancel: r.cancel,
      mediaKind: r.media_kind ?? undefined,
      inputWidth: r.input_width ?? undefined,
      inputHeight: r.input_height ?? undefined,
      resultBucket: r.result_bucket ?? undefined,
      resultKey: r.result_key ?? undefined,
      resultUrl: r.result_url ?? undefined,
      contentType: r.content_type ?? undefined,
      width: r.width ?? undefined,
      height: r.height ?? undefined,
      frames: r.frames ?? undefined,
      durationSec: r.duration_sec ?? undefined,
      bytes: r.bytes ? Number(r.bytes) : undefined,
      processingMs: r.processing_ms ?? undefined,
      errorCode: r.error_code ?? undefined,
      errorMessage: r.error_message ?? undefined,
    };
  }

  async getDeviceQuota(deviceId: string): Promise<DeviceQuotaRecord | null> {
    const res = await this.pool.query(
      `SELECT * FROM forma_device_quotas WHERE device_id = $1`,
      [deviceId],
    );
    if (res.rows.length === 0) return null;
    const r = res.rows[0];
    return {
      deviceId: r.device_id,
      ipAddress: r.ip_address,
      windowStart: Number(r.window_start),
      imagesUsed: Number(r.images_used),
      videosUsed: Number(r.videos_used),
      updatedAt: Number(r.updated_at),
    };
  }

  async saveDeviceQuota(quota: DeviceQuotaRecord): Promise<void> {
    await this.pool.query(
      `
      INSERT INTO forma_device_quotas (
        device_id, ip_address, window_start, images_used, videos_used, updated_at
      ) VALUES ($1, $2, $3, $4, $5, $6)
      ON CONFLICT (device_id) DO UPDATE SET
        ip_address = EXCLUDED.ip_address,
        window_start = EXCLUDED.window_start,
        images_used = EXCLUDED.images_used,
        videos_used = EXCLUDED.videos_used,
        updated_at = EXCLUDED.updated_at;
      `,
      [
        quota.deviceId,
        quota.ipAddress,
        quota.windowStart,
        quota.imagesUsed,
        quota.videosUsed,
        quota.updatedAt,
      ],
    );
  }

  async getIpUsage(
    ipAddress: string,
    windowStartCutoff: number,
  ): Promise<{ deviceCount: number; imagesUsed: number; videosUsed: number }> {
    const res = await this.pool.query(
      `
      SELECT 
        COUNT(DISTINCT device_id) as device_count,
        COALESCE(SUM(images_used), 0) as images_used,
        COALESCE(SUM(videos_used), 0) as videos_used
      FROM forma_device_quotas 
      WHERE ip_address = $1 AND window_start >= $2
      `,
      [ipAddress, windowStartCutoff],
    );
    const r = res.rows[0];
    return {
      deviceCount: Number(r?.device_count || 0),
      imagesUsed: Number(r?.images_used || 0),
      videosUsed: Number(r?.videos_used || 0),
    };
  }

  async cleanOldRecords(
    cutoffMs: number,
  ): Promise<{
    deletedSlots: number;
    deletedJobs: number;
    deletedQuotas?: number;
  }> {
    const slotsRes = await this.pool.query(
      `DELETE FROM forma_upload_slots WHERE created_at < $1`,
      [cutoffMs],
    );
    const jobsRes = await this.pool.query(
      `DELETE FROM forma_jobs WHERE updated_at < $1 AND status IN ('done', 'failed', 'rejected', 'cancelled', 'expired')`,
      [cutoffMs],
    );
    const quotasRes = await this.pool.query(
      `DELETE FROM forma_device_quotas WHERE updated_at < $1`,
      [cutoffMs],
    );
    return {
      deletedSlots: slotsRes.rowCount || 0,
      deletedJobs: jobsRes.rowCount || 0,
      deletedQuotas: quotasRes.rowCount || 0,
    };
  }

  async close(): Promise<void> {
    await this.pool.end();
  }
}

export class MemoryDatabaseService implements DatabaseService {
  private slots = new Map<string, UploadSlotRecord>();
  private jobs = new Map<string, JobState>();
  private quotas = new Map<string, DeviceQuotaRecord>();

  async init(): Promise<void> {}

  async saveUploadSlot(slot: UploadSlotRecord): Promise<void> {
    this.slots.set(slot.assetId, slot);
  }

  async getUploadSlot(assetId: string): Promise<UploadSlotRecord | null> {
    return this.slots.get(assetId) ?? null;
  }

  async saveJob(job: JobState): Promise<void> {
    this.jobs.set(job.jobId, job);
  }

  async getJob(jobId: string): Promise<JobState | null> {
    return this.jobs.get(jobId) ?? null;
  }

  async getDeviceQuota(deviceId: string): Promise<DeviceQuotaRecord | null> {
    const quota = this.quotas.get(deviceId);
    return quota ? { ...quota } : null;
  }

  async saveDeviceQuota(quota: DeviceQuotaRecord): Promise<void> {
    this.quotas.set(quota.deviceId, { ...quota });
  }

  async getIpUsage(
    ipAddress: string,
    windowStartCutoff: number,
  ): Promise<{ deviceCount: number; imagesUsed: number; videosUsed: number }> {
    const devices = new Set<string>();
    let imagesUsed = 0;
    let videosUsed = 0;
    for (const record of this.quotas.values()) {
      if (
        record.ipAddress === ipAddress &&
        record.windowStart >= windowStartCutoff
      ) {
        devices.add(record.deviceId);
        imagesUsed += record.imagesUsed;
        videosUsed += record.videosUsed;
      }
    }
    return {
      deviceCount: devices.size,
      imagesUsed,
      videosUsed,
    };
  }

  async cleanOldRecords(
    cutoffMs: number,
  ): Promise<{
    deletedSlots: number;
    deletedJobs: number;
    deletedQuotas?: number;
  }> {
    let deletedSlots = 0;
    for (const [id, slot] of this.slots.entries()) {
      if (slot.createdAt < cutoffMs) {
        this.slots.delete(id);
        deletedSlots++;
      }
    }
    let deletedJobs = 0;
    for (const [id, job] of this.jobs.entries()) {
      if (
        job.updatedAt < cutoffMs &&
        ["done", "failed", "rejected", "cancelled", "expired"].includes(
          job.status,
        )
      ) {
        this.jobs.delete(id);
        deletedJobs++;
      }
    }
    let deletedQuotas = 0;
    for (const [id, quota] of this.quotas.entries()) {
      if (quota.updatedAt < cutoffMs) {
        this.quotas.delete(id);
        deletedQuotas++;
      }
    }
    return { deletedSlots, deletedJobs, deletedQuotas };
  }

  async close(): Promise<void> {}
}
