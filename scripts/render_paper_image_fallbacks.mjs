import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const queuePath = path.join(projectRoot, "tmp", "paper-image-fallback-queue.json");
const resultPath = path.join(projectRoot, "tmp", "paper-image-fallback-results.json");

const queue = JSON.parse(await fs.readFile(queuePath, "utf8"));
await fs.mkdir(path.dirname(resultPath), { recursive: true });

function candidateUrls(item) {
  return Array.from(
    new Set([item.html_url, item.ar5iv_url].filter(Boolean)),
  );
}

async function pickElement(page) {
  const selectors = [
    "figure",
    ".ltx_figure",
    ".ltx_figure_outer",
    ".ltx_figure_panel",
    ".ltx_float",
  ];

  for (const selector of selectors) {
    const locator = page.locator(selector);
    const count = await locator.count();
    for (let index = 0; index < count; index += 1) {
      const element = locator.nth(index);
      const box = await element.boundingBox();
      if (!box || box.width < 220 || box.height < 120) {
        continue;
      }
      return { element, selector, box };
    }
  }

  const locator = page.locator('img:not([src^="data:"])');
  const count = await locator.count();
  for (let index = 0; index < count; index += 1) {
    const element = locator.nth(index);
    const src = (await element.getAttribute("src")) || "";
    if (/logo|icon|badge|ar5iv_card/i.test(src)) {
      continue;
    }
    const box = await element.boundingBox();
    if (!box || box.width < 220 || box.height < 120) {
      continue;
    }
    return { element, selector: "img", box };
  }

  return null;
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1440, height: 1600 },
  deviceScaleFactor: 2,
});

const results = [];

for (const item of queue) {
  const result = {
    arxiv_id: item.arxiv_id,
    title: item.title,
    ok: false,
    used_url: "",
    selector: "",
    width: null,
    height: null,
    error: "",
  };

  for (const url of candidateUrls(item)) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
      await page.waitForTimeout(1500);

      const picked = await pickElement(page);
      if (!picked) {
        continue;
      }

      await fs.mkdir(path.dirname(item.output_path), { recursive: true });
      await picked.element.screenshot({ path: item.output_path, type: "png" });

      result.ok = true;
      result.used_url = url;
      result.selector = picked.selector;
      result.width = Math.round(picked.box.width);
      result.height = Math.round(picked.box.height);
      break;
    } catch (error) {
      result.error = String(error);
    }
  }

  results.push(result);
  if (result.ok) {
    console.log(`[fallback] ${item.arxiv_id} saved -> ${path.relative(projectRoot, item.output_path)}`);
  } else {
    console.log(`[fallback] ${item.arxiv_id} failed`);
  }
}

await browser.close();
await fs.writeFile(resultPath, JSON.stringify(results, null, 2), "utf8");

const successCount = results.filter((item) => item.ok).length;
console.log(`fallback results: ${successCount}/${results.length}`);
