import * as vscode from "vscode";

export function getWebviewHtml(webview: vscode.Webview, _extensionUri: vscode.Uri, initialTab = "chat"): string {
  const nonce = getNonce();
  const cspSource = webview.cspSource;

  return String.raw`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${cspSource} https: data:; style-src ${cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>NovaCode</title>
  <style>
    :root {
      color-scheme: dark light;
      --bg: var(--vscode-sideBar-background);
      --fg: var(--vscode-sideBar-foreground);
      --muted: var(--vscode-descriptionForeground);
      --panel: var(--vscode-editor-background);
      --input: var(--vscode-input-background);
      --input-fg: var(--vscode-input-foreground);
      --border: var(--vscode-sideBarSectionHeader-border);
      --focus: var(--vscode-focusBorder);
      --button: var(--vscode-button-background);
      --button-fg: var(--vscode-button-foreground);
      --button-hover: var(--vscode-button-hoverBackground);
      --secondary: var(--vscode-button-secondaryBackground);
      --secondary-hover: var(--vscode-button-secondaryHoverBackground);
      --code: var(--vscode-textCodeBlock-background);
      --error: var(--vscode-errorForeground);
      --accent: var(--vscode-button-background, #2f7dff);
      --accent-2: #22d3ee;
      --accent-grad: linear-gradient(135deg, var(--accent), var(--accent-2));
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.18);
      --shadow-md: 0 4px 14px rgba(0,0,0,0.22);
      --radius-lg: 14px;
      --radius-md: 10px;
      --radius-sm: 7px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      height: 100vh;
      overflow: hidden;
      color: var(--fg);
      background: var(--bg);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      line-height: 1.5;
    }

    /* === Layout === */
    .shell { display: flex; flex-direction: column; height: 100vh; }
    .topbar { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--border); background: var(--panel); flex-shrink: 0; }
    .topbar .logo { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
    .topbar .logo svg { width: 20px; height: 20px; flex-shrink: 0; }
    .topbar .logo span { font-weight: 600; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .topbar .model-badge { font-size: 11px; color: var(--muted); background: var(--input); padding: 2px 8px; border-radius: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px; }
    .topbar .actions { display: flex; gap: 4px; flex-shrink: 0; }

    main { flex: 1; min-height: 0; overflow: hidden; position: relative; }
     .pane { height: 100%; overflow-y: auto; padding: 12px; display: none; position: relative; }
    .pane.active { display: block; }

    /* === Tabs === */
    .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); background: var(--panel); flex-shrink: 0; padding: 0 6px; }
    .tab {
      padding: 8px 14px; font-size: 12px; font-weight: 500; cursor: pointer;
      color: var(--muted); border-bottom: 2px solid transparent;
      border-radius: 6px 6px 0 0;
      transition: color .15s, border-color .15s, background .15s;
    }
    .tab:hover { color: var(--fg); background: color-mix(in srgb, var(--accent) 6%, transparent); }
    .tab.active { color: var(--fg); border-bottom-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, transparent); }

    /* === Messages === */
    .messages { display: flex; flex-direction: column; gap: 18px; padding-bottom: 132px; }
    .empty { color: var(--muted); text-align: center; padding: 40px 16px; line-height: 1.7; }
    .message { display: flex; flex-direction: column; gap: 4px; animation: msg-in .22s ease; }
    @keyframes msg-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
    .message.user { align-items: flex-end; }
    .meta { font-size: 10px; color: var(--muted); padding: 0 4px; letter-spacing: .02em; text-transform: uppercase; opacity: .75; }
    .bubble {
      max-width: 100%;
      padding: 11px 14px;
      border-radius: var(--radius-lg);
      background: var(--panel);
      border: 1px solid var(--border);
      line-height: 1.65;
      overflow-wrap: anywhere;
      word-break: break-word;
      box-shadow: var(--shadow-sm);
    }
    .user .bubble {
      background: var(--accent-grad);
      color: var(--button-fg);
      border-color: transparent;
      border-radius: var(--radius-lg) var(--radius-lg) 4px var(--radius-lg);
      box-shadow: 0 3px 10px color-mix(in srgb, var(--accent) 35%, transparent);
    }
    .assistant .bubble { border-radius: var(--radius-lg) var(--radius-lg) var(--radius-lg) 4px; }
    .error .bubble { background: color-mix(in srgb, var(--error) 10%, var(--panel)); border-color: color-mix(in srgb, var(--error) 30%, transparent); color: var(--error); }
    .typing .bubble { opacity: 0.85; }
    .typing .bubble::after { content: ""; display: inline-block; width: 4px; height: 14px; background: currentColor; margin-left: 4px; animation: blink 1s steps(2) infinite; vertical-align: middle; }
    @keyframes blink { 0% { opacity: 1; } 50% { opacity: 0; } }

    /* === Code blocks === */
    pre { overflow-x: auto; margin: 8px 0; padding: 10px 12px; border-radius: 8px; background: var(--code); border: 1px solid var(--border); font-size: 12px; }
    code { font-family: var(--vscode-editor-font-family); font-size: var(--vscode-editor-font-size); }
    .code-actions { display: flex; gap: 4px; margin: -4px 0 8px; }
    .code-actions button { min-height: 24px; padding: 0 8px; font-size: 11px; border-radius: 4px; color: var(--muted); background: var(--secondary); border: 1px solid var(--border); cursor: pointer; }
    .code-actions button:hover { color: var(--fg); background: var(--secondary-hover); }

    /* === File changes === */
    .file-change { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border); background: var(--panel); margin: 4px 0; font-size: 12px; }
    .file-change .icon { font-size: 14px; flex-shrink: 0; }
    .file-change .path { font-family: var(--vscode-editor-font-family); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-change .meta { color: var(--muted); font-size: 10px; }

    /* === Agent Todo List (Copilot-style) === */
    .agent-todo { margin: 8px 0; border-radius: 10px; border: 1px solid var(--border); background: var(--panel); overflow: hidden; }
    .agent-todo-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; font-size: 12px; font-weight: 600; color: var(--fg); border-bottom: 1px solid var(--border); background: color-mix(in srgb, var(--accent) 6%, var(--panel)); }
    .agent-todo-header .spinner { width: 14px; height: 14px; border: 2px solid var(--muted); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; flex-shrink: 0; }
    .agent-todo-header .check-all { color: #22c55e; font-size: 16px; flex-shrink: 0; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .agent-todo-list { list-style: none; padding: 0; margin: 0; }
    .agent-todo-item { display: flex; align-items: flex-start; gap: 10px; padding: 8px 12px; border-bottom: 1px solid color-mix(in srgb, var(--border) 50%, transparent); font-size: 12px; line-height: 1.5; transition: background .15s; }
    .agent-todo-item:last-child { border-bottom: none; }
    .agent-todo-item .todo-icon { width: 18px; height: 18px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; margin-top: 1px; }
    .agent-todo-item .todo-icon .circle { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--muted); }
    .agent-todo-item.in-progress .todo-icon .circle { border-color: var(--accent); border-top-color: transparent; animation: spin 0.8s linear infinite; }
    .agent-todo-item.completed .todo-icon svg { color: #22c55e; }
    .agent-todo-item .todo-text { flex: 1; color: var(--fg); }
    .agent-todo-item.pending .todo-text { color: var(--muted); }
    .agent-todo-item.completed .todo-text { color: var(--muted); text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--muted) 50%, transparent); }
    .agent-todo-item .todo-detail { font-size: 11px; color: var(--muted); margin-top: 2px; font-family: var(--vscode-editor-font-family); }
    .agent-tool-log { margin: 0 0 4px; padding: 4px 12px 4px 40px; font-size: 11px; color: var(--muted); font-family: var(--vscode-editor-font-family); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    /* === Composer === */
    .composer { padding: 10px 12px 12px; border-top: 1px solid var(--border); background: var(--panel); flex-shrink: 0; }
    .composer-box {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px 12px 8px;
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--input);
      box-shadow: var(--shadow-sm);
      transition: border-color .15s, box-shadow .15s;
    }
    .composer-box:focus-within {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
    }
    textarea {
      width: 100%;
      min-height: 44px;
      max-height: 150px;
      resize: none;
      border: 0;
      outline: 0;
      color: var(--input-fg);
      background: transparent;
      line-height: 1.55;
      padding-right: 40px; /* keep last line clear of the floating send button */
    }
    .controls { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .controls select {
      height: 26px; width: auto; min-width: 70px; padding: 0 8px;
      font-size: 11px; font-weight: 500; border-radius: var(--radius-sm);
      border: 1px solid var(--border); color: var(--input-fg); background: var(--secondary);
      transition: border-color .15s;
    }
    .controls select:hover { border-color: var(--accent); }
    .controls .spacer { flex: 1; }

    /* Send button floats in the bottom-right corner of the composer box so it
       never wraps/collides with the mode controls on a narrow sidebar. */
    .send {
      position: absolute;
      right: 10px;
      bottom: 8px;
      width: 30px;
      height: 30px;
      padding: 0;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
      border: none;
      color: var(--button-fg);
      background: var(--accent-grad);
      cursor: pointer;
      box-shadow: 0 2px 8px color-mix(in srgb, var(--accent) 45%, transparent);
      transition: transform .12s ease, box-shadow .15s ease, opacity .15s ease;
      flex-shrink: 0;
    }
    .send svg { width: 15px; height: 15px; stroke: currentColor; pointer-events: none; }
    .send:hover { transform: translateY(-1px) scale(1.05); box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 55%, transparent); }
    .send:active { transform: scale(0.94); }
    .send:disabled { opacity: 0.45; cursor: not-allowed; box-shadow: none; transform: none; }

    .refine-btn, .summarize-btn {
      height: 26px; padding: 0 10px; font-size: 11px; font-weight: 500;
      border-radius: var(--radius-sm);
      border: 1px solid var(--border);
      color: var(--muted);
      background: var(--secondary);
      cursor: pointer;
      display: inline-flex; align-items: center; gap: 4px;
      transition: color .15s, background .15s, border-color .15s, transform .1s;
    }
    .refine-btn:hover { color: var(--fg); background: var(--secondary-hover); border-color: var(--accent); }
    .summarize-btn:hover { color: var(--fg); background: var(--secondary-hover); border-color: var(--accent); }
    .refine-btn:active, .summarize-btn:active { transform: scale(0.96); }
    .refine-btn:disabled, .summarize-btn:disabled { opacity: 0.6; cursor: default; }

    /* === Status Dashboard === */
    .status-dashboard { display: flex; align-items: center; gap: 8px; padding: 4px 12px; border-bottom: 1px solid var(--border); background: color-mix(in srgb, var(--panel) 95%, var(--accent) 5%); font-size: 11px; color: var(--muted); flex-shrink: 0; }
    .status-item { display: flex; align-items: center; gap: 4px; }
    .status-item .label { opacity: 0.7; }
    .status-item .value { font-weight: 500; color: var(--fg); font-family: var(--vscode-editor-font-family); }
    .token-bar { width: 60px; height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; }
    .token-bar-fill { height: 100%; border-radius: 3px; background: var(--accent); transition: width .3s ease; }
    .context-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: var(--secondary); color: var(--muted); }

     /* === Scroll to bottom === */
     .scroll-bottom {
       position: absolute;
       bottom: 12px;
       right: 12px;
       width: 40px;
       height: 40px;
       border-radius: 50%;
       background: var(--accent);
       color: var(--button-fg);
       border: none;
       cursor: pointer;
       display: flex;
       align-items: center;
       justify-content: center;
       font-size: 18px;
       box-shadow: 0 2px 8px rgba(0,0,0,0.25);
       z-index: 10;
       transition: opacity .2s, transform .2s;
       opacity: 0;
       transform: translateY(8px);
       pointer-events: none;
     }
     .scroll-bottom.visible {
       opacity: 1;
       transform: translateY(0);
       pointer-events: auto;
     }
     .scroll-bottom:hover {
       opacity: 0.9;
       transform: translateY(-2px);
     }

    /* === Buttons === */
    button { font: inherit; cursor: pointer; }
    .icon-btn {
      width: 28px; height: 28px; padding: 0;
      display: inline-flex; align-items: center; justify-content: center;
      border-radius: var(--radius-sm);
      border: 1px solid transparent;
      color: var(--muted);
      background: transparent;
      transition: color .15s, background .15s, transform .1s, border-color .15s;
    }
    .icon-btn:hover { color: var(--fg); background: var(--secondary); border-color: var(--border); }
    .icon-btn:active { transform: scale(0.92); }
    .icon-btn svg { width: 14px; height: 14px; stroke: currentColor; pointer-events: none; }

    /* === Explorer === */
    .explorer-header { display: flex; gap: 6px; margin-bottom: 8px; align-items: center; }
    .explorer-header input { flex: 1; height: 28px; padding: 0 8px; font-size: 12px; border-radius: 5px; border: 1px solid var(--border); color: var(--input-fg); background: var(--input); }
    .explorer-item { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-radius: 5px; font-size: 12px; cursor: pointer; }
    .explorer-item:hover { background: var(--secondary); }
    .explorer-item .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .explorer-item .actions { display: none; gap: 4px; }
    .explorer-item:hover .actions { display: flex; }
    .explorer-item .actions button { min-height: 20px; padding: 0 6px; font-size: 10px; border-radius: 3px; color: var(--muted); background: var(--secondary); border: 1px solid var(--border); }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="logo">${novaMark()}<span>NovaCode</span></div>
      <span class="model-badge" id="modelName">No model</span>
      <div class="actions">
        <button class="icon-btn" id="pickModel" title="Select model">${iconSliders()}</button>
        <button class="icon-btn" id="openSettings" title="Settings">${iconGear()}</button>
        <button class="icon-btn" id="stopAgent" title="Stop">⏹</button>
      </div>
    </header>

    <div class="tabs">
      <div class="tab active" data-tab="chat">Chat</div>
      <div class="tab" data-tab="explorer">Explorer</div>
      <div class="tab" data-tab="terminal">Terminal</div>
    </div>

    <div class="status-dashboard" id="statusDashboard">
      <div class="status-item">
        <span class="label">Tokens:</span>
        <span class="value" id="tokenCount">0</span>
        <div class="token-bar"><div class="token-bar-fill" id="tokenBar" style="width: 0%"></div></div>
      </div>
      <div class="status-item">
        <span class="label">Context:</span>
        <span class="value context-badge" id="contextInfo">idle</span>
      </div>
      <div class="status-item">
        <span class="label">Files:</span>
        <span class="value" id="filesLoaded">0</span>
      </div>
    </div>

    <main>
      <section class="pane active" data-pane="chat"><div id="messages" class="messages"><div class="empty" id="empty">Ask anything about your code.<br>I can edit files, explain code, debug, and more.</div></div><button class="scroll-bottom" id="scrollBottom" title="Scroll to bottom">↓</button></section>
      <section class="pane" data-pane="explorer">
        <div class="explorer">
          <div class="explorer-header">
            <input id="explorerPath" value="." placeholder="Path" />
            <button class="icon-btn" id="explorerRefresh" title="Refresh">${iconRefresh()}</button>
            <button class="icon-btn" id="newFile" title="New File">+</button>
          </div>
          <div id="explorerList"></div>
        </div>
      </section>
      <section class="pane" data-pane="terminal">
        <div class="terminal-pane">
          <div class="explorer-header">
            <input id="terminalInput" placeholder="Enter command (ls, dir, cd, etc.)" style="flex:1" />
            <select id="shellType" style="height:28px;padding:0 6px;font-size:11px;border-radius:5px;border:1px solid var(--border);color:var(--input-fg);background:var(--input);">
              <option value="auto">Auto</option>
              <option value="powershell">PowerShell</option>
              <option value="cmd">CMD</option>
              <option value="bash">Bash</option>
            </select>
            <button class="icon-btn" id="terminalRun" title="Run">▶</button>
          </div>
          <pre id="terminalOutput" style="margin-top:8px;padding:10px;border-radius:8px;background:var(--code);border:1px solid var(--border);font-size:12px;max-height:calc(100vh - 250px);overflow:auto;white-space:pre-wrap;"></pre>
        </div>
      </section>
      </section>
    </main>

    <footer class="composer">
      <div class="composer-box">
        <textarea id="prompt" placeholder="Ask NovaCode anything..." rows="2"></textarea>
        <div class="controls">
          <select id="mode" title="Mode">
            <option>Agent</option><option>Chat</option><option>Plan</option><option>WebSearch</option>
          </select>
          <button class="refine-btn" id="refinePrompt" title="Refine your prompt with AI prompt engineering">✨ Refine</button>
          <button class="summarize-btn" id="summarizeChat" title="Summarize the conversation">📝 Summarize</button>
          <span class="spacer"></span>
          <button class="icon-btn" id="clearHistory" title="Clear">${iconTrash()}</button>
        </div>
        <button class="send" id="send" title="Send">${iconSend()}</button>
      </div>
    </footer>
  </div>

  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const initialTab = ${JSON.stringify(initialTab)};
    const state = { tab: "chat", messages: [] };
    const els = {
      modelName: document.getElementById("modelName"),
      messages: document.getElementById("messages"),
      empty: document.getElementById("empty"),
      prompt: document.getElementById("prompt"),
      mode: document.getElementById("mode"),
      send: document.getElementById("send"),
      tabs: document.querySelectorAll(".tab"),
       panes: document.querySelectorAll(".pane"),
       explorerList: document.getElementById("explorerList"),
       explorerPath: document.getElementById("explorerPath"),
       explorerRefresh: document.getElementById("explorerRefresh"),
       newFile: document.getElementById("newFile"),
       scrollBottom: document.getElementById("scrollBottom"),
       refinePrompt: document.getElementById("refinePrompt"),
       summarizeChat: document.getElementById("summarizeChat"),
       terminalInput: document.getElementById("terminalInput"),
       terminalOutput: document.getElementById("terminalOutput"),
       terminalRun: document.getElementById("terminalRun"),
       shellType: document.getElementById("shellType"),
       tokenCount: document.getElementById("tokenCount"),
       tokenBar: document.getElementById("tokenBar"),
       contextInfo: document.getElementById("contextInfo"),
       filesLoaded: document.getElementById("filesLoaded"),
     };
    let pending;
    let totalTokensUsed = 0;

    document.querySelectorAll(".tab").forEach(tab => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        els.tabs.forEach(t => t.classList.toggle("active", t === tab));
        els.panes.forEach(p => p.classList.toggle("active", p.dataset.pane === target));
        if (target === "explorer") requestExplorer();
        vscode.postMessage({ type: "switchTab", tab: target });
      });
    });

    // Terminal tab handlers
    function runTerminalCommand() {
      const cmd = els.terminalInput.value.trim();
      if (!cmd) return;
      els.terminalOutput.textContent += "$ " + cmd + "\n";
      vscode.postMessage({ type: "runTerminal", command: cmd, shellType: els.shellType.value });
      els.terminalInput.value = "";
    }
    els.terminalRun.addEventListener("click", runTerminalCommand);
    els.terminalInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); runTerminalCommand(); }
    });

    // Refine Prompt button
    els.refinePrompt.addEventListener("click", () => {
      const text = els.prompt.value.trim();
      if (!text) return;
      els.refinePrompt.disabled = true;
      els.refinePrompt.textContent = "⏳ Refining...";
      vscode.postMessage({ type: "enhancePrompt", text });
    });

    // Summarize button
    els.summarizeChat.addEventListener("click", () => {
      const allText = Array.from(document.querySelectorAll(".bubble"))
        .map(b => b.textContent).join("\n\n");
      if (!allText.trim()) return;
      els.summarizeChat.disabled = true;
      els.summarizeChat.textContent = "⏳...";
      vscode.postMessage({ type: "summarize", text: allText });
    });

    document.getElementById("pickModel").addEventListener("click", () => vscode.postMessage({ type: "openModelPicker" }));
    document.getElementById("openSettings").addEventListener("click", () => vscode.postMessage({ type: "openSettings" }));
    document.getElementById("stopAgent").addEventListener("click", () => vscode.postMessage({ type: "stopAgent" }));
    document.getElementById("clearHistory").addEventListener("click", () => vscode.postMessage({ type: "clearHistory" }));
     els.explorerRefresh.addEventListener("click", () => requestExplorer());
     els.newFile.addEventListener("click", () => {
       const name = prompt("New file name");
       if (!name) return;
       vscode.postMessage({ type: "newFile", path: (els.explorerPath.value || ".") + "/" + name });
     });

     const chatPane = document.querySelector(".pane[data-pane='chat']");
     if (chatPane) {
       chatPane.addEventListener("scroll", () => {
         const atBottom = chatPane.scrollHeight - chatPane.scrollTop - chatPane.clientHeight < 40;
         els.scrollBottom.classList.toggle("visible", !atBottom);
       });
     }
     els.scrollBottom.addEventListener("click", () => {
       scrollToBottom();
     });

    function requestExplorer() {
      vscode.postMessage({ type: "requestExplorer", payload: { base: els.explorerPath.value || "." } });
    }

    function renderExplorer(entries) {
      if (!entries || !entries.length) { els.explorerList.innerHTML = '<div class="explorer-empty">Empty directory</div>'; return; }
      els.explorerList.innerHTML = entries.map(e => {
        const actions = e.isDir
          ? '<button data-action="openDir" data-path="' + e.path + '">Open</button>'
          : '<button data-action="openFile" data-path="' + e.path + '">Open</button><button data-action="deleteFile" data-path="' + e.path + '">Delete</button>';
        return '<div class="explorer-item"><span class="name">' + (e.isDir ? '📁' : '📄') + ' ' + escapeHtml(e.name) + '</span><div class="actions">' + actions + '</div></div>';
      }).join("");
      els.explorerList.querySelectorAll("[data-action]").forEach(btn => {
        btn.addEventListener("click", () => {
          const action = btn.dataset.action;
          const p = btn.dataset.path;
          if (action === "openFile") vscode.postMessage({ type: "openFile", filePath: p });
          else if (action === "openDir") { els.explorerPath.value = p; requestExplorer(); }
          else if (action === "deleteFile") vscode.postMessage({ type: "deleteFile", path: p });
        });
      });
    }
    els.send.addEventListener("click", submit);
    els.prompt.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey) {
        if (event.isComposing) return;
        event.preventDefault();
        event.stopPropagation();
        submit();
      }
    });
    els.prompt.addEventListener("input", () => {
      els.prompt.style.height = "auto";
      els.prompt.style.height = Math.min(els.prompt.scrollHeight, 150) + "px";
    });


    function submit() {
      const text = els.prompt.value.trim();
      if (!text || els.send.disabled) return;
      append("user", text, els.mode.value);
      els.prompt.value = "";
      els.prompt.style.height = "auto";
      setBusy(true);
      vscode.postMessage({ type: "send", text, mode: els.mode.value });
    }

    function setBusy(value) {
      els.send.disabled = value;
      if (value) pending = append("assistant", "Thinking...", "NovaCode", true);
      else if (pending) { pending.remove(); pending = undefined; }
    }

    function scrollToBottom() {
      const pane = document.querySelector(".pane[data-pane='chat']");
      if (!pane) return;
      const doScroll = () => {
        pane.scrollTop = pane.scrollHeight + 9999;
        els.scrollBottom.classList.remove("visible");
      };
      doScroll();
      requestAnimationFrame(doScroll);
      setTimeout(doScroll, 50);
      setTimeout(doScroll, 150);
      setTimeout(doScroll, 300);
      setTimeout(doScroll, 600);
      setTimeout(doScroll, 1000);
    }

    // Auto-scroll when new content is added
    const chatMsgs = document.getElementById("messages");
    if (chatMsgs) {
      const observer = new MutationObserver(() => { scrollToBottom(); });
      observer.observe(chatMsgs, { childList: true, subtree: true, characterData: true });
    }

     function append(role, text, label, transient, doScroll = true) {
       els.empty.style.display = "none";
       const item = document.createElement("section");
       item.className = "message " + role;
       if (transient) item.classList.add("typing");
       const meta = document.createElement("div");
       meta.className = "meta";
       meta.textContent = label || (role === "user" ? "You" : "NovaCode");
       const bubble = document.createElement("div");
       bubble.className = "bubble";
       bubble.innerHTML = renderMarkdown(text || "");
       item.append(meta, bubble);
       els.messages.appendChild(item);
       if (doScroll) scrollToBottom();
       bindCodeActions(item);
       return item;
     }

    function appendAgentStep(title, detail, status) {
      els.empty.style.display = "none";
      const item = document.createElement("div");
      item.className = "agent-step " + (status || "");
      const titleEl = document.createElement("div");
      titleEl.className = "step-title";
      titleEl.textContent = title;
      item.appendChild(titleEl);
      if (detail) {
        const detailEl = document.createElement("div");
        detailEl.className = "step-detail";
        detailEl.textContent = detail;
        item.appendChild(detailEl);
      }
      els.messages.appendChild(item);
      scrollToBottom();
      return item;
    }

    // --- Agent Todo List (Copilot-style) ---
    let agentTodoContainer = null;
    let agentTodoListEl = null;
    let agentTodoHeaderEl = null;

    function renderAgentTodo(steps) {
      els.empty.style.display = "none";
      if (!agentTodoContainer) {
        agentTodoContainer = document.createElement("div");
        agentTodoContainer.className = "agent-todo";
        agentTodoHeaderEl = document.createElement("div");
        agentTodoHeaderEl.className = "agent-todo-header";
        agentTodoContainer.appendChild(agentTodoHeaderEl);
        agentTodoListEl = document.createElement("ul");
        agentTodoListEl.className = "agent-todo-list";
        agentTodoContainer.appendChild(agentTodoListEl);
        els.messages.appendChild(agentTodoContainer);
      }

      // Update header
      const allDone = steps.every(function(s) { return s.status === "completed"; });
      const inProgress = steps.find(function(s) { return s.status === "in-progress"; });
      agentTodoHeaderEl.innerHTML = allDone
        ? '<span class="check-all">✓</span> All steps completed'
        : '<div class="spinner"></div> ' + (inProgress ? escapeHtml(inProgress.title) : 'Working...');

      // Update items
      agentTodoListEl.innerHTML = "";
      steps.forEach(function(step) {
        const li = document.createElement("li");
        li.className = "agent-todo-item " + step.status;
        const iconDiv = document.createElement("div");
        iconDiv.className = "todo-icon";
        if (step.status === "completed") {
          iconDiv.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M6.27 10.87L3.13 7.73a.5.5 0 0 0-.7.7l3.5 3.5a.5.5 0 0 0 .7 0l7-7a.5.5 0 0 0-.7-.7L6.27 10.87z"/></svg>';
        } else {
          iconDiv.innerHTML = '<div class="circle"></div>';
        }
        const textDiv = document.createElement("div");
        textDiv.className = "todo-text";
        textDiv.textContent = step.title;
        li.append(iconDiv, textDiv);
        agentTodoListEl.appendChild(li);
      });
      scrollToBottom();
    }

    function appendToolLog(name, args) {
      if (!agentTodoContainer) { return; }
      // Remove previous tool log to keep it clean
      const prev = agentTodoContainer.parentElement.querySelector(".agent-tool-log");
      if (prev) { prev.remove(); }
      const log = document.createElement("div");
      log.className = "agent-tool-log";
      log.textContent = "⚡ " + name + "(" + (args || "") + ")";
      agentTodoContainer.after(log);
      scrollToBottom();
    }

    function clearAgentTodo() {
      agentTodoContainer = null;
      agentTodoListEl = null;
      agentTodoHeaderEl = null;
    }

    function appendFileChange(path, action) {
      const item = document.createElement("div");
      item.className = "file-change";
      const icons = { created: "🆕", modified: "✏️", deleted: "🗑️", renamed: "🔃" };
      item.innerHTML = '<div class="icon">' + (icons[action] || "📄") + '</div><div><div class="path">' + escapeHtml(path) + '</div><div class="meta">' + action + '</div></div>';
      els.messages.appendChild(item);
      scrollToBottom();
    }

     function renderHistory(messages) {
       els.messages.querySelectorAll(".message").forEach((node) => node.remove());
       els.empty.style.display = messages && messages.length ? "none" : "block";
       (messages || []).forEach((msg) => append(msg.role, msg.content, msg.mode || (msg.role === "user" ? "You" : "NovaCode"), false, false));
       scrollToBottom();
     }

    function renderMarkdown(text) {
      const progressMatch = text.match(/<!-- progress:(.*?) -->/);
      if (progressMatch) {
        try {
          const steps = JSON.parse(progressMatch[1]);
          steps.forEach((step, idx) => {
            const existing = document.querySelectorAll(".agent-step");
            if (idx < existing.length) {
              existing[idx].className = "agent-step " + (step.status === "completed" ? "completed" : step.status === "failed" ? "failed" : "pending");
            } else {
              appendAgentStep(step.title, "", step.status);
            }
          });
        } catch (_e) {}
      }
      return escapeHtml(text)
        .replace(/\x60\x60\x60([\w-]*)\n([\s\S]*?)\x60\x60\x60/g, (_m, _lang, code) => {
          const decoded = code.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
          return '<pre data-code="' + encodeURIComponent(decoded) + '"><code>' + code + '</code></pre><div class="code-actions"><button data-action="copy">Copy</button><button data-action="insert">Insert</button></div>';
        })
        .replace(/\*{2}([^*]+)\*{2}/g, "<strong>$1</strong>")
        .replace(/\x60([^\x60]+)\x60/g, "<code>$1</code>")
        .replace(/\r?\n/g, "<br>");
    }

    function bindCodeActions(root) {
      root.querySelectorAll("[data-action]").forEach((button) => {
        button.addEventListener("click", () => {
          const pre = button.parentElement.previousElementSibling;
          const code = decodeURIComponent(pre.dataset.code || "");
          vscode.postMessage({ type: button.dataset.action === "copy" ? "copyCode" : "insertCode", code });
        });
      });
    }


    function escapeHtml(value) {
      return String(value || "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch]);
    }

    // --- Streaming state ---
    let streamingItem = null;
    let streamingBubble = null;
    let streamingRaw = "";

    window.addEventListener("message", (event) => {
      const msg = event.data;
      if (msg.type === "settings") {
        els.modelName.textContent = msg.modelName || "No model";
        els.modelName.dataset.contextSize = String(msg.contextSize || 4096);
        if (msg.defaultMode) els.mode.value = msg.defaultMode;
      }
      if (msg.type === "historyUpdated") renderHistory(msg.messages || []);
      if (msg.type === "response") { setBusy(false); append("assistant", msg.text, "NovaCode"); }
      if (msg.type === "streamStart") {
        // Reset streaming state; the bubble is created lazily on first text chunk
        streamingRaw = "";
        streamingItem = null;
        streamingBubble = null;
        els.contextInfo.textContent = "loading...";
      }
      if (msg.type === "streamChunk") {
        // Lazily create the assistant bubble on first text chunk
        if (!streamingBubble) {
          els.empty.style.display = "none";
          streamingItem = document.createElement("section");
          streamingItem.className = "message assistant typing";
          const meta = document.createElement("div");
          meta.className = "meta";
          meta.textContent = "NovaCode";
          streamingBubble = document.createElement("div");
          streamingBubble.className = "bubble";
          streamingItem.append(meta, streamingBubble);
          els.messages.appendChild(streamingItem);
        }
        streamingRaw += msg.chunk;
        streamingBubble.innerHTML = renderMarkdown(streamingRaw);
        scrollToBottom();
      }
      if (msg.type === "agentEvent") {
        if (msg.event === "plan" && msg.steps) {
          renderAgentTodo(msg.steps);
        } else if (msg.event === "tool") {
          appendToolLog(msg.name, msg.args);
        }
      }
      if (msg.type === "streamEnd") {
        if (streamingItem) { streamingItem.classList.remove("typing"); }
      }
      if (msg.type === "streamFinalize") {
        setBusy(false);
        els.contextInfo.textContent = "idle";
        // Remove the tool log if present
        const toolLog = document.querySelector(".agent-tool-log");
        if (toolLog) { toolLog.remove(); }
        // Re-render the final text with proper markdown and bind code actions
        if (streamingBubble && streamingItem) {
          streamingBubble.innerHTML = renderMarkdown(msg.text);
          streamingItem.classList.remove("typing");
          bindCodeActions(streamingItem);
        }
        streamingItem = null;
        streamingBubble = null;
        streamingRaw = "";
      }
      if (msg.type === "error") {
        setBusy(false);
        if (streamingItem) {
          streamingItem.remove();
          streamingItem = null;
          streamingBubble = null;
          streamingRaw = "";
        }
        append("error", msg.text, "Error");
      }
      if (msg.type === "clear") { clearAgentTodo(); renderHistory([]); }
      if (msg.type === "retryStart") { clearAgentTodo(); setBusy(true); }
      if (msg.type === "explorerData") renderExplorer(msg.entries || []);
      if (msg.type === "refreshExplorer") requestExplorer();

      // Terminal result
      if (msg.type === "terminalResult") {
        const prefix = msg.exitCode === 0 ? "" : "[exit " + msg.exitCode + "] ";
        els.terminalOutput.textContent += prefix + (msg.output || "") + "\n\n";
        els.terminalOutput.scrollTop = els.terminalOutput.scrollHeight;
      }

      // Token usage dashboard update
      if (msg.type === "tokenUsage") {
        const usage = msg.usage || {};
        totalTokensUsed += (usage.total || 0);
        els.tokenCount.textContent = totalTokensUsed.toLocaleString();
        const contextSize = parseInt(els.modelName.dataset.contextSize || "4096");
        const pct = Math.min(100, Math.round((usage.total || 0) / contextSize * 100));
        els.tokenBar.style.width = pct + "%";
        els.tokenBar.style.background = pct > 80 ? "var(--error)" : "var(--accent)";
        els.contextInfo.textContent = (usage.context || 0) + " ctx";
        els.filesLoaded.textContent = (usage.files_loaded || []).length;
      }

      // Summarize result
      if (msg.type === "summarizeResult") {
        els.summarizeChat.disabled = false;
        els.summarizeChat.textContent = "📝 Summarize";
        append("assistant", "**📝 Summary** (" + (msg.tokens || 0) + " tokens):\\n\\n" + msg.summary, "Summary");
      }

      // Enhanced prompt result
      if (msg.type === "enhancedPrompt") {
        els.prompt.value += msg.chunk;
        els.prompt.style.height = "auto";
        els.prompt.style.height = Math.min(els.prompt.scrollHeight, 150) + "px";
      }
      if (msg.type === "enhancedPromptDone") {
        els.refinePrompt.disabled = false;
        els.refinePrompt.textContent = "✨ Refine";
      }
    });

    vscode.postMessage({ type: "getSettings" });
    vscode.postMessage({ type: "getHistory" });
  </script>
</body>
</html>`;
}

