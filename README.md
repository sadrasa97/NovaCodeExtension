# NovaCode AI Chat

<p align="center">
  <strong>Your AI-Powered Coding Agent — Right Inside VS Code</strong>
</p>

---

**NovaCode AI Chat** is a VS Code extension that brings a full AI coding assistant directly into your editor. It works with local GGUF models (completely offline), OpenRouter, or NVIDIA cloud APIs — giving you the power of an AI agent without any subscription.

## ✨ Features

### 🤖 Agent Mode 
- **Autonomous code editing** — the agent searches your workspace, reads files, makes precise edits, and validates changes automatically
- **Multi-step reasoning** — uses a ReAct-style tool loop to understand context before making changes
- **Auto-validation** — runs `py_compile` and `pytest` after edits to catch errors before presenting results
- **Modified files summary** — shows exactly which files were changed at the end of every agent session
- **Terminal command execution** — can run build, test, lint, and debug commands directly from the agent loop and return output

### 🔍 Workspace Code Search
- **Regex-powered search** across your entire workspace
- **Symbol and pattern discovery** — find classes, functions, imports, and usage patterns
- **Contextual results** — shows surrounding code so you understand matches without opening files
- **Glob-based file search** — find files by name or extension patterns

### 💬 Chat Mode
- Ask questions about your code, get explanations, and receive suggestions
- Supports selected code context — highlight code and ask about it
- Markdown-rendered responses with syntax-highlighted code blocks

### 🔧 Specialized Modes
| Mode | Purpose |
|------|---------|
| **Chat** | General coding Q&A with context awareness |
| **Agent** | Autonomous workspace editing with search → read → edit → validate loop |
| **Search** | Deep code search across workspace files and modules |
| **Explain** | Detailed explanations of selected code or files |
| **Fix** | Bug diagnosis and fix suggestions |
| **Tests** | Generate tests for selected code or active file |

### 🛠️ Agent Tools
When in Agent or Search mode, the AI has access to:
- `search_code` — regex/text search across all workspace files
- `read_file` — read any file in the workspace
- `edit_file` — make precise, targeted edits (find & replace)
- `write_file` — create new files or overwrite existing ones
- `delete_file` — remove files
- `glob` — find files by pattern
- `list_files` — browse directory contents
- `run_command` — execute shell commands (build, test, lint)

### 🧪 Terminal & Verification Workflows
- Execute project commands from agent mode: test runs, linting, type checks, build steps
- Uses workspace-scoped current directory control (`cd` + `run_command`) for multi-step fixes
- Supports long-running command timeouts for bigger tasks (for example full test suites)

### 🏠 Fully Local / Fully Private
- Run any GGUF model on your own hardware — no data leaves your machine
- Supports GPU acceleration (configurable layers)
- Adjustable context size (2K to 128K tokens)

### ☁️ Cloud Options
- **OpenRouter** — access hundreds of models (Llama, Mistral, Claude, GPT, etc.)
- **NVIDIA** — use NVIDIA's hosted inference endpoints
- **OpenAI** — direct access to OpenAI's powerful models (GPT-4o, etc.)

## 📸 How It Works

1. Open the **NovaCode AI** panel in the sidebar
2. Select your mode (Chat, Agent, Search, etc.)
3. Type your request and press **Ctrl+Enter** or click **Send**
4. In Agent mode, watch as the AI searches your code, makes edits, validates, and reports back with a list of modified files

## ⚙️ Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| `novacode.backend` | LLM backend (`gguf`, `openrouter`, `nvidia`) | `gguf` |
| `novacode.modelPath` | Path to your `.gguf` model file | — |
| `novacode.modelsDirectory` | Folder containing GGUF models | — |
| `novacode.contextSize` | Context window size in tokens | `4096` |
| `novacode.gpuLayers` | GPU layers for acceleration (`-1` = all) | `-1` |
| `novacode.temperature` | Response creativity (0.0–2.0) | `0.7` |
| `novacode.maxTokens` | Maximum response length | `2048` |
| `novacode.threads` | CPU threads (null = auto) | `null` |
| `novacode.openrouterApiKey` | Your OpenRouter API key | — |
| `novacode.openrouterModel` | OpenRouter model identifier | — |
| `novacode.nvidiaApiKey` | Your NVIDIA API key | — |
| `novacode.nvidiaModel` | NVIDIA model identifier | — |
| `novacode.projectRoot` | NovaCode project root directory | — |
| `novacode.defaultChatMode` | Default mode when opening chat | `Chat` |

## 🎯 Requirements

- **VS Code** 1.85+
- **Python 3.10+** (for the AI bridge)
- For local models: a `.gguf` model file and sufficient RAM/VRAM
- For cloud: an API key for OpenRouter or NVIDIA

## 📋 Commands

| Command | Description |
|---------|-------------|
| `NovaCode: New Chat` | Clear conversation and start fresh |
| `NovaCode: Select Model` | Pick a model from your models directory |
| `NovaCode: Model Settings` | Open NovaCode settings |
| `NovaCode: Set Working Directory` | Set the project root |
| `NovaCode: Set Models Directory` | Choose where your GGUF models are stored |

## 🔒 Privacy & Security

- Local GGUF mode: **zero network requests** — everything runs on your machine
- API keys are stored in VS Code settings (use Secrets storage for production)
- The agent cannot operate outside your workspace root
- Shell commands are sandboxed with timeouts

## 📄 License

MIT
