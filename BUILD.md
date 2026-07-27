# NovaCode VS Code Extension Build Guide

## One-time setup

Install Node.js 20 or newer.

Optional dependency install (you can skip this if npm install is slow or stuck):

```powershell
cd D:\NOvaCode\vscode-extension-starter
npm install
```

The build scripts in this repo auto-fetch their required tools via `npx`, so `npm run compile` and `npm run package` can work even if local `node_modules` is not fully healthy.

Install Python dependencies for the NovaCode backend:

```powershell
cd D:\NOvaCode
python -m pip install -r requirements.txt
python -m pip install llama-cpp-python
```

Important: on Windows, the official prebuilt `llama-cpp-python` wheels are only published
for Python 3.10, 3.11, and 3.12. If your default `python` is 3.13 or newer, point
`novacode.pythonPath` at a Python 3.12 installation before using the GGUF backend.

For CUDA builds of `llama-cpp-python`, use the wheel/index that matches your GPU and CUDA version.

## Build the extension

```powershell
cd D:\NOvaCode\vscode-extension-starter
npm run compile
npm run package
```

The output is a `.vsix` file such as:

```text
D:\NOvaCode\vscode-extension-starter\novacode-chat-1.0.1.vsix
```

## Install in VS Code

```powershell
code --install-extension .\novacode-chat-1.0.1.vsix
```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
Or open VS Code, run `Extensions: Install from VSIX...`, and select the generated file.

## Updating later

1. Edit the extension files.
2. Increase `version` in `package.json`.
3. Run `npm run compile`.
4. Run `npm run package`.
5. Install the new `.vsix` in VS Code.

## Configure NovaCode

Open VS Code settings and search `NovaCode`, or use the NovaCode sidebar toolbar.

Important settings:

- `novacode.backend`: `gguf`, `openrouter`, or `nvidia`.
- `novacode.modelPath`: exact local `.gguf` model path.
- `novacode.modelsDirectory`: folder that contains `.gguf` models.
- `novacode.projectRoot`: root of the NovaCode Python project, normally `D:\NOvaCode`.
- `novacode.pythonPath`: optional Python executable path. Leave empty to use `python`.
- `novacode.openrouterApiKey` / `novacode.openrouterModel`: OpenRouter backend.
- `novacode.nvidiaApiKey` / `novacode.nvidiaModel`: NVIDIA backend.

The extension adds a NovaCode activity bar view with chat, model picker, working directory selection, selected-code context, code copy, and code insertion.
