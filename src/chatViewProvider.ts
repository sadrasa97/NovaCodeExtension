import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as child from "child_process";
import { SettingsManager } from "./settings";
import { getWebviewHtml } from "./webviewHtml";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
  mode?: string;
}

type TabId = "chat" | "runner";

export class ChatViewProvider implements vscode.WebviewViewProvider {
  private _view?: vscode.WebviewView;
  private _views = new Map<string, vscode.WebviewView>();
  private _messages: ChatMessage[] = [];
  private _currentTab: TabId = "chat";
  private _runnerOutput = "";
  private _recentFiles: string[] = [];
  private _activeBridge: child.ChildProcess | null = null;

  constructor(
    private readonly _context: vscode.ExtensionContext,
    private readonly _settings: SettingsManager
  ) {
    this._recentFiles = this._context.globalState.get<string[]>("novacode.recentFiles", []);
    if (this._settings.rememberChatHistory) {
      this._messages = this._context.globalState.get<ChatMessage[]>("novacode.chatHistory", []);
    }
  }

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this._view = webviewView;
    this._views.set(webviewView.viewType, webviewView);
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._context.extensionUri],
    };
    webviewView.webview.html = getWebviewHtml(webviewView.webview, this._context.extensionUri, this._tabForView(webviewView.viewType));

    webviewView.webview.onDidReceiveMessage(async (msg: any) => {
      console.log("[NovaCode] webview message:", msg.type);
      switch (msg.type) {
        case "send":
          await this._handleSend(msg.text, msg.mode);
          break;
        case "retry":
          await this._handleRetry();
          break;
        case "getSettings":
          this._postSettings();
          break;
        case "getHistory":
          this.postMessage({ type: "historyUpdated", messages: this._messages }, webviewView.viewType);
          break;
        case "updateBackend":
          await vscode.workspace.getConfiguration("novacode").update("backend", msg.backend, vscode.ConfigurationTarget.Global);
          this._postSettings();
          break;
        case "useDeepSeekOpenRouter":
          await vscode.workspace.getConfiguration("novacode").update("backend", "openrouter", vscode.ConfigurationTarget.Global);
          await vscode.workspace.getConfiguration("novacode").update("openrouterModel", "deepseek/deepseek-chat", vscode.ConfigurationTarget.Global);
          vscode.window.showInformationMessage("NovaCode is using DeepSeek through OpenRouter");
          this._postSettings();
          break;
        case "openModelPicker":
          vscode.window.showInformationMessage("[NovaCode] Opening model picker...");
          await this._settings.selectModelInteractive();
          this._postSettings();
          break;
        case "openSettings":
          vscode.window.showInformationMessage("[NovaCode] Opening settings...");
          this._settings.openSettingsUI();
          break;
        case "updateContextSize":
          await vscode.workspace.getConfiguration("novacode").update("contextSize", msg.value, vscode.ConfigurationTarget.Global);
          vscode.window.showInformationMessage(`Context size updated to ${msg.value}`);
          this._postSettings();
          break;
        case "insertCode":
          await this._insertCode(msg.code);
          break;
        case "copyCode":
          await vscode.env.clipboard.writeText(msg.code);
          vscode.window.showInformationMessage("Copied!");
          break;
        case "switchTab":
          this._currentTab = msg.tab;
          this._handleTabMessage(msg.tab, msg.payload);
          break;
        case "saveHistory":
          this.saveHistory();
          break;
        case "clearHistory":
          this.clearChat();
          break;
        case "requestExplorer":
          this._postExplorerData(msg.payload);
          break;
        case "requestRecent":
          this._postRecentFiles();
          break;
        case "requestFunctions":
          this._postFunctionsData(msg.payload);
          break;
        case "openFile":
          await this._openFile(msg.filePath);
          break;
        case "gotoFunction":
          await this._gotoFunction(msg.filePath, msg.line);
          break;
        case "runFile":
          await this.runActiveFile();
          break;
        case "runSelection":
          await this.runSelectedCode();
          break;
        case "newFile":
          await this._newFile(msg.path, msg.content);
          break;
        case "saveFile":
          await this.saveActiveFile();
          break;
        case "deleteFile":
          await this._deleteFile(msg.path);
          break;
        case "renameFile":
          await this._renameFile(msg.path, msg.newName);
          break;
        case "writeFile":
          await this._writeFile(msg.path, msg.content);
          break;
        case "editFile":
          await this._editFile(msg.path, msg.oldStr, msg.newStr);
          break;
        case "deepseekSend":
          await this._handleSend(msg.text, msg.mode || "Chat");
          break;
        case "stopAgent":
          this._stopAgent();
          break;
      }
    });
    this._postSettings();
    this.postMessage({ type: "historyUpdated", messages: this._messages }, webviewView.viewType);
    this._handleTabMessage(this._tabForView(webviewView.viewType), {});
  }

  refreshAllTabs() {
    const editor = vscode.window.activeTextEditor;
    if (editor) {
      this.postMessage({ type: "activeFileChanged", filePath: editor.document.fileName });
    }
  }

  postMessage(message: any, viewType?: string) {
    if (viewType) {
      this._views.get(viewType)?.webview.postMessage(message);
      return;
    }
    for (const view of this._views.values()) {
      view.webview.postMessage(message);
    }
  }

  getRecentFilesList(): string[] {
    return this._recentFiles;
  }

  setRecentFilesList(files: string[]) {
    this._recentFiles = files;
    this._context.globalState.update("novacode.recentFiles", files);
  }

  clearChat(): void {
    this._messages = [];
    this._currentTab = "chat";
    this.postMessage({ type: "clear" });
    this.postMessage({ type: "switchToChat" });
    this._context.globalState.update("novacode.chatHistory", []);
  }

  saveHistory() {
    const history = this._messages.map(m => ({ role: m.role, content: m.content, mode: m.mode }));
    this._context.globalState.update("novacode.chatHistory", history);
    this._writeHistoryFile(history);
    this.postMessage({ type: "historySaved", timestamp: Date.now() });
    vscode.window.showInformationMessage("Chat history saved");
  }

  async runActiveFile(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("No active file to run");
      return;
    }
    const filePath = editor.document.fileName;
    const lang = editor.document.languageId;
    await this._runFileInTerminal(filePath, lang);
  }

  async runSelectedCode(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("No active editor");
      return;
    }
    const selection = editor.document.getText(editor.selection);
    if (!selection) {
      vscode.window.showWarningMessage("No code selected");
      return;
    }
    const lang = editor.document.languageId;
    await this._runCodeInTerminal(selection, lang);
  }

  private async _runFileInTerminal(filePath: string, lang: string): Promise<void> {
    const ext = path.extname(filePath).toLowerCase();
    const terminalName = `NovaCode: ${path.basename(filePath)}`;
    let terminal = vscode.window.terminals.find(t => t.name === terminalName);
    if (!terminal) {
      terminal = vscode.window.createTerminal({ name: terminalName, cwd: path.dirname(filePath) });
    }

    let command = "";
    if (ext === ".py") {
      command = this._settings.pythonPath || (process.platform === "win32" ? "python" : "python3");
      command = `${command} "${filePath}"`;
    } else if (ext === ".js" || ext === ".ts" || ext === ".jsx" || ext === ".tsx") {
      command = `node "${filePath}"`;
    } else if (ext === ".sh" || ext === ".bash") {
      command = `bash "${filePath}"`;
    } else if (ext === ".ps1") {
      command = `powershell -ExecutionPolicy Bypass -File "${filePath}"`;
    } else {
      vscode.window.showWarningMessage(`Cannot run files of type: ${ext}`);
      return;
    }

    terminal.sendText(command);
    await vscode.commands.executeCommand("workbench.action.terminal.focus");
  }

  private async _runCodeInTerminal(code: string, lang: string): Promise<void> {
    const terminalName = `NovaCode: Selected ${lang}`;
    let terminal = vscode.window.terminals.find(t => t.name === terminalName);
    if (!terminal) {
      const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "";
      terminal = vscode.window.createTerminal({ name: terminalName, cwd });
    }

    if (lang === "python") {
      const tempFile = path.join(vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || "", ".novacode_selected.py");
      fs.writeFileSync(tempFile, code, "utf-8");
      terminal.sendText((this._settings.pythonPath || (process.platform === "win32" ? "python" : "python3")) + ` "${tempFile}"`);
    } else if (lang === "javascript" || lang === "typescript" || lang === "json") {
      terminal.sendText(code);
    } else {
      terminal.sendText(`# ${lang} code:\n${code}`);
    }
    await vscode.commands.executeCommand("workbench.action.terminal.focus");
  }

  private _handleTabMessage(tab: string, payload: any) {
    switch (tab) {
      case "explorer":
        this._postExplorerData(payload || { base: "." });
        break;
      case "recent":
        this._postRecentFiles();
        break;
      case "functions":
        if (payload?.filePath) {
          this._postFunctionsData(payload);
        } else if (vscode.window.activeTextEditor) {
          this._postFunctionsData({ filePath: vscode.window.activeTextEditor.document.fileName });
        }
        break;
      case "deepseek":
        this._postSettings();
        break;
      case "runner":
        this._postRunnerOutput();
        break;
    }
  }

  private _postSettings(): void {
    const cfg = vscode.workspace.getConfiguration("novacode");
    let modelName = "no model";
    if (this._settings.backend === "gguf" && this._settings.modelPath) {
      modelName = path.basename(this._settings.modelPath);
    } else if (this._settings.backend === "openrouter") {
      modelName = cfg.get<string>("openrouterModel") || "not set";
    } else if (this._settings.backend === "nvidia") {
      modelName = cfg.get<string>("nvidiaModel") || "not set";
    }
    this.postMessage({
      type: "settings",
      backend: this._settings.backend,
      modelName,
      defaultMode: this._settings.defaultChatMode,
      contextSize: this._settings.contextSize,
      deepseekModel: this._settings.deepseekModel,
    });
  }

  private _postExplorerData(payload: any) {
    const base = (payload && payload.base) || ".";
    const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!root) {
      this.postMessage({ type: "explorerData", base, entries: [{ name: "No workspace open", path: "", isDir: true, children: [] }] });
      return;
    }
    const basePath = path.resolve(root, base);
    if (!basePath.startsWith(path.resolve(root))) {
      this.postMessage({ type: "explorerData", base: ".", entries: [] });
      return;
    }
    if (!fs.existsSync(basePath) || !fs.statSync(basePath).isDirectory()) {
      this.postMessage({ type: "explorerData", base, entries: [] });
      return;
    }
    const items = fs.readdirSync(basePath, { withFileTypes: true });
    const entries = items.map(item => ({
      name: item.name,
      path: path.relative(root, path.join(basePath, item.name)).replace(/\\/g, "/") || ".",
      isDir: item.isDirectory(),
      children: [],
    })).sort((a, b) => {
      if (a.isDir && !b.isDir) return -1;
      if (!a.isDir && b.isDir) return 1;
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });
    this.postMessage({ type: "explorerData", base, entries });
  }

  private _postRecentFiles() {
    const recent = this._recentFiles.slice(0, this._settings.recentFilesMax);
    const entries = recent.map(p => ({
      name: path.basename(p),
      path: p,
      isDir: false,
    }));
    this.postMessage({ type: "recentFilesData", entries });
  }

  private _postFunctionsData(payload: any) {
    const filePath = payload?.filePath;
    if (!filePath) {
      this.postMessage({ type: "functionsData", filePath: "", entries: [] });
      return;
    }
    let entries: { name: string; kind: string; line: number }[] = [];
    try {
      const text = fs.readFileSync(filePath, "utf-8");
      const lines = text.split("\n");
      const patterns = [
        { pattern: /^\s*class\s+([A-Za-z_$][\w$]*)/g, kind: "class" },
        { pattern: /^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)/g, kind: "function" },
        { pattern: /^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/g, kind: "function" },
        { pattern: /^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/g, kind: "function" },
        { pattern: /^\s*(?:public|private|protected)?\s*(?:static\s+)?(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*[:{]/g, kind: "method" },
        { pattern: /^\s*(?:export\s+)?(?:class|interface|type|enum)\s+([A-Za-z_$][\w$]*)/g, kind: "symbol" },
      ];
      for (let i = 0; i < lines.length; i++) {
        for (const sym of patterns) {
          sym.pattern.lastIndex = 0;
          const match = sym.pattern.exec(lines[i]);
          if (match) {
            entries.push({ name: match[1], kind: sym.kind, line: i + 1 });
            break;
          }
        }
      }
    } catch (_err) {
      entries = [];
    }
    this.postMessage({ type: "functionsData", filePath, entries });
  }

  private _postRunnerOutput() {
    this.postMessage({ type: "runnerOutput", text: this._runnerOutput || "# Code output will appear here after you run a file or selection." });
  }

  private async _openFile(filePath: string) {
    try {
      const uri = vscode.Uri.file(this._resolveUserFile(filePath));
      await vscode.commands.executeCommand("vscode.open", uri);
    } catch (_err) {
      vscode.window.showWarningMessage("Could not open: " + filePath);
    }
  }

  private async _gotoFunction(filePath: string, line: number) {
    try {
      const uri = vscode.Uri.file(this._resolveUserFile(filePath));
      const doc = await vscode.workspace.openTextDocument(uri);
      const editor = await vscode.window.showTextDocument(doc);
      const pos = new vscode.Position(Math.max(0, Number(line || 1) - 1), 0);
      editor.selection = new vscode.Selection(pos, pos);
      editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);
    } catch (_err) {
      vscode.window.showWarningMessage("Could not jump to symbol");
    }
  }

  private async _handleSend(text: string, mode: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    let prompt = text;
    if (editor) {
      const sel = editor.document.getText(editor.selection);
      if (sel) { prompt += "\n\n[Selected code from " + path.basename(editor.document.fileName) + "]:\n```\n" + sel + "\n```"; }
    }
    this._messages.push({ role: "user", content: prompt, mode });
    try {
      const resp = await this._callBridge(prompt, mode);
      this._messages.push({ role: "assistant", content: resp });
      this._persistHistoryIfEnabled();
      this.postMessage({ type: "response", text: resp });
      this.postMessage({ type: "historyUpdated", messages: this._messages });
    } catch (err: any) {
      const msg = err?.message || String(err);
      this._messages.push({ role: "error", content: msg });
      this._persistHistoryIfEnabled();
      this.postMessage({ type: "error", text: msg });
    }
  }

  private async _handleRetry(): Promise<void> {
    for (let i = this._messages.length - 1; i >= 0; i--) {
      if (this._messages[i].role === "user") {
        const m = this._messages[i];
        this._messages = this._messages.slice(0, i + 1);
        this.postMessage({ type: "retryStart" });
        try {
          const resp = await this._callBridge(m.content, m.mode || "Chat");
          this._messages.push({ role: "assistant", content: resp });
          this._persistHistoryIfEnabled();
          this.postMessage({ type: "response", text: resp });
          this.postMessage({ type: "historyUpdated", messages: this._messages });
        } catch (err: any) {
          const msg = err?.message || String(err);
          this._messages.push({ role: "error", content: msg });
          this._persistHistoryIfEnabled();
          this.postMessage({ type: "error", text: msg });
        }
        break;
      }
    }
  }

  private async _insertCode(code: string): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (editor) {
      await editor.edit(eb => eb.insert(editor.selection.active, code));
    } else {
      const doc = await vscode.workspace.openTextDocument({ content: code });
      await vscode.window.showTextDocument(doc);
    }
  }

  async saveActiveFile(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!editor) { vscode.window.showWarningMessage("No active file to save"); return; }
    await editor.document.save();
    vscode.window.showInformationMessage("Saved: " + path.basename(editor.document.fileName));
  }

  private async _newFile(filePath: string, content = ""): Promise<void> {
    const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!root) { vscode.window.showWarningMessage("No workspace open"); return; }
    const target = path.isAbsolute(filePath) ? filePath : path.resolve(root, filePath);
    if (!target.startsWith(root)) { vscode.window.showWarningMessage("Path escapes workspace"); return; }
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content, "utf-8");
    const uri = vscode.Uri.file(target);
    await vscode.commands.executeCommand("vscode.open", uri);
    vscode.window.showInformationMessage("Created: " + path.basename(target));
    this.postMessage({ type: "refreshExplorer" });
  }

  private async _deleteFile(filePath: string): Promise<void> {
    const resolved = this._resolveUserFile(filePath);
    if (!fs.existsSync(resolved)) { vscode.window.showWarningMessage("File not found: " + filePath); return; }
    const confirm = await vscode.window.showWarningMessage(`Delete ${path.basename(resolved)}?`, "Delete", "Cancel");
    if (confirm !== "Delete") return;
    try {
      fs.unlinkSync(resolved);
      vscode.window.showInformationMessage("Deleted: " + path.basename(resolved));
      this.postMessage({ type: "refreshExplorer" });
    } catch (err: any) {
      vscode.window.showErrorMessage("Delete failed: " + (err?.message || String(err)));
    }
  }

  private async _renameFile(filePath: string, newName: string): Promise<void> {
    const resolved = this._resolveUserFile(filePath);
    if (!fs.existsSync(resolved)) { vscode.window.showWarningMessage("File not found: " + filePath); return; }
    const newPath = path.resolve(path.dirname(resolved), newName);
    try {
      fs.renameSync(resolved, newPath);
      await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(newPath));
      vscode.window.showInformationMessage("Renamed to: " + newName);
      this.postMessage({ type: "refreshExplorer" });
    } catch (err: any) {
      vscode.window.showErrorMessage("Rename failed: " + (err?.message || String(err)));
    }
  }

  private async _writeFile(filePath: string, content: string): Promise<void> {
    const resolved = this._resolveUserFile(filePath);
    fs.mkdirSync(path.dirname(resolved), { recursive: true });
    fs.writeFileSync(resolved, content, "utf-8");
    vscode.window.showInformationMessage("Wrote: " + path.basename(resolved));
    this.postMessage({ type: "refreshExplorer" });
  }

  private async _editFile(filePath: string, oldStr: string, newStr: string): Promise<void> {
    const resolved = this._resolveUserFile(filePath);
    if (!fs.existsSync(resolved)) { vscode.window.showWarningMessage("File not found: " + filePath); return; }
    const text = fs.readFileSync(resolved, "utf-8");
    const count = text.split(oldStr).length - 1;
    if (count === 0) { vscode.window.showWarningMessage("old_str not found in file"); return; }
    if (count > 1) { vscode.window.showWarningMessage(`old_str matched ${count} times; expected exactly once`); return; }
    const updated = text.replace(oldStr, newStr);
    fs.writeFileSync(resolved, updated, "utf-8");
    vscode.window.showInformationMessage("Edited: " + path.basename(resolved));
    this.postMessage({ type: "refreshExplorer" });
  }

  private _callBridge(prompt: string, mode: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const projectRoot = this._resolveProjectRoot();
      const candidateBridgePaths = [
        path.join(projectRoot, "bridge", "chat_bridge.py"),
        path.join(projectRoot, "vscode-extension-starter", "bridge", "chat_bridge.py"),
        path.join(this._context.extensionUri.fsPath, "bridge", "chat_bridge.py"),
      ];
      const actualBridge = candidateBridgePaths.find(p => fs.existsSync(p)) || candidateBridgePaths[0];

      const cfg = vscode.workspace.getConfiguration("novacode");
      const payload = JSON.stringify({
        prompt,
        mode,
        backend: this._settings.backend,
        model_path: this._settings.modelPath,
        context_size: this._settings.contextSize,
        gpu_layers: this._settings.gpuLayers,
        threads: this._settings.threads,
        temperature: this._settings.temperature,
        max_tokens: this._settings.maxTokens,
        openrouter_api_key: cfg.get<string>("openrouterApiKey") || "",
        openrouter_model: cfg.get<string>("openrouterModel") || "",
        nvidia_api_key: cfg.get<string>("nvidiaApiKey") || "",
        nvidia_model: cfg.get<string>("nvidiaModel") || "",
        deepseek_api_key: cfg.get<string>("deepseekApiKey") || "",
        deepseek_model: this._settings.deepseekModel,
        workspace: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || projectRoot,
      });

      const python = this._settings.pythonPath || (process.platform === "win32" ? "python" : "python3");
      const childProcess = child.execFile(python, [actualBridge, payload], {
        cwd: projectRoot,
        windowsHide: true,
        timeout: 300000,
        maxBuffer: 20 * 1024 * 1024,
      }, (error, stdout, stderr) => {
        this._activeBridge = null;
        if (stdout && stdout.trim()) {
          try {
            const r = JSON.parse(stdout.trim());
            if (r.ok) {
              if (r.runner_output) {
                this._runnerOutput = r.runner_output;
                this.postMessage({ type: "runnerOutput", text: r.runner_output });
              }
              resolve(r.text || "(empty)");
              return;
            }
            reject(new Error(r.error || "Bridge error"));
            return;
          } catch (_err) { /* stdout wasn't valid JSON, fall through */ }
        }
        if (error) {
          reject(new Error(error.message));
          return;
        }
        reject(new Error("Invalid bridge output: " + (stdout || "").slice(0, 200)));
      });
      this._activeBridge = childProcess;
    });
  }

  private _stopAgent(): void {
    if (this._activeBridge) {
      try {
        if (process.platform === "win32") {
          child.execFile("taskkill", ["/F", "/T", "/PID", String(this._activeBridge.pid || 0)]);
        } else {
          this._activeBridge.kill("SIGTERM");
        }
      } catch (_err) { /* ignore */ }
      this._activeBridge = null;
      this.postMessage({ type: "error", text: "Agent stopped by user." });
    }
  }

  private _resolveProjectRoot(): string {
    if (this._settings.projectRoot) { return this._settings.projectRoot; }
    const ext = this._context.extensionUri.fsPath;
    const parent = path.dirname(ext);
    if (fs.existsSync(path.join(parent, "agent", "providers.py"))) { return parent; }
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || ext;
  }

  private _persistHistoryIfEnabled(): void {
    if (!this._settings.rememberChatHistory) {
      return;
    }
    const history = this._messages.map(m => ({ role: m.role, content: m.content, mode: m.mode }));
    this._context.globalState.update("novacode.chatHistory", history);
    this._writeHistoryFile(history);
  }

  private _writeHistoryFile(history: ChatMessage[]): void {
    const configuredPath = this._settings.chatHistoryPath;
    if (!configuredPath) {
      return;
    }
    try {
      const target = path.isAbsolute(configuredPath)
        ? configuredPath
        : path.join(this._context.globalStorageUri.fsPath, configuredPath);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, JSON.stringify(history, null, 2), "utf-8");
    } catch (_err) {
      vscode.window.showWarningMessage("NovaCode could not write chat history file");
    }
  }

  private _resolveUserFile(filePath: string): string {
    if (path.isAbsolute(filePath)) {
      return filePath;
    }
    const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || this._resolveProjectRoot();
    return path.resolve(root, filePath);
  }

  private _tabForView(_viewType: string): TabId {
    return "chat";
  }
}