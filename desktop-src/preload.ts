import { contextBridge, ipcRenderer } from "electron";

type RuntimeStatus = "starting" | "ready" | "error" | "stopped";

type RuntimeState = {
  apiBaseUrl: string;
  message: string;
  status: RuntimeStatus;
};

type FolderSelection =
  | { canceled: true }
  | { canceled: false; name: string; path: string };

const api = {
  getRuntimeState(): Promise<RuntimeState> {
    return ipcRenderer.invoke("runtime:get-state");
  },
  onRuntimeState(listener: (state: RuntimeState) => void): () => void {
    const wrapped = (_event: Electron.IpcRendererEvent, state: RuntimeState): void => listener(state);
    ipcRenderer.on("runtime-state", wrapped);
    return () => ipcRenderer.removeListener("runtime-state", wrapped);
  },
  selectFolder(): Promise<FolderSelection> {
    return ipcRenderer.invoke("folder:select");
  },
};

contextBridge.exposeInMainWorld("desktopApi", api);
