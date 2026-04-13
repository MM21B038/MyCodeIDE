import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const from = path.join(root, "desktop-src", "renderer");
const to = path.join(root, "desktop-dist", "renderer");

fs.mkdirSync(to, { recursive: true });
for (const file of ["index.html", "styles.css"]) {
  fs.copyFileSync(path.join(from, file), path.join(to, file));
}
