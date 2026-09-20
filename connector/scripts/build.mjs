import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "src");
const output = resolve(process.env.CONNECTOR_OUTPUT_DIR || join(root, "dist"));
const apiOrigin = process.argv[2] || process.env.SRM_TRACKER_API_ORIGIN;

if (!apiOrigin || !/^https?:\/\/[^/]+$/.test(apiOrigin)) {
  throw new Error("A loopback or production API origin is required, for example http://127.0.0.1:8000");
}

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
const files = ["manifest.json", "worker.mjs", "popup.html", "popup.mjs", "popup.css", "page-collector.js", "message-policy.mjs", "collector.mjs", "portal-policy.mjs"];
for (const file of files) {
  const input = await readFile(join(source, file), "utf8");
  await writeFile(join(output, file), input.replaceAll("__SRM_TRACKER_API_ORIGIN__", apiOrigin), "utf8");
}
console.log(`Built connector for ${apiOrigin} at ${output}`);
