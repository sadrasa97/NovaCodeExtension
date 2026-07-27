import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import { ChatViewProvider } from "./chatViewProvider";
import { SettingsManager } from "./settings";

export function activate(context: vscode.ExtensionContext): void {
  const settings = new SettingsManager();
  const chatProvider = new ChatViewProvider(context, settings);

  for (const viewId of [
    "novacode.chatView",
  ]) {
    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider(viewId, chatProvider, {
        webviewOptions: { retainContextWhenHidden: true },
      })
    );
  }

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.newChat", () => chatProvider.clearChat())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.openSettings", () => settings.openSettingsUI())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.setWorkspace", async () => {
      const folder = await vscode.window.showOpenDialog({
        canSelectFiles: false, canSelectFolders: true, canSelectMany: false,
        openLabel: "Set Working Directory",
      });
      if (folder && folder[0]) {
        const config = vscode.workspace.getConfiguration("novacode");
        await config.update("projectRoot", folder[0].fsPath, vscode.ConfigurationTarget.Global);
        vscode.window.showInformationMessage("NovaCode project root: " + folder[0].fsPath);
        chatProvider.refreshAllTabs();
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.setModelsDirectory", () => settings.selectModelsDirectoryInteractive())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.selectModel", () => settings.selectModelInteractive())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.saveChatHistory", () => chatProvider.saveHistory())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.clearChatHistory", () => {
      chatProvider.clearChat();
      vscode.window.showInformationMessage("Chat history cleared");
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.runFile", () => chatProvider.runActiveFile())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.newFile", async () => {
      const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!root) { vscode.window.showWarningMessage("No workspace open"); return; }
      const name = await vscode.window.showInputBox({ placeHolder: "file.txt", prompt: "New file name (relative to workspace root)" });
      if (!name) return;
      const target = path.resolve(root, name);
      if (!target.startsWith(root)) { vscode.window.showWarningMessage("Path escapes workspace"); return; }
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, "");
      const uri = vscode.Uri.file(target);
      await vscode.commands.executeCommand("vscode.open", uri);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.saveFile", () => chatProvider.saveActiveFile())
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.deleteFile", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) { vscode.window.showWarningMessage("No active file"); return; }
      const filePath = editor.document.fileName;
      const confirm = await vscode.window.showWarningMessage(`Delete ${path.basename(filePath)}?`, "Delete", "Cancel");
      if (confirm !== "Delete") return;
      try {
        fs.unlinkSync(filePath);
        vscode.window.showInformationMessage("Deleted: " + path.basename(filePath));
      } catch (err: any) {
        vscode.window.showErrorMessage("Delete failed: " + (err?.message || String(err)));
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.renameFile", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) { vscode.window.showWarningMessage("No active file"); return; }
      const oldPath = editor.document.fileName;
      const oldName = path.basename(oldPath);
      const newName = await vscode.window.showInputBox({ value: oldName, prompt: "New file name" });
      if (!newName || newName === oldName) return;
      const newPath = path.resolve(path.dirname(oldPath), newName);
      try {
        fs.renameSync(oldPath, newPath);
        await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(newPath));
        vscode.window.showInformationMessage("Renamed to: " + newName);
      } catch (err: any) {
        vscode.window.showErrorMessage("Rename failed: " + (err?.message || String(err)));
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("novacode.runSelection", () => chatProvider.runSelectedCode())
  );

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((e) => {
      const recentMax = settings.recentFilesMax || 25;
      const history = chatProvider.getRecentFilesList();
      const path = e.uri.fsPath;
      if (!history.includes(path)) {
        history.unshift(path);
        while (history.length > recentMax) {
          history.pop();
        }
        chatProvider.setRecentFilesList(history);
        chatProvider.postMessage({ type: "recentFilesUpdated", files: history });
      }
    })
  );

  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((e) => {
      if (e) {
        chatProvider.postMessage({ type: "activeFileChanged", filePath: e.document.fileName });
      }
    })
  );

  const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBar.text = "$(hubot) NovaCode";
  statusBar.tooltip = "NovaCode AI Chat";
  statusBar.command = "novacode.chatView.focus";
  statusBar.show();
  context.subscriptions.push(statusBar);

  if (vscode.window.activeTextEditor) {
    chatProvider.postMessage({
      type: "activeFileChanged",
      filePath: vscode.window.activeTextEditor.document.fileName,
    });
  }
}

export function deactivate(): void {}