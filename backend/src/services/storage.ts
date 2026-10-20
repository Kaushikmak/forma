import { createClient, SupabaseClient } from "@supabase/supabase-js";
import fs from "fs";
import path from "path";
import { Readable } from "stream";
import WebSocket from "ws";

if (!globalThis.WebSocket) {
  (globalThis as any).WebSocket = WebSocket;
}

export interface StorageService {
  save(bucket: string, key: string, data: Buffer | Readable, contentType?: string): Promise<void>;
  get(bucket: string, key: string): Promise<Buffer>;
  getStream(bucket: string, key: string): Promise<Readable>;
  exists(bucket: string, key: string): Promise<boolean>;
  delete(bucket: string, key: string): Promise<void>;
  getAbsolutePath(bucket: string, key: string): string;
  createSignedUploadUrl?(bucket: string, key: string): Promise<{ uploadUrl: string; expiresAt: number }>;
  createSignedUrl?(bucket: string, key: string, expiresIn?: number): Promise<string>;
  getPublicUrl?(bucket: string, key: string): string;
  ensureLocalFile?(bucket: string, key: string): Promise<string>;
}

export class SupabaseStorageService implements StorageService {
  private client: SupabaseClient;
  private stagingDir: string;

  constructor(supabaseUrl: string, supabaseKey: string, stagingDir: string) {
    this.client = createClient(supabaseUrl, supabaseKey);
    this.stagingDir = path.resolve(stagingDir);
    if (!fs.existsSync(this.stagingDir)) {
      fs.mkdirSync(this.stagingDir, { recursive: true });
    }
  }

  private resolveBucket(bucket: string): string {
    const bLower = bucket.toLowerCase();
    if (bLower === "results" || bLower === "outputs") {
      const envVal = process.env.SUPABASE_RESULTS_BUCKET;
      return envVal && envVal.toLowerCase() === "results" ? envVal : "Results";
    }
    if (bLower === "upload" || bLower === "uploads") {
      return "upload";
    }
    return bucket;
  }

  private cleanKey(bucket: string, key: string): string {
    let clean = key;
    const bLower = bucket.toLowerCase();
    if (clean.toLowerCase().startsWith(`${bLower}/`)) {
      clean = clean.slice(bLower.length + 1);
    }
    if ((bLower === "upload" || bLower === "uploads") && clean.startsWith("uploads/")) {
      clean = clean.slice("uploads/".length);
    }
    if ((bLower === "results" || bLower === "outputs") && clean.startsWith("outputs/")) {
      clean = clean.slice("outputs/".length);
    }
    return clean.replace(/^\/+/, "");
  }

  getAbsolutePath(bucket: string, key: string): string {
    const bLower = bucket.toLowerCase();
    if (key.startsWith(`${bucket}/`) || key.toLowerCase().startsWith(`${bLower}/`)) {
      return path.join(this.stagingDir, key);
    }
    if ((bLower === "upload" || bLower === "uploads") && (key.startsWith("upload/") || key.startsWith("uploads/"))) {
      return path.join(this.stagingDir, key);
    }
    if ((bLower === "results" || bLower === "outputs") && (key.startsWith("results/") || key.startsWith("outputs/"))) {
      return path.join(this.stagingDir, key);
    }
    if (key.startsWith("uploads/") || key.startsWith("outputs/")) {
      return path.join(this.stagingDir, key);
    }
    return path.join(this.stagingDir, bucket, key);
  }

  async createSignedUploadUrl(
    bucket: string,
    key: string
  ): Promise<{ uploadUrl: string; expiresAt: number }> {
    const resolvedBucket = this.resolveBucket(bucket);
    const targetKey = this.cleanKey(resolvedBucket, key);
    const { data, error } = await this.client.storage
      .from(resolvedBucket)
      .createSignedUploadUrl(targetKey);

    if (error || !data) {
      throw new Error(`Failed to create signed upload URL: ${error?.message || "Unknown error"}`);
    }

    return {
      uploadUrl: data.signedUrl,
      expiresAt: Date.now() + 2 * 60 * 60 * 1000,
    };
  }

