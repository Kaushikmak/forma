import fs from "fs";
import path from "path";
import { SupabaseClient } from "@supabase/supabase-js";
import {
  StorageService,
  SupabaseStorageService,
} from "./storage.js";
import { DatabaseService } from "./db.js";

export interface CleanupStats {
  timestamp: number;
  durationMs: number;
  maxAgeMinutes: number;
  deletedRemoteFiles: number;
  deletedRemoteBytes: number;
  deletedLocalFiles: number;
  deletedDbSlots?: number;
  deletedDbJobs?: number;
  bucketBreakdown: Record<string, { count: number; bytes: number }>;
  errors: string[];
}

export interface CleanupServiceOptions {
  storage: StorageService;
  db?: DatabaseService;
  storageDir?: string;
  maxAgeMinutes?: number; // default: 30
  intervalMinutes?: number; // default: 5
  buckets?: string[];
}

export class StorageCleanupService {
  private storage: StorageService;
  private db?: DatabaseService;
  private storageDir?: string;
  private maxAgeMinutes: number;
  private intervalMinutes: number;
  private buckets: string[];

  private timer: NodeJS.Timeout | null = null;
  private isRunning: boolean = false;
  private lastStats: CleanupStats | null = null;
  private totalDeletedFiles: number = 0;
  private totalDeletedBytes: number = 0;

  constructor(options: CleanupServiceOptions) {
    this.storage = options.storage;
    this.db = options.db;
    this.storageDir = options.storageDir;

    const envMaxAge = process.env.CLEANUP_MAX_AGE_MINUTES
      ? parseInt(process.env.CLEANUP_MAX_AGE_MINUTES, 10)
      : NaN;
    this.maxAgeMinutes =
      Number.isFinite(envMaxAge) && envMaxAge > 0
        ? envMaxAge
        : options.maxAgeMinutes || 30;

    const envInterval = process.env.CLEANUP_INTERVAL_MINUTES
      ? parseInt(process.env.CLEANUP_INTERVAL_MINUTES, 10)
      : NaN;
    this.intervalMinutes =
      Number.isFinite(envInterval) && envInterval > 0
        ? envInterval
        : options.intervalMinutes || 5;

    const envBuckets = process.env.CLEANUP_BUCKETS
      ? process.env.CLEANUP_BUCKETS.split(",")
          .map((b) => b.trim())
          .filter(Boolean)
      : null;

    this.buckets = envBuckets ||
      options.buckets || ["upload", "Results", "results"];
  }