function novaMark(): string {
  return `<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4.5 18.5V6.2c0-1 .8-1.7 1.8-1.7h3.2l10 15h-3.7L8 7.8v10.7H4.5Z" stroke="#28d8ff" stroke-width="2.35" stroke-linecap="round" stroke-linejoin="round"/><path d="M19.5 5.5v12.3c0 1-.8 1.7-1.8 1.7h-3.2l-10-15h3.7L16 16.2V5.5h3.5Z" stroke="#22f0d2" stroke-width="2.35" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function iconGear(): string {
  return `<svg viewBox="0 0 24 24" fill="none"><path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" stroke-width="2"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.14.37.43.66.79.79.24.09.5.14.76.14H21a2 2 0 1 1 0 4h-.09A1.7 1.7 0 0 0 19.4 15Z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function iconSliders(): string {
  return `<svg viewBox="0 0 24 24" fill="none"><path d="M4 7h10M18 7h2M4 17h2M10 17h10" stroke-width="2" stroke-linecap="round"/><path d="M14 7a2 2 0 1 0 4 0 2 2 0 0 0-4 0ZM6 17a2 2 0 1 0 4 0 2 2 0 0 0-4 0Z" stroke-width="2"/></svg>`;
}

function iconRefresh(): string {
  return `<svg viewBox="0 0 24 24" fill="none"><path d="M20 12a8 8 0 0 1-13.66 5.66L4 15.32M4 12A8 8 0 0 1 17.66 6.34L20 8.68" stroke-width="2" stroke-linecap="round"/><path d="M4 20v-4.68h4.68M20 4v4.68h-4.68" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function iconSend(): string {
  return `<svg viewBox="0 0 24 24" fill="none"><path d="M4 12 20 4l-6.5 16-2.5-7-7-2.5Z" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function iconUp(): string {
  return `<svg viewBox="0 0 24 24" fill="none"><path d="M12 19V5M5 12l7-7 7 7" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function iconSave(): string {
  return `<svg viewBox="0 0 24 24" fill="none"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" stroke-width="2"/><path d="M17 21v-8H7v8M7 3v5h8" stroke-width="2"/></svg>`;
}

function iconTrash(): string {
  return `<svg viewBox="0 0 24 24" fill="none"><path d="M3 6h18M8 6V4h8v2M6 6l1 16h10l1-16" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function iconWand(): string {
  return `<svg viewBox="0 0 24 24" fill="none"><path d="M15 4V2m0 2v2m0-2h2m-2 0h-2m-3.5 3.5L3 18l3 3 8.5-8.5m-3-3l1.5-1.5 3 3-1.5 1.5m-3-3l3 3" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M9.5 2l.5 1 .5-1L11 1.5l-1-.5.5-1L10 .5 9.5 2ZM20.5 8l.5 1 .5-1 1-.5-1-.5-.5-1-.5 1-1 .5 1 .5Z" stroke-width="1.5"/></svg>`;
}

function iconFolderText(): string { return "DIR"; }
function iconFileText(): string { return "FILE"; }
function iconSymbolText(): string { return "FN"; }

function getNonce(): string {
  let text = "";
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}