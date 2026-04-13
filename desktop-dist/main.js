"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const node_child_process_1 = require("node:child_process");
const node_path_1 = __importDefault(require("node:path"));
const repoRoot = node_path_1.default.resolve(__dirname, "..");
const apiPort = 8765;
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
let mainWindow = null;
let backendProcess = null;
let runtimeState = {
    apiBaseUrl,
    message: "Starting local API runtime...",
    status: "starting",
};
let backendBuffer = "";
function broadcastRuntimeState() {
    if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("runtime-state", runtimeState);
    }
}
function setRuntimeState(partial) {
    runtimeState = { ...runtimeState, ...partial };
    broadcastRuntimeState();
}
async function waitForHealth(timeoutMs = 15000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
        try {
            const response = await fetch(`${apiBaseUrl}/health`);
            if (response.ok) {
                return;
            }
        }
        catch {
            // The server is still booting.
        }
        await new Promise((resolve) => setTimeout(resolve, 300));
    }
    throw new Error("Timed out waiting for the local API runtime.");
}
async function trySpawnBackend(command) {
    return new Promise((resolve, reject) => {
        const child = (0, node_child_process_1.spawn)(command, ["-m", "uvicorn", "context_engine.api.main:app", "--host", "127.0.0.1", "--port", String(apiPort)], {
            cwd: repoRoot,
            env: {
                ...process.env,
                PYTHONPATH: node_path_1.default.join(repoRoot, "src"),
            },
            stdio: "pipe",
        });
        let settled = false;
        const finishResolve = () => {
            if (!settled) {
                settled = true;
                resolve(child);
            }
        };
        const finishReject = (error) => {
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
async function startBackend() {
    if (backendProcess) {
        return;
    }
    setRuntimeState({ message: "Starting local API runtime...", status: "starting" });
    const commands = process.platform === "win32" ? ["python", "py"] : ["python3", "python"];
    let lastError = null;
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
        }
        catch (error) {
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
async function createWindow() {
    mainWindow = new electron_1.BrowserWindow({
        width: 1520,
        height: 980,
        minWidth: 1200,
        minHeight: 760,
        title: "MyCodeIDE Desktop",
        backgroundColor: "#efe4d3",
        webPreferences: {
            preload: node_path_1.default.join(__dirname, "preload.js"),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
    await mainWindow.loadFile(node_path_1.default.join(__dirname, "renderer", "index.html"));
    broadcastRuntimeState();
}
electron_1.ipcMain.handle("runtime:get-state", async () => runtimeState);
electron_1.ipcMain.handle("folder:select", async () => {
    const result = await electron_1.dialog.showOpenDialog({
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
        name: node_path_1.default.basename(folderPath),
    };
});
electron_1.app.whenReady().then(async () => {
    await createWindow();
    await startBackend();
    electron_1.app.on("activate", async () => {
        if (electron_1.BrowserWindow.getAllWindows().length === 0) {
            await createWindow();
        }
    });
});
electron_1.app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
        electron_1.app.quit();
    }
});
electron_1.app.on("before-quit", () => {
    if (backendProcess && !backendProcess.killed) {
        backendProcess.kill();
        backendProcess = null;
    }
});