  start(): this {
    if (this.timer) {
      return this;
    }

    const intervalMs = this.intervalMinutes * 60 * 1000;
    console.log(
      `[Storage Cleaner] Daemon started. Max age: ${this.maxAgeMinutes} mins, check interval: ${this.intervalMinutes} mins, buckets: ${this.buckets.join(", ")}`,
    );

    // Initial scan after 3s
    const initialTimeout = setTimeout(() => {
      this.cleanupNow().catch((err) => {
        console.warn(
          "[Storage Cleaner] Initial cleanup error:",
          err.message || err,
        );
      });
    }, 3000);
    initialTimeout.unref?.();

    // Recurring interval
    this.timer = setInterval(() => {
      this.cleanupNow().catch((err) => {
        console.warn(
          "[Storage Cleaner] Scheduled cleanup error:",
          err.message || err,
        );
      });
    }, intervalMs);
    this.timer.unref?.();

    return this;
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
      console.log("[Storage Cleaner] Daemon stopped.");
    }
  }

  getStats(): {
    lastStats: CleanupStats | null;
    totalDeletedFiles: number;
    totalDeletedBytes: number;
    maxAgeMinutes: number;
    intervalMinutes: number;
    active: boolean;
  } {
    return {
      lastStats: this.lastStats,
      totalDeletedFiles: this.totalDeletedFiles,
      totalDeletedBytes: this.totalDeletedBytes,
      maxAgeMinutes: this.maxAgeMinutes,
      intervalMinutes: this.intervalMinutes,
      active: this.timer !== null,
    };
  }

  async cleanupNow(): Promise<CleanupStats> {
    if (this.isRunning) {
      return (
        this.lastStats || {
          timestamp: Date.now(),
          durationMs: 0,
          maxAgeMinutes: this.maxAgeMinutes,
          deletedRemoteFiles: 0,
          deletedRemoteBytes: 0,
          deletedLocalFiles: 0,
          bucketBreakdown: {},
          errors: ["Cleanup already in progress"],
        }
      );
    }

    this.isRunning = true;
    const startTime = Date.now();
    const cutoffTime = startTime - this.maxAgeMinutes * 60 * 1000;

    const stats: CleanupStats = {
      timestamp: startTime,
      durationMs: 0,
      maxAgeMinutes: this.maxAgeMinutes,
      deletedRemoteFiles: 0,
      deletedRemoteBytes: 0,
      deletedLocalFiles: 0,
      bucketBreakdown: {},
      errors: [],
    };

    try {
      //  Storage Cleanup
      if (this.storage instanceof SupabaseStorageService) {
        const client = this.storage.getClient();
        await this.cleanSupabaseBuckets(client, cutoffTime, stats);
      }

      const localDirsToClean = new Set<string>();
      if (this.storageDir) {
        localDirsToClean.add(path.resolve(this.storageDir));
      }
      if (this.storage instanceof SupabaseStorageService) {
        localDirsToClean.add(path.resolve(this.storage.getStagingDir()));
      }

      for (const dir of localDirsToClean) {
        try {
          if (fs.existsSync(dir)) {
            const count = await this.cleanLocalDirectory(dir, cutoffTime);
            stats.deletedLocalFiles += count;
          }
        } catch (err: any) {
          stats.errors.push(
            `Local cleanup error (${dir}): ${err.message || err}`,
          );
        }
      }

      if (this.db && typeof this.db.cleanOldRecords === "function") {
        try {
          const dbRes = await this.db.cleanOldRecords(cutoffTime);
          stats.deletedDbSlots = dbRes.deletedSlots;
          stats.deletedDbJobs = dbRes.deletedJobs;
        } catch (dbErr: any) {
          stats.errors.push(`DB cleanup error: ${dbErr.message || dbErr}`);
        }
      }

      this.totalDeletedFiles += stats.deletedRemoteFiles;
      this.totalDeletedBytes += stats.deletedRemoteBytes;
    } finally {
      stats.durationMs = Date.now() - startTime;
      this.lastStats = stats;
      this.isRunning = false;

      if (stats.deletedRemoteFiles > 0 || stats.deletedLocalFiles > 0) {
        const mb = (stats.deletedRemoteBytes / (1024 * 1024)).toFixed(2);
        console.log(
          `[Storage Cleaner] Cleanup completed in ${stats.durationMs}ms: removed ${stats.deletedRemoteFiles} remote files (${mb} MB), ${stats.deletedLocalFiles} local files, ${stats.deletedDbSlots ?? 0} db slots.`,
        );
      }
    }

    return stats;
  }

  private async cleanSupabaseBuckets(
    client: SupabaseClient,
    cutoffTime: number,
    stats: CleanupStats,
  ): Promise<void> {
    for (const bucket of this.buckets) {
      stats.bucketBreakdown[bucket] = { count: 0, bytes: 0 };
      const keysToDelete: string[] = [];
      let totalBytesInBucket = 0;

      try {
        let offset = 0;
        const limit = 100;
        let hasMore = true;

        while (hasMore) {
          const { data: rootItems, error } = await client.storage
            .from(bucket)
            .list("", {
              limit,
              offset,
              sortBy: { column: "created_at", order: "asc" },
            });

          if (error) {
            if (
              !error.message.includes("Bucket not found") &&
              !error.message.includes("not found")
            ) {
              stats.errors.push(
                `Error listing bucket ${bucket}: ${error.message}`,
              );
            }
            break;
          }

          if (!rootItems || rootItems.length === 0) {
            break;
          }

          for (const item of rootItems) {
            if (item.id) {
              const fileTime = new Date(
                item.created_at || item.updated_at || "",
              ).getTime();
              if (Number.isFinite(fileTime) && fileTime < cutoffTime) {
                keysToDelete.push(item.name);
                totalBytesInBucket += item.metadata?.size || 0;
              }
            } else {
              let folderOffset = 0;
              let folderHasMore = true;

              while (folderHasMore) {
                const { data: folderFiles, error: folderErr } =
                  await client.storage.from(bucket).list(item.name, {
                    limit: 100,
                    offset: folderOffset,
                  });

                if (folderErr || !folderFiles || folderFiles.length === 0) {
                  break;
                }

                for (const f of folderFiles) {
                  const fTime = new Date(
                    f.created_at || f.updated_at || "",
                  ).getTime();
                  if (Number.isFinite(fTime) && fTime < cutoffTime) {
                    keysToDelete.push(`${item.name}/${f.name}`);
                    totalBytesInBucket += f.metadata?.size || 0;
                  }
                }

                if (folderFiles.length < 100) {
                  folderHasMore = false;
                } else {
                  folderOffset += 100;
                }
              }
            }
          }

          if (rootItems.length < limit) {
            hasMore = false;
          } else {
            offset += limit;
          }
        }

        if (keysToDelete.length > 0) {
          const batchSize = 50;
          for (let i = 0; i < keysToDelete.length; i += batchSize) {
            const batch = keysToDelete.slice(i, i + batchSize);
            const { error: delErr } = await client.storage
              .from(bucket)
              .remove(batch);
            if (delErr) {
              stats.errors.push(
                `Error deleting batch in ${bucket}: ${delErr.message}`,
              );
            }
          }

          stats.bucketBreakdown[bucket].count = keysToDelete.length;
          stats.bucketBreakdown[bucket].bytes = totalBytesInBucket;
          stats.deletedRemoteFiles += keysToDelete.length;
          stats.deletedRemoteBytes += totalBytesInBucket;
        }
      } catch (err: any) {
        stats.errors.push(
          `Error processing bucket ${bucket}: ${err.message || err}`,
        );
      }
    }
  }

  private async cleanLocalDirectory(
    dir: string,
    cutoffTime: number,
  ): Promise<number> {
    let deleted = 0;
    const entries = await fs.promises.readdir(dir, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      try {
        if (entry.isDirectory()) {
          deleted += await this.cleanLocalDirectory(fullPath, cutoffTime);
          const remaining = await fs.promises.readdir(fullPath);
          if (remaining.length === 0) {
            await fs.promises.rmdir(fullPath).catch(() => {});
          }
        } else if (entry.isFile()) {
          const stat = await fs.promises.stat(fullPath);
          const fileTime = stat.mtimeMs;
          if (fileTime < cutoffTime) {
            await fs.promises.unlink(fullPath);
            deleted++;
          }
        }
      } catch {
        // idk
      }
    }

    return deleted;
  }
}
