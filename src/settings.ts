import * as vscode from "vscode";
import * as path from "path";

export class SettingsManager {
  private _recentFilesKey = "novacode.recentFiles";

  getConfig(): vscode.WorkspaceConfiguration {
    return vscode.workspace.getConfiguration("novacode");
  }

  get backend(): string { return this.getConfig().get<string>("backend") || "gguf"; }
  get modelPath(): string { return this.getConfig().get<string>("modelPath") || ""; }
  get modelsDirectory(): string { return this.getConfig().get<string>("modelsDirectory") || ""; }
  get projectRoot(): string { return this.getConfig().get<string>("projectRoot") || ""; }
  get pythonPath(): string { return this.getConfig().get<string>("pythonPath") || ""; }
  get defaultChatMode(): string { return this.getConfig().get<string>("defaultChatMode") || "Chat"; }
  get contextSize(): number { return this.getConfig().get<number>("contextSize") || 4096; }
  get threads(): number | null { return this.getConfig().get<number | null>("threads") ?? null; }
  get gpuLayers(): number { return this.getConfig().get<number>("gpuLayers") ?? -1; }
  get temperature(): number { return this.getConfig().get<number>("temperature") || 0.7; }
  get maxTokens(): number { return this.getConfig().get<number>("maxTokens") || 2048; }

  get deepseekApiKey(): string { return this.getConfig().get<string>("deepseekApiKey") || ""; }
  get deepseekModel(): string { return this.getConfig().get<string>("deepseekModel") || "deepseek-chat"; }

  get openaiApiKey(): string { return this.getConfig().get<string>("openaiApiKey") || ""; }
  get openaiBaseUrl(): string { return this.getConfig().get<string>("openaiBaseUrl") || ""; }
  get openaiModel(): string { return this.getConfig().get<string>("openaiModel") || ""; }
  get rememberChatHistory(): boolean { return this.getConfig().get<boolean>("rememberChatHistory") ?? true; }
  get chatHistoryPath(): string { return this.getConfig().get<string>("chatHistoryPath") || ""; }
  get recentFilesMax(): number { return this.getConfig().get<number>("recentFilesMax") || 25; }
  get runPythonInTerminal(): boolean { return this.getConfig().get<boolean>("runPythonInTerminal") ?? true; }
  get runNodeInTerminal(): boolean { return this.getConfig().get<boolean>("runNodeInTerminal") ?? true; }

  async listModels(): Promise<string[]> {
    const dir = this.modelsDirectory;
    if (!dir || !vscode.workspace.fs) { return []; }
    try {
      const entries = await vscode.workspace.fs.readDirectory(vscode.Uri.file(dir));
      return entries.filter(([name]) => name.endsWith(".gguf")).map(([name]) => name);
    } catch (_err) {
      return [];
    }
  }

  async selectModelInteractive(): Promise<void> {
    const config = this.getConfig();
    const backend = this.backend;

    if (backend === "gguf") {
      const models = await this.listModels();
      if (models.length > 0) {
        const pick = await vscode.window.showQuickPick(models, { title: "Select GGUF Model" });
        if (pick) {
          await config.update("modelPath", path.join(this.modelsDirectory, pick), vscode.ConfigurationTarget.Global);
          vscode.window.showInformationMessage("Model: " + pick);
        }
      } else {
        const file = await vscode.window.showOpenDialog({
          canSelectFiles: true, filters: { "GGUF": ["gguf"] }, openLabel: "Select Model"
        });
        if (file && file[0]) {
          await config.update("modelPath", file[0].fsPath, vscode.ConfigurationTarget.Global);
          await config.update("modelsDirectory", path.dirname(file[0].fsPath), vscode.ConfigurationTarget.Global);
          vscode.window.showInformationMessage("Model: " + path.basename(file[0].fsPath));
        }
      }
    } else if (backend === "openrouter") {
      const model = await vscode.window.showInputBox({
        title: "OpenRouter Model", prompt: "e.g. meta-llama/llama-3-70b-instruct or deepseek/deepseek-chat",
        value: config.get<string>("openrouterModel") || ""
      });
      if (model !== undefined) { await config.update("openrouterModel", model, vscode.ConfigurationTarget.Global); }
     } else if (backend === "nvidia") {
       const model = await vscode.window.showInputBox({
         title: "NVIDIA Model", value: config.get<string>("nvidiaModel") || ""
       });
       if (model !== undefined) { await config.update("nvidiaModel", model, vscode.ConfigurationTarget.Global); }
     } else if (backend === "openai") {
       const model = await vscode.window.showInputBox({
         title: "OpenAI Model", prompt: "e.g. gpt-4o, gpt-4o-mini, gpt-4.1",
         value: config.get<string>("openaiModel") || ""
       });
       if (model !== undefined) { await config.update("openaiModel", model, vscode.ConfigurationTarget.Global); }
       const baseUrl = await vscode.window.showInputBox({
         title: "OpenAI Base URL", prompt: "e.g. https://api.openai.com/v1 or your custom endpoint",
         value: config.get<string>("openaiBaseUrl") || ""
       });
       if (baseUrl !== undefined) { await config.update("openaiBaseUrl", baseUrl, vscode.ConfigurationTarget.Global); }
     }
  }

  async selectModelsDirectoryInteractive(): Promise<void> {
    const folder = await vscode.window.showOpenDialog({
      canSelectFiles: false,
      canSelectFolders: true,
      canSelectMany: false,
      openLabel: "Set Models Directory",
    });
    if (folder && folder[0]) {
      await this.getConfig().update("modelsDirectory", folder[0].fsPath, vscode.ConfigurationTarget.Global);
      vscode.window.showInformationMessage("NovaCode models directory: " + folder[0].fsPath);
    }
  }

  openSettingsUI(): void {
    vscode.commands.executeCommand("workbench.action.openSettings", "novacode");
  }
}