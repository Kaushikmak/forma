import dotenv from "dotenv";
import { createApp } from "./app.js";
import path from "path";
import fs from "fs";

if (fs.existsSync(path.resolve(process.cwd(), ".env"))) {
  dotenv.config({ path: path.resolve(process.cwd(), ".env") });
}
if (fs.existsSync(path.resolve(process.cwd(), "../.env"))) {
  dotenv.config({ path: path.resolve(process.cwd(), "../.env") });
}

const port = process.env.PORT || 4000;
const app = createApp();

app.listen(port, () => {
  console.log(`[Forma Backend] API server listening on http://localhost:${port}`);
  console.log(`[Forma Backend] Supabase Storage and Worker queue initialized`);
});
