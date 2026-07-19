# AI Agent Hub - Setup Guide

## System Requirements

| Component | Minimum Version |
|-----------|----------------|
| Python    | 3.10+          |
| Node.js   | 18+            |
| npm       | 9+             |

## Quick Start

```bash
# Windows - run setup.bat (double-click or CMD)
setup.bat

# Manual install (all platforms)
pip install -r requirements-all.txt
cd builder/frontend && npm install
```

## Python Dependencies

### Core (Required)

| Package       | Version  | Purpose              |
|---------------|----------|----------------------|
| fastapi       | >=0.115  | Web framework        |
| uvicorn       | >=0.30   | ASGI server          |
| pyyaml        | >=6.0    | YAML parser          |
| pydantic      | >=2.0    | Data validation      |

### LLM Providers (Install at least one)

| Package               | Version  | Provider               |
|-----------------------|----------|------------------------|
| openai                | >=1.30   | OpenAI / DeepSeek      |
| anthropic             | >=0.30   | Anthropic Claude       |
| google-generativeai   | >=0.6    | Google Gemini          |
| httpx                 | >=0.27   | Ollama (local)         |

### RAG Engine

| Package                  | Version  | Purpose                  |
|--------------------------|----------|--------------------------|
| chromadb                 | >=0.5    | Vector database          |
| sentence-transformers    | >=3.0    | Embedding model        |
| tiktoken                 | >=0.7    | Token counting (optional) |
| jieba                    | >=0.42   | Chinese tokenization (optional) |

### File Processing

| Package              | Version  | Purpose              |
|----------------------|----------|----------------------|
| PyPDF2               | >=3.0    | PDF parsing          |
| python-multipart     | >=0.0.9  | File upload          |
| aiofiles             | >=24.0   | Async file I/O       |

### CLI

| Package  | Version  | Purpose                |
|----------|----------|------------------------|
| rich     | >=13.0   | Terminal UI (optional) |

## Frontend Dependencies (Auto-installed via npm)

| Package            | Purpose         |
|--------------------|-----------------|
| react / react-dom  | UI framework    |
| lucide-react       | Icons           |
| tailwindcss        | CSS framework   |
| vite               | Build tool      |
| typescript         | Type checker    |

## Environment Variables

Configure at least one provider key:

```bash
set DEEPSEEK_API_KEY=sk-xxxx     # Windows CMD
set OPENAI_API_KEY=sk-xxxx
set ANTHROPIC_API_KEY=sk-ant-xxxx
set GOOGLE_API_KEY=xxxx
```

Or configure via frontend Settings panel (gear icon) after startup.

## Databases (No external setup needed)

| Component | Type       | Note                    |
|-----------|------------|------------------------|
| SQLite    | Stdlib     | Conversation storage   |
| ChromaDB  | Pip package| In-process vector DB   |

## Optional: Ollama (Local Models)

Install Ollama separately for local LLM inference:
https://ollama.com/download
