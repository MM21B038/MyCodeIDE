"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const api = {
    getRuntimeState() {
        return electron_1.ipcRenderer.invoke("runtime:get-state");
    },
    onRuntimeState(listener) {
        const wrapped = (_event, state) => listener(state);
        electron_1.ipcRenderer.on("runtime-state", wrapped);
        return () => electron_1.ipcRenderer.removeListener("runtime-state", wrapped);
    },
    selectFolder() {
        return electron_1.ipcRenderer.invoke("folder:select");
    },
};
electron_1.contextBridge.exposeInMainWorld("desktopApi", api);