  async createSignedUrl(
    bucket: string,
    key: string,
    expiresIn: number = 86400
  ): Promise<string> {
    const resolvedBucket = this.resolveBucket(bucket);
    const targetKey = this.cleanKey(resolvedBucket, key);
    const { data, error } = await this.client.storage
      .from(resolvedBucket)
      .createSignedUrl(targetKey, expiresIn);

    if (error || !data) {
      throw new Error(`Failed to create signed URL: ${error?.message || "Unknown error"}`);
    }

    return data.signedUrl;
  }

  getPublicUrl(bucket: string, key: string): string {
    const resolvedBucket = this.resolveBucket(bucket);
    const targetKey = this.cleanKey(resolvedBucket, key);
    const { data } = this.client.storage.from(resolvedBucket).getPublicUrl(targetKey);
    return data.publicUrl;
  }

  async save(
    bucket: string,
    key: string,
    data: Buffer | Readable,
    contentType?: string
  ): Promise<void> {
    const resolvedBucket = this.resolveBucket(bucket);
    const targetKey = this.cleanKey(resolvedBucket, key);
    let buffer: Buffer;

    if (Buffer.isBuffer(data)) {
      buffer = data;
    } else {
      const chunks: Buffer[] = [];
      for await (const chunk of data) {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      }
      buffer = Buffer.concat(chunks);
    }

    const { error } = await this.client.storage.from(resolvedBucket).upload(targetKey, buffer, {
      contentType: contentType || "application/octet-stream",
      upsert: true,
    });

    if (error) {
      throw new Error(`Supabase upload failed for ${resolvedBucket}/${targetKey}: ${error.message}`);
    }

    // Also cache in local staging
    const localPath = this.getAbsolutePath(bucket, key);
    await fs.promises.mkdir(path.dirname(localPath), { recursive: true });
    await fs.promises.writeFile(localPath, buffer);
  }

  async get(bucket: string, key: string): Promise<Buffer> {
    const localPath = this.getAbsolutePath(bucket, key);
    if (fs.existsSync(localPath)) {
      return fs.promises.readFile(localPath);
    }
    const resolvedBucket = this.resolveBucket(bucket);
    const targetKey = this.cleanKey(resolvedBucket, key);
    const { data, error } = await this.client.storage.from(resolvedBucket).download(targetKey);
    if (error || !data) {
      throw new Error(`Failed to download ${resolvedBucket}/${targetKey}: ${error?.message || "Not found"}`);
    }
    const arrayBuffer = await data.arrayBuffer();
    return Buffer.from(arrayBuffer);
  }

  async getStream(bucket: string, key: string): Promise<Readable> {
    const buffer = await this.get(bucket, key);
    return Readable.from(buffer);
  }

  async exists(bucket: string, key: string): Promise<boolean> {
    const localPath = this.getAbsolutePath(bucket, key);
    if (fs.existsSync(localPath)) {
      return true;
    }
    const resolvedBucket = this.resolveBucket(bucket);
    const targetKey = this.cleanKey(resolvedBucket, key);
    const dir = path.dirname(targetKey);
    const filename = path.basename(targetKey);
    const searchDir = dir === "." ? "" : dir;

    const { data, error } = await this.client.storage.from(resolvedBucket).list(searchDir, {
      search: filename,
    });

    if (error || !data) return false;
    return data.some((item) => item.name === filename);
  }

  async delete(bucket: string, key: string): Promise<void> {
    const resolvedBucket = this.resolveBucket(bucket);
    const targetKey = this.cleanKey(resolvedBucket, key);
    await this.client.storage.from(resolvedBucket).remove([targetKey]);
    const localPath = this.getAbsolutePath(bucket, key);
    if (fs.existsSync(localPath)) {
      await fs.promises.unlink(localPath);
    }
  }

  async ensureLocalFile(bucket: string, key: string): Promise<string> {
    const localPath = this.getAbsolutePath(bucket, key);
    if (fs.existsSync(localPath)) {
      return localPath;
    }
    const buffer = await this.get(bucket, key);
    await fs.promises.mkdir(path.dirname(localPath), { recursive: true });
    await fs.promises.writeFile(localPath, buffer);
    return localPath;
  }

  getClient(): SupabaseClient {
    return this.client;
  }

  getStagingDir(): string {
    return this.stagingDir;
  }
}
