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
    .tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); background: var(--panel); flex-shrink: 0; }
    .tab { padding: 6px 14px; font-size: 12px; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; transition: color .15s, border-color .15s; }
    .tab:hover { color: var(--fg); }
    .tab.active { color: var(--fg); border-bottom-color: var(--accent); }

    /* === Messages === */
    .messages { display: flex; flex-direction: column; gap: 16px; padding-bottom: 120px; }
    .empty { color: var(--muted); text-align: center; padding: 32px 16px; line-height: 1.6; }
    .message { display: flex; flex-direction: column; gap: 2px; }
    .message.user { align-items: flex-end; }
    .meta { font-size: 10px; color: var(--muted); padding: 0 2px; }
    .bubble { max-width: 100%; padding: 10px 12px; border-radius: 12px; background: var(--panel); border: 1px solid var(--border); line-height: 1.6; overflow-wrap: anywhere; word-break: break-word; }
    .user .bubble { background: var(--accent); color: var(--button-fg); border-color: transparent; border-radius: 12px 12px 4px 12px; }
    .assistant .bubble { border-radius: 12px 12px 12px 4px; }
    .error .bubble { background: color-mix(in srgb, var(--error) 10%, var(--panel)); border-color: color-mix(in srgb, var(--error) 30%, transparent); color: var(--error); }
    .typing .bubble { opacity: 0.7; }
    .typing .bubble::after { content: ""; display: inline-block; width: 4px; height: 14px; background: var(--fg); margin-left: 4px; animation: blink 1s steps(2) infinite; vertical-align: middle; }
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

    /* === Composer === */
    .composer { padding: 8px 12px; border-top: 1px solid var(--border); background: var(--panel); flex-shrink: 0; }
    .composer-box { display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 10px; background: var(--input); transition: border-color .15s; }
    .composer-box:focus-within { border-color: var(--accent); }
    textarea { width: 100%; min-height: 60px; max-height: 150px; resize: none; border: 0; outline: 0; color: var(--input-fg); background: transparent; line-height: 1.5; }
    .controls { display: flex; align-items: center; gap: 6px; }
    .controls select { height: 26px; width: auto; min-width: 70px; padding: 0 6px; font-size: 11px; border-radius: 5px; border: 1px solid var(--border); color: var(--input-fg); background: var(--input); }
    .controls .spacer { flex: 1; }
    .send { min-width: 50px; height: 28px; padding: 0 12px; font-weight: 600; font-size: 12px; border-radius: 6px; border: none; color: var(--button-fg); background: var(--accent); cursor: pointer; }
     .send:hover { opacity: 0.9; }
     .send:disabled { opacity: 0.5; cursor: not-allowed; }

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
    .icon-btn { width: 26px; height: 26px; padding: 0; display: inline-flex; align-items: center; justify-content: center; border-radius: 5px; border: 1px solid transparent; color: var(--muted); background: transparent; }
    .icon-btn:hover { color: var(--fg); background: var(--secondary); }
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
    </main>

    <footer class="composer">
      <div class="composer-box">
        <textarea id="prompt" placeholder="Ask NovaCode anything..." rows="2"></textarea>
        <div class="controls">
          <select id="mode" title="Mode">
            <option>Agent</option><option>Chat</option><option>Plan</option><option>WebSearch</option>
          </select>
          <span class="spacer"></span>
          <button class="icon-btn" id="clearHistory" title="Clear">${iconTrash()}</button>
          <button class="send" id="send">Send</button>
        </div>
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
       scrollBottom: document.getElementById("scrollBottom")
     };
    let pending;

    document.querySelectorAll(".tab").forEach(tab => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        els.tabs.forEach(t => t.classList.toggle("active", t === tab));
        els.panes.forEach(p => p.classList.toggle("active", p.dataset.pane === target));
        if (target === "explorer") requestExplorer();
        vscode.postMessage({ type: "switchTab", tab: target });
      });
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
        .replace(/\x60\x60\x60([\\w-]*)\n([\s\S]*?)\x60\x60\x60/g, (_m, _lang, code) => {
          const decoded = code.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
          return '<pre data-code="' + encodeURIComponent(decoded) + '"><code>' + code + '</code></pre><div class="code-actions"><button data-action="copy">Copy</button><button data-action="insert">Insert</button></div>';
        })
        .replace(/\*{2}([^*]+)\*{2}/g, "<strong>$1</strong>")
        .replace(/\x60([^\x60]+)\x60/g, "<code>$1</code>")
        .replace(/\\n/g, "<br>");
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

    window.addEventListener("message", (event) => {
      const msg = event.data;
      if (msg.type === "settings") {
        els.modelName.textContent = msg.modelName || "No model";
        if (msg.defaultMode) els.mode.value = msg.defaultMode;
      }
      if (msg.type === "historyUpdated") renderHistory(msg.messages || []);
      if (msg.type === "response") { setBusy(false); append("assistant", msg.text, "NovaCode"); }
      if (msg.type === "error") { setBusy(false); append("error", msg.text, "Error"); }
      if (msg.type === "clear") renderHistory([]);
      if (msg.type === "retryStart") setBusy(true);
      if (msg.type === "explorerData") renderExplorer(msg.entries || []);
      if (msg.type === "refreshExplorer") requestExplorer();
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