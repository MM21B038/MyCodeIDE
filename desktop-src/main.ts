import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import path from "node:path";

type RuntimeStatus = "starting" | "ready" | "error" | "stopped";

type RuntimeState = {
  apiBaseUrl: string;
  message: string;
  status: RuntimeStatus;
};

const repoRoot = path.resolve(__dirname, "..");
const apiPort = 8765;
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcessWithoutNullStreams | null = null;
let runtimeState: RuntimeState = {
  apiBaseUrl,
  message: "Starting local API runtime...",
  status: "starting",
};
let backendBuffer = "";

function broadcastRuntimeState(): void {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("runtime-state", runtimeState);
  }
}

function setRuntimeState(partial: Partial<RuntimeState>): void {
  runtimeState = { ...runtimeState, ...partial };
  broadcastRuntimeState();
}

async function waitForHealth(timeoutMs = 15000): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(`${apiBaseUrl}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      // The server is still booting.
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error("Timed out waiting for the local API runtime.");
}

async function trySpawnBackend(command: string): Promise<ChildProcessWithoutNullStreams> {
  return new Promise((resolve, reject) => {
    const child = spawn(
      command,
      ["-m", "uvicorn", "context_engine.api.main:app", "--host", "127.0.0.1", "--port", String(apiPort)],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          PYTHONPATH: path.join(repoRoot, "src"),
        },
        stdio: "pipe",
      },
    );

    let settled = false;
    const finishResolve = (): void => {
      if (!settled) {
        settled = true;
        resolve(child);
      }
    };
    const finishReject = (error: Error): void => {
      if (!settled) {
        settled = true;
        reject(error);
      }
    };

    child.stdout.on("data", (chunk) => {
      backendBuffer = `${backendBuffer}${chunk.toString()}`.slice(-4000);
    });
    child.stderr.on("data", (chunk) => {
      backendBuffer = `${backendBuffer}${chunk.toString()}`.slice(-4000);
    });

    child.once("error", (error) => {
      finishReject(error);
    });

    child.once("spawn", () => {
      setTimeout(finishResolve, 400);
    });

    child.once("exit", (code) => {
      finishReject(new Error(`Backend exited early with code ${code ?? "unknown"}.`));
    });
  });
}

async function startBackend(): Promise<void> {
  if (backendProcess) {
    return;
  }

  setRuntimeState({ message: "Starting local API runtime...", status: "starting" });
  const commands = process.platform === "win32" ? ["python", "py"] : ["python3", "python"];
  let lastError: Error | null = null;

  for (const command of commands) {
    try {
      const child = await trySpawnBackend(command);
      backendProcess = child;
      await waitForHealth();
      child.once("exit", () => {
        backendProcess = null;
        setRuntimeState({
          message: "Local API runtime stopped.",
          status: "stopped",
        });
      });
      setRuntimeState({
        message: "Local API runtime is ready.",
        status: "ready",
      });
      return;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      if (backendProcess) {
        backendProcess.kill();
        backendProcess = null;
      }
    }
  }

  setRuntimeState({
    message: `Failed to start backend. ${lastError?.message ?? "Unknown error."}${backendBuffer ? `\n\n${backendBuffer}` : ""}`,
    status: "error",
  });
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1520,
    height: 980,
    minWidth: 1200,
    minHeight: 760,
    title: "MyCodeIDE Desktop",
    backgroundColor: "#efe4d3",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  await mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  broadcastRuntimeState();
}

ipcMain.handle("runtime:get-state", async () => runtimeState);

ipcMain.handle("folder:select", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory"],
    title: "Select Project Folder",
  });
  if (result.canceled || !result.filePaths[0]) {
    return { canceled: true };
  }
  const folderPath = result.filePaths[0];
  return {
    canceled: false,
    path: folderPath,
    name: path.basename(folderPath),
  };
});

app.whenReady().then(async () => {
  await createWindow();
  await startBackend();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
    backendProcess = null;
  }
});
