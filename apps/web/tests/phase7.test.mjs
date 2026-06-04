import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

function read(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
}

test("methodology page contains required methodological disclaimer", () => {
  const source = read("app/methodology/page.tsx");

  assert.match(source, /NDVI/);
  assert.match(source, /NDWI/);
  assert.match(source, /NDBI/);
  assert.match(source, /предварительной дистанционной оценкой/);
});

test("about page presents portfolio stack", () => {
  const source = read("app/about/page.tsx");

  assert.match(source, /Next\.js/);
  assert.match(source, /FastAPI/);
  assert.match(source, /Redis\/RQ/);
  assert.match(source, /Docker\/Caddy/);
});

test("dashboard has explicit demo scenario preparation", () => {
  const source = read("components/dashboard.tsx");

  assert.match(source, /Подготовить демо-сценарий/);
  assert.match(source, /rostov_on_don/);
  assert.match(source, /setMode\("comparison"\)/);
  assert.match(source, /Запустить сравнение/);
});

test("pdf panel handles queued and ready states", () => {
  const source = read("components/dashboard.tsx");

  assert.match(source, /PDF поставлен в очередь/);
  assert.match(source, /report\?\.status === "ready"/);
});
