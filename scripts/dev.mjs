import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const apiDir = path.join(root, "apps", "api");
const venvDir = path.join(apiDir, ".venv");
const isWindows = process.platform === "win32";
const pythonBin = isWindows
  ? path.join(venvDir, "Scripts", "python.exe")
  : path.join(venvDir, "bin", "python");
const pipBin = isWindows
  ? path.join(venvDir, "Scripts", "pip.exe")
  : path.join(venvDir, "bin", "pip");

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? root,
    stdio: "inherit",
    shell: false,
    env: { ...process.env, ...options.env }
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function commandOutput(command, args) {
  const result = spawnSync(command, args, { encoding: "utf-8", shell: false });
  if (result.status !== 0) {
    return "";
  }
  return `${result.stdout}${result.stderr}`.trim();
}

function isPython311(command, args) {
  return commandOutput(command, args).includes("Python 3.11.");
}

function findPython() {
  const candidates = isWindows
    ? [["py", ["-3.11", "--version"]], ["python", ["--version"]]]
    : [["python3.11", ["--version"]], ["python3", ["--version"]], ["python", ["--version"]]];

  for (const [command, args] of candidates) {
    if (isPython311(command, args)) {
      return { command, createArgs: command === "py" ? ["-3.11", "-m", "venv", venvDir] : ["-m", "venv", venvDir] };
    }
  }

  console.error("Python 3.11 не найден. Установите Python 3.11 и повторите npm run dev.");
  process.exit(1);
}

await mkdir(path.join(root, "data", "rasters"), { recursive: true });
await mkdir(path.join(root, "data", "reports"), { recursive: true });
await mkdir(path.join(root, "data", "cache"), { recursive: true });

if (existsSync(pythonBin) && !isPython311(pythonBin, ["--version"])) {
  console.log("Найден apps/api/.venv не на Python 3.11. Пересоздаю venv для устойчивого dev-запуска...");
  await rm(venvDir, { recursive: true, force: true });
}

if (!existsSync(pythonBin)) {
  const python = findPython();
  console.log("Создаю Python venv для FastAPI...");
  run(python.command, python.createArgs);
}

console.log("Проверяю зависимости FastAPI...");
const install = spawnSync(pipBin, ["install", "-r", path.join(apiDir, "requirements.txt")], {
  cwd: root,
  stdio: "inherit",
  shell: false
});

if (install.status !== 0) {
  console.error(`
Не удалось установить Python-зависимости.

Чаще всего на Windows проблема связана с GDAL/rasterio. Попробуйте:
1. Убедиться, что установлен Python 3.11 x64.
2. Обновить pip: ${pythonBin} -m pip install --upgrade pip
3. Установить зависимости повторно: ${pipBin} install -r apps/api/requirements.txt
4. Если rasterio не собирается из исходников, установить готовые wheels или использовать production Docker на VPS.

Скрипт остановлен честно: live raster pipeline без rasterio/GDAL работать не сможет.
`);
  process.exit(install.status ?? 1);
}

const env = {
  ...process.env,
  PYTHONUTF8: "1",
  PYTHONPATH: apiDir,
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
};

const children = [];

function start(name, command, args, cwd) {
  const child = spawn(command, args, {
    cwd,
    stdio: "inherit",
    shell: isWindows,
    env
  });
  child.on("exit", (code) => {
    if (!shuttingDown && code !== 0) {
      console.error(`${name} завершился с кодом ${code}. Останавливаю dev-сессию.`);
      stopAll(code ?? 1);
    }
  });
  children.push(child);
}

let shuttingDown = false;
function stopAll(code = 0) {
  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) {
      child.kill(isWindows ? undefined : "SIGTERM");
    }
  }
  setTimeout(() => process.exit(code), 300);
}

process.on("SIGINT", () => stopAll(0));
process.on("SIGTERM", () => stopAll(0));

console.log("Запускаю FastAPI на http://localhost:8000");
start("FastAPI", pythonBin, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"], apiDir);

console.log("Запускаю Next.js на http://localhost:3000");
start("Next.js", "npm", ["--workspace", "apps/web", "run", "dev", "--", "--port", "3000"], root);
