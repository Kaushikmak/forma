import dotenv from "dotenv";
import path from "path";
import fs from "fs";
import { SupabaseStorageService } from "./services/storage.js";
import { PostgresService, MemoryDatabaseService } from "./services/db.js";
import { StorageCleanupService } from "./services/cleaner.js";

dotenv.config();

async function main() {
  const projectRoot = fs.existsSync(path.resolve(process.cwd(), "lego_core/worker.py"))
    ? process.cwd()
    : path.resolve(process.cwd(), "..");
  const storageDir = path.resolve(projectRoot, ".forma_storage");

  const supabaseUrl = process.env.SUPABASE_URL || "https://pkohbeuqtfbbwbfkxear.supabase.co";
  const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;

  const storage = new SupabaseStorageService(supabaseUrl, supabaseKey || "", storageDir);

  const databaseUrl = process.env.DATABASE_URL;
  const db = databaseUrl ? new PostgresService(databaseUrl) : new MemoryDatabaseService();
  if (databaseUrl) {
    await db.init().catch(() => {});
  }

  const cleaner = new StorageCleanupService({ storage, db, storageDir });
  console.log(`[Storage Cleaner CLI] Running one-shot cleanup (threshold: ${cleaner.getStats().maxAgeMinutes} mins)...`);
  const stats = await cleaner.cleanupNow();
  
  console.log(`[Storage Cleaner CLI] Completed in ${stats.durationMs}ms`);
  console.log(`  - Deleted remote files: ${stats.deletedRemoteFiles} (${(stats.deletedRemoteBytes / 1024 / 1024).toFixed(2)} MB)`);
  console.log(`  - Deleted local staging files: ${stats.deletedLocalFiles}`);
  console.log(`  - Purged DB upload slots: ${stats.deletedDbSlots ?? 0}`);
  console.log(`  - Purged DB completed jobs: ${stats.deletedDbJobs ?? 0}`);
  if (stats.errors.length > 0) {
    console.warn(`  - Warnings/Errors:`, stats.errors);
  }
  process.exit(0);
}

main().catch((err) => {
  console.error("[Storage Cleaner CLI] Error:", err);
  process.exit(1);
});
