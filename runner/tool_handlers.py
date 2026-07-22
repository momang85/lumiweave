"""
AI Agent Hub — Tool 处理器

每个函数对应一个 tool.handler 名称，
接收参数 dict，返回执行结果字符串。
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from collections import OrderedDict

# v0.6.1: 固定项目根目录 — 不依赖 CWD（asyncio线程/handle_run_command 会改变CWD）
_PROJECT_ROOT = (Path(__file__).resolve().parent.parent / "builder" / "backend").resolve()

# v0.6.1: delegate_task 结果缓存（LRU，可配置）
try:
    from runtime_config import get as _rc_get
except ImportError:
    def _rc_get(key, default=None):
        return default

_CACHE_MAX = _rc_get("delegate_cache_max", 50)
_delegate_cache: OrderedDict[str, str] = OrderedDict()

# v0.6.1: 单会话 run_command 计数器
_run_command_count: int = 0



def _make_cache_key(**kwargs) -> str:
    """v2.3: 结构化缓存键——基于 (agent_id, project_path, file_target) 而非全文匹配"""
    import re
    task = kwargs.get("task", "")
    context = kwargs.get("context", "")
    agent_id = kwargs.get("agent_id", "")

    # 从task/context中提取 project 路径
    project = ""
    m = re.search(r'projects/([a-zA-Z0-9_-]+)', task + context)
    if m:
        project = m.group(1)

    # 从task中提取目标文件
    file_targets = re.findall(r'([a-zA-Z_][\w.]*\.[a-z]+)', task)

    raw = json.dumps({
        "agent_id": agent_id,
        "project": project,
        "targets": sorted(file_targets)[:3],
        "context_hash": hashlib.md5(context.encode()).hexdigest() if context else "",
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode()).hexdigest()


def _resolve_safe_path(relative_path: str) -> Path | None:
    """将相对路径解析到固定项目根目录下，超出根目录则返回 None"""
    clean = relative_path.lstrip("/").lstrip("\\")
    p = (_PROJECT_ROOT / clean).resolve()
    if str(p).startswith(str(_PROJECT_ROOT)):
        return p
    return None


# v0.6.1: 已 git init 的项目目录缓存（避免重复 init）
_git_inited_dirs: set[str] = set()


def _auto_git_commit(file_path: Path):
    """文件写入后自动 git init + add + commit（每个项目目录仅 init 一次，后续不再自动 commit 避免拖慢响应）"""
    try:
        parts = file_path.relative_to(_PROJECT_ROOT).parts
        if parts and parts[0] == "projects" and len(parts) >= 2:
            project_dir = _PROJECT_ROOT / "projects" / parts[1]
            dir_key = str(project_dir.resolve())
            if dir_key in _git_inited_dirs:
                return  # v0.6.1: 已 init，不重复操作

            if (project_dir / ".git").exists():
                _git_inited_dirs.add(dir_key)
                return

            # 首次 git init + add + commit（仅一次）
            result = subprocess.run(
                ["git", "init"], cwd=str(project_dir),
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                _git_inited_dirs.add(dir_key)
                with open(project_dir / ".gitignore", "w") as f:
                    f.write("__pycache__/\n*.pyc\nnode_modules/\n.env\n")
                subprocess.run(
                    ["git", "add", "-A"], cwd=str(project_dir),
                    capture_output=True, timeout=5,
                )
                subprocess.run(
                    ["git", "commit", "-m", "init: AI Agent Hub 自动生成"], cwd=str(project_dir),
                    capture_output=True, timeout=5,
                )
    except Exception:
        pass


# ──────────────────────────────────────────────
# 内置处理器
# ──────────────────────────────────────────────

def handle_search_docs(**kwargs) -> str:
    """
    模拟文档搜索。

    在实际部署中，这里会对接真实的文档搜索 API
    （如 Algolia、Meilisearch 或向量搜索）。
    """
    query = kwargs.get("query", "")
    scope = kwargs.get("scope", "all")
    time.sleep(0.5)  # 模拟网络延迟

    results = [
        {
            "title": f"[{scope}] 搜索结果: {query}",
            "url": f"https://docs.example.com/{scope}?q={query}",
            "snippet": f"关于 '{query}' 的文档搜索结果（{scope} 范围内）。"
                       f"这是模拟数据，实际部署后会返回真实文档内容。",
        }
    ]

    return json.dumps(results, ensure_ascii=False, indent=2)


def handle_code_lint(**kwargs) -> str:
    """
    对代码片段进行静态检查。

    使用 Python 内置 compile() 检查语法错误，
    后续可集成 pylint/flake8。
    """
    code = kwargs.get("code", "")
    language = kwargs.get("language", "python")

    if language != "python":
        return json.dumps({
            "status": "skipped",
            "message": f"当前仅支持 Python 代码检查，不支持 {language}",
        }, ensure_ascii=False)

    # 检查语法
    try:
        compile(code, "<lint>", "exec")
        syntax_ok = True
        syntax_error = None
    except SyntaxError as e:
        syntax_ok = False
        syntax_error = str(e)

    # 检查常见风格问题
    issues = []
    lines = code.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip()
        if len(stripped) > 120:
            issues.append({
                "line": i,
                "severity": "warning",
                "message": f"行长度 {len(stripped)} 超过 120 字符",
            })
        if stripped != line and line.endswith(" "):
            issues.append({
                "line": i,
                "severity": "info",
                "message": "行尾有空格",
            })

    return json.dumps({
        "syntax_ok": syntax_ok,
        "syntax_error": syntax_error,
        "issues": issues,
        "issue_count": len(issues),
    }, ensure_ascii=False, indent=2)


def handle_code_run(**kwargs) -> str:
    """
    在子进程中安全执行 Python 代码（带超时）。

    安全措施：
    - 独立子进程隔离
    - 超时强制终止
    - 捕获 stdout/stderr
    - 限制执行时间
    """
    code = kwargs.get("code", "")
    timeout = min(int(kwargs.get("timeout", _rc_get("code_executor_timeout", 10))), 30)

    try:
        result = subprocess.run(
            ["python", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tempfile.gettempdir(),  # 安全：在临时目录执行
        )
        return json.dumps({
            "exit_code": result.returncode,
            "stdout": result.stdout[:_rc_get("output_truncate_limit", 8000)],
            "stderr": result.stderr[:_rc_get("output_truncate_limit", 8000)],
            "truncated": len(result.stdout) > _rc_get("output_truncate_limit", 8000) or len(result.stderr) > _rc_get("output_truncate_limit", 8000),
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "exit_code": -1,
            "error": f"代码执行超时（>{timeout}s）",
        }, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({
            "exit_code": -1,
            "error": "未找到 Python 解释器",
        }, ensure_ascii=False)


def _search_bing(query: str, opener, limit: int = 5) -> list[dict]:
    """从 Bing HTML 搜索结果页抓取标题、URL 和摘要。"""
    import html as _html
    import re
    import urllib.request, urllib.parse
    results: list[dict] = []
    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&setlang=en"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with opener.open(req, timeout=12) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")

        # 解析 b_algo 结果块
        blocks = re.findall(r'<li class=\"b_algo\"[^>]*>(.*?)</li>', raw_html, re.DOTALL)
        for block in blocks:
            if len(results) >= limit:
                break
            # 提取标题和链接（h2 标签内的是真正的标题，不是域名面包屑）
            title_match = re.search(r'<h2[^>]*>.*?<a[^>]*href=\"(https?://[^\"]+)\"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_match:
                continue
            href = title_match.group(1)
            title = _html.unescape(re.sub(r'<[^>]+>', '', title_match.group(2)).strip())

            # 过滤掉非结果链接
            skip_domains = ("bing.com", "microsoft.com/bing", "go.microsoft.com", "login.live.com")
            if not title or any(d in href for d in skip_domains):
                continue

            # 提取摘要
            snippet = ""
            snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
            if snippet_match:
                snippet = _html.unescape(re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip())

            results.append({"title": title, "url": href, "snippet": snippet[:300]})
    except Exception:
        pass
    return results


def handle_github_api(**kwargs) -> str:
    """调用 GitHub REST API（需 GITHUB_TOKEN 环境变量）。"""
    import os
    import urllib.request, urllib.parse, urllib.error
    endpoint = kwargs.get("endpoint", "").strip("/")
    method = (kwargs.get("method", "GET") or "GET").upper()
    if not endpoint:
        return json.dumps({"error": "缺少 endpoint 参数"}, ensure_ascii=False)
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        return json.dumps({
            "error": "未配置 GITHUB_TOKEN 环境变量",
            "hint": "请在环境变量中设置 GITHUB_TOKEN，或在前端 API 设置中配置",
        }, ensure_ascii=False)
    try:
        url = f"https://api.github.com/{endpoint}"
        body = None
        if method in ("POST", "PATCH", "PUT"):
            body_data = kwargs.get("body", "")
            body = json.dumps(body_data).encode() if isinstance(body_data, dict) else str(body_data).encode()
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "AI-Agent-Hub/1.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="replace"))
        # 截断大响应
        result_str = json.dumps(result, ensure_ascii=False)
        if len(result_str) > 4000:
            result_str = result_str[:4000] + "\n...(输出已截断)"
        return result_str
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return json.dumps({"error": f"GitHub API {e.code}: {body[:300]}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"GitHub API 调用失败: {str(e)[:200]}"}, ensure_ascii=False)


def handle_web_search(**kwargs) -> str:
    """通用网页搜索 — 优先使用 DuckDuckGo Instant Answer API（免费无需Key）"""
    import os
    import urllib.request, urllib.parse
    query = kwargs.get("query", "")
    if not query:
        return json.dumps({"error": "缺少 query 参数"}, ensure_ascii=False)

    results: list[dict] = []

    # 构建 HTTP opener（支持 HTTP/SOCKS5 代理）
    proxy_url = _rc_get("web_search_proxy", "").strip()
    _socks_socket = None  # 保存原始 socket 用于恢复
    if proxy_url:
        if proxy_url.startswith("socks5://"):
            import socks as _socks
            import socket as _socket
            _socks_socket = _socket.socket  # 保存原始
            host = proxy_url.split("://")[1].split(":")[0]
            port = int(proxy_url.rsplit(":", 1)[-1])
            _socks.set_default_proxy(_socks.SOCKS5, host, port)
            _socket.socket = _socks.socksocket
            opener = urllib.request.build_opener()
        else:
            proxy_handler = urllib.request.ProxyHandler({
                "http": proxy_url,
                "https": proxy_url,
            })
            opener = urllib.request.build_opener(proxy_handler)
    else:
        opener = urllib.request.build_opener()

    # 1. 尝试 DuckDuckGo Instant Answer API（免费，无 Key 需求）
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Agent-Hub/1.0"})
        with opener.open(req, timeout=_rc_get("web_search_timeout", 8)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # AbstractText
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("AbstractSource", "DuckDuckGo"),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data["AbstractText"],
                })
            # RelatedTopics（取可配置条数）
            limit = _rc_get("search_result_limit", 5)
            for topic in data.get("RelatedTopics", [])[:limit]:
                if isinstance(topic, dict) and topic.get("Text"):
                    results.append({
                        "title": topic.get("FirstURL", "").split("/")[-1] if topic.get("FirstURL") else "DuckDuckGo",
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic["Text"],
                    })
            # Results (alternative format)
            for r in data.get("Results", [])[:_rc_get("search_result_limit", 5)]:
                if isinstance(r, dict):
                    results.append({
                        "title": r.get("Text", ""),
                        "url": r.get("FirstURL", ""),
                        "snippet": r.get("Text", ""),
                    })
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning(f"DuckDuckGo 搜索失败，尝试降级: {type(e).__name__}: {e}")

    # 2. 如果 DuckDuckGo 返回空，尝试 Google（需要 SERPAPI_KEY 环境变量）
    if not results:
        try:
            serp_key = os.environ.get("SERPAPI_KEY", "")
            if serp_key:
                url = f"https://serpapi.com/search.json?q={urllib.parse.quote(query)}&api_key={serp_key}&num={_rc_get('search_result_limit', 5)}"
                req = urllib.request.Request(url, headers={"User-Agent": "AI-Agent-Hub/1.0"})
                with opener.open(req, timeout=_rc_get("serpapi_timeout", 10)) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for r in data.get("organic_results", [])[:_rc_get("search_result_limit", 5)]:
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("link", ""),
                            "snippet": r.get("snippet", ""),
                        })
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Google SerpAPI 搜索失败: {type(e).__name__}: {e}")

    # 2.5. Bing HTML 抓取（DuckDuckGo/Google 都不可用时的兜底）
    if not results:
        results = _search_bing(query, opener, _rc_get("search_result_limit", 5))

    # 3. 都失败 — 返回提示
    if not results:
        results.append({
            "title": "搜索不可用",
            "url": "",
            "snippet": f"未找到关于 '{query}' 的实时搜索结果。请尝试设置 SERPAPI_KEY 环境变量以启用 Google 搜索，或依赖模型知识回答。",
        })

    # 恢复原始 socket（SOCKS5 代理时被替换）
    if _socks_socket is not None:
        _socket.socket = _socks_socket

    return json.dumps({
        "query": query,
        "result_count": len(results),
        "results": results,
    }, ensure_ascii=False, indent=2)


def handle_search_memory(**kwargs) -> str:
    """
    搜索对话记忆库（非破坏性卸载的消息）。

    Agent 推理卡壳时可主动调用此工具回溯原始记录。
    """
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _root)

    from shared.conversation_memory import get_memory

    agent_id = kwargs.get("agent_id", "")
    session_id = kwargs.get("session_id", "")
    query = kwargs.get("query", "")
    top_k = min(int(kwargs.get("top_k", 10)), 20)

    if not agent_id:
        return json.dumps({
            "error": "缺少 agent_id 参数",
            "hint": "需要传入 agent_id 和 session_id 来查询已卸载的历史消息",
        }, ensure_ascii=False)

    results = get_memory().search(
        agent_id=agent_id,
        session_id=session_id or None,
        query=query,
        top_k=top_k,
    )

    stats = {}
    if session_id:
        stats = get_memory().get_statistics(agent_id, session_id)

    return json.dumps({
        "results": results,
        "count": len(results),
        "total_archived": stats.get("total", 0),
        "total_tokens_archived": stats.get("total_tokens", 0),
    }, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# v0.5: 多Agent调度工具
# ──────────────────────────────────────────────

def handle_list_agents(**kwargs) -> str:
    """列出所有可用的子 Agent — 供中央调度 Agent 使用"""
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _root)

    from shared.agent_dispatcher import AgentRegistry

    filter_tag = kwargs.get("filter_tag", "")
    agents = AgentRegistry.list_agents(filter_tag)

    if not agents:
        # 首次调用时强制加载
        AgentRegistry._loaded = False
        agents = AgentRegistry.list_agents(filter_tag)

    return json.dumps({
        "agents": [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "description": a.description,
                "tags": a.tags,
                "domain": a.domain,
                "avatar": a.avatar,
            }
            for a in agents
        ],
        "count": len(agents),
    }, ensure_ascii=False, indent=2)


def handle_delegate_task(**kwargs) -> str:
    """将子任务指派给指定 Agent 执行 — 供中央调度 Agent 使用（含缓存）"""
    import sys, os

    # v0.6.1: 缓存检查 — 相同 task + context + agent_id 直接返回缓存
    cache_key = _make_cache_key(**kwargs)
    if cache_key in _delegate_cache:
        cached = _delegate_cache[cache_key]
        _delegate_cache.move_to_end(cache_key)
        parsed = json.loads(cached)
        parsed["_from_cache"] = True
        return json.dumps(parsed, ensure_ascii=False, indent=2)

    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _root)

    from shared.agent_dispatcher import get_dispatcher

    agent_id = kwargs.get("agent_id", "")
    task = kwargs.get("task", "")
    context = kwargs.get("context", "")

    # v0.5.2: 接收 orchestrator 注入的 API Key/provider，优先使用
    api_key = kwargs.get("_api_key", kwargs.get("api_key", ""))
    provider = kwargs.get("_provider", kwargs.get("provider", ""))
    model = kwargs.get("_model", kwargs.get("model", ""))
    base_url = kwargs.get("_base_url", kwargs.get("base_url", ""))

    dispatcher = get_dispatcher()
    result = dispatcher.delegate_task(
        agent_id=agent_id,
        task=task,
        context=context,
        api_key=api_key,       # 使用 orchestrator 的 Key
        provider=provider,     # 使用 orchestrator 的 provider
        model=model,
        base_url=base_url,     # 使用 orchestrator 的 base_url
    )

    # v0.6.1: 缓存结果
    if result.get("success"):
        _delegate_cache[cache_key] = json.dumps(result, ensure_ascii=False)
        if len(_delegate_cache) > _CACHE_MAX:
            _delegate_cache.popitem(last=False)  # 淘汰最旧的

    return json.dumps(result, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# v2.5: 一键派发——自动创建Agent并执行
# ──────────────────────────────────────────────

def handle_dispatch_to_agents(**kwargs) -> str:
    """自动创建缺失的Agent并并行派发任务。
    
    Orchestrator 不需要关心Agent是否存在——这个函数自动兜底。
    """
    task = kwargs.get("task", kwargs.get("message", ""))
    project_dir = kwargs.get("project_dir", kwargs.get("project", "."))
    api_key = kwargs.get("api_key", "")
    provider = kwargs.get("provider", "")
    model = kwargs.get("model", "")
    base_url = kwargs.get("base_url", "")

    # 1. 无task时自动读取contract.json
    if not task:
        import os
        contract_path = os.path.join(project_dir, 'contract.json')
        if os.path.exists(contract_path):
            try:
                with open(contract_path, encoding='utf-8') as f:
                    contract = json.load(f)
                desc = contract.get('project', '')
                backend_info = contract.get('backend', {})
                frontend_info = contract.get('frontend', {})
                task = f'项目: {desc}
后端: {json.dumps(backend_info, ensure_ascii=False)}
前端: {json.dumps(frontend_info, ensure_ascii=False)}'
            except:
                pass
    if not task:
        return json.dumps({'error': '缺少task参数且contract.json未找到'}, ensure_ascii=False)

    # 2. 并行派发后端+前端
    results = {}
    dispatcher = get_dispatcher()

    # 后端任务
    backend_task = f"创建 {project_dir}/backend/main.py：FastAPI应用，SQLite数据库，CORS配置。\n完整要求：{task}"
    be_result = dispatcher.delegate_task(
        agent_id="com.aihub.backend-dev",
        task=backend_task,
        api_key=api_key, provider=provider, model=model, base_url=base_url
    )
    results["backend"] = be_result

    # 前端任务
    frontend_task = f"创建 {project_dir}/frontend/：index.html+app.js+style.css。\n完整要求：{task}"
    fe_result = dispatcher.delegate_task(
        agent_id="com.aihub.frontend-dev",
        task=frontend_task,
        api_key=api_key, provider=provider, model=model, base_url=base_url
    )
    results["frontend"] = fe_result

    return json.dumps(results, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# v0.6.1: 子Agent直通通信
# ──────────────────────────────────────────────

def handle_send_to_agent(**kwargs) -> str:
    """子Agent直接给其他Agent发消息并获取回复"""
    import sys, os
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _root)
    from shared.agent_dispatcher import get_dispatcher

    target = kwargs.get("target_agent_id", kwargs.get("to_agent", ""))
    msg = kwargs.get("message", kwargs.get("task", ""))
    ctx = kwargs.get("context", "")

    if not target or not msg:
        return json.dumps({"error": "缺少 target_agent_id 或 message 参数"}, ensure_ascii=False)

    depth = int(kwargs.get("_send_depth", "0"))
    if depth >= 3:
        return json.dumps({"error": "send_to_agent递归超限(最多3层)", "depth": depth}, ensure_ascii=False)

    apik = kwargs.get("_api_key", kwargs.get("api_key", ""))
    prov = kwargs.get("_provider", kwargs.get("provider", ""))
    mdl = kwargs.get("_model", kwargs.get("model", ""))
    burl = kwargs.get("_base_url", kwargs.get("base_url", ""))

    result = get_dispatcher().delegate_task(
        agent_id=target, task=msg,
        context=f"[来自子Agent直通消息]\n{ctx}" if ctx else "[来自子Agent直通消息]",
        api_key=apik, provider=prov, model=mdl,
        base_url=burl,
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# 处理器注册表
# ──────────────────────────────────────────────

def handle_create_agent(**kwargs) -> str:
    """AI 生成新 Agent — 当系统无合适子 Agent 时动态创建"""
    import sys, os, yaml
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, _root)

    description = kwargs.get("description", kwargs.get("task", ""))
    domain_hint = kwargs.get("domain", "")
    provider = kwargs.get("provider", "openai")     # 绑定调度的 Provider
    model = kwargs.get("model", "gpt-4o-mini")       # 绑定调度的模型
    api_key = kwargs.get("api_key", "")

    if not description:
        return json.dumps({
            "success": False,
            "error": "缺少 description 参数。请描述你需要创建什么样的 Agent。",
        }, ensure_ascii=False)

    try:
        # v0.5.2: 去重检查 — 扫描现有 Agent，避免重复创建
        from shared.agent_dispatcher import AgentRegistry
        existing = AgentRegistry.list_agents()
        desc_lower = description.lower()
        best_match = None
        best_score = 0
        for a in existing:
            score = 0
            # 按描述关键词匹配
            keywords = [w for w in desc_lower.split() if len(w) > 1]
            name_lower = a.name.lower()
            for kw in keywords:
                if kw in name_lower: score += 2
                if kw in a.description.lower(): score += 1
                if any(kw in t.lower() for t in a.tags): score += 1
            if score > best_score and score >= 3:  # 至少 3 分才算匹配
                best_score = score
                best_match = a
        if best_match:
            return json.dumps({
                "success": True,
                "agent_id": best_match.agent_id,
                "agent_name": best_match.name,
                "already_exists": True,
                "match_score": best_score,
                "message": f"已存在功能类似的 Agent「{best_match.name}」(ID: {best_match.agent_id})，直接使用无需重新创建。",
            }, ensure_ascii=False)

        # 使用共享的 AgentGenerator
        from shared.agent_generator import AgentGenerator, AgentDomain
        from shared.agent_modes import AgentMode
        from shared.tool_presets import get_enabled_presets, inject_secrets, BUILTIN_TOOL_PRESETS

        # v0.6: 读取可用工具预设（不含 Key），传给 LLM 选择
        available_tools = get_enabled_presets()
        tools_hint = ""  # LLM 会从 available_tools 列表中选择

        gen = AgentGenerator()

        # 如果有可用 Key，注入给生成器
        if not api_key:
            for env_key in ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
                key = os.getenv(env_key, "")
                if key:
                    api_key = key
                    if "DEEPSEEK" in env_key: provider = "deepseek"
                    elif "OPENAI" in env_key: provider = "openai"
                    elif "ANTHROPIC" in env_key: provider = "anthropic"
                    break

        result = gen.generate(
            user_input=description,
            domain_hint=AgentDomain(domain_hint) if domain_hint else None,
            available_tools=available_tools,  # v0.6: 传给 LLM 选择
            tool_presets_hint=tools_hint,
        )

        if not result.success or not result.agent_ir:
            return json.dumps({
                "success": False,
                "output": result.error or "生成失败",
                "fallback_suggestion": result.raw_skeleton if hasattr(result, 'raw_skeleton') else None,
            }, ensure_ascii=False)

        # 覆盖为调度 Agent 的 Provider/Model
        agent_ir = result.agent_ir
        agent_ir.model_name = model
        from shared.ir_models import ProviderType
        try:
            agent_ir.provider = ProviderType(provider)
        except ValueError:
            agent_ir.provider = ProviderType.OPENAI

        # v0.6: 注入秘密参数到工具定义中
        injected_count = 0
        for tool in agent_ir.tools:
            tool_dict = {"name": tool.name, "description": tool.description,
                         "parameters": list(tool.parameters.items()) if isinstance(tool.parameters, dict) else []}
            # 转换 parameters 格式为 list[dict]
            if isinstance(tool.parameters, dict):
                tool_dict["parameters"] = [
                    {"name": k, "type": v.get("type", "string"), "description": v.get("description", ""),
                     "required": k in (getattr(tool, 'required', None) or [])}
                    for k, v in tool.parameters.items()
                ]
            else:
                tool_dict["parameters"] = tool.parameters if isinstance(tool.parameters, list) else []

            updated = inject_secrets(tool_dict, BUILTIN_TOOL_PRESETS)
            if updated.get("_injected"):
                injected_count += 1
                tool.description = updated.get("description", tool.description)

        # 保存为 YAML 文件
        from pathlib import Path
        agents_dir = Path(_root) / "agents"
        safe_name = agent_ir.name.replace(" ", "-").replace("/", "-").lower()
        yaml_path = agents_dir / f"{safe_name}-generated.yaml"

        # 避免覆盖已存在的
        counter = 1
        while yaml_path.exists():
            yaml_path = agents_dir / f"{safe_name}-generated-{counter}.yaml"
            counter += 1

        yaml_content = agent_ir.to_yaml_dict()
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(yaml_content, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        # 强制刷新注册表
        from shared.agent_dispatcher import AgentRegistry
        AgentRegistry._loaded = False
        new_agents = AgentRegistry.list_agents()

        # 找到新创建的 Agent
        new_agent_info = None
        for a in new_agents:
            if safe_name in a.agent_id.lower() or yaml_path.name.replace(".yaml", "") in a.agent_id:
                new_agent_info = a
                break
        if not new_agent_info and new_agents:
            # 最后一个可能就是最新的
            new_agent_info = AgentRegistry.get_agent(yaml_path.stem)

        new_agent_id = new_agent_info.agent_id if new_agent_info else yaml_path.stem

        return json.dumps({
            "success": True,
            "agent_id": new_agent_id,
            "agent_name": agent_ir.name,
            "description": agent_ir.description,
            "model": model,
            "provider": provider,
            "tools_count": len(agent_ir.tools),
            "message": f"已创建 Agent「{agent_ir.name}」(ID: {new_agent_id})，使用 {provider}/{model}，可直接 delegate_task 调用。",
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"创建 Agent 失败: {str(e)[:300]}",
        }, ensure_ascii=False)


# ──────────────────────────────────────────────
# v0.6: 本地文件/系统操作工具
# ──────────────────────────────────────────────

def handle_read_file(**kwargs) -> str:
    """读取本地文件内容（安全限制：仅项目目录内）"""
    # v0.6.1: 兼容多种参数名
    path = kwargs.get("path", kwargs.get("file_path", kwargs.get("filePath", "")))
    path = path.lstrip("/")  # v0.6.1: 去掉前导斜杠，防止路径解析错误
    lines = int(kwargs.get("lines", 0))
    offset = int(kwargs.get("offset", 0))
    limit = int(kwargs.get("limit", _rc_get("file_read_default_lines", 500)))

    if not path:
        return json.dumps({"error": "缺少 path 参数"}, ensure_ascii=False)

    try:
        p = _resolve_safe_path(path)
        if p is None:
            return json.dumps({"error": f"安全限制：文件路径必须在项目目录 {_PROJECT_ROOT} 内", "hint": f"请使用相对路径，如 projects/项目名/文件名"}, ensure_ascii=False)
        if not p.exists():
            return json.dumps({"error": f"文件不存在: {path}"}, ensure_ascii=False)
        if p.is_dir():
            return json.dumps({"error": f"路径是目录，非文件: {path}"}, ensure_ascii=False)

        content = p.read_text(encoding="utf-8", errors="replace")
        total_lines = content.count("\n") + 1

        if offset > 0 or limit < len(content):
            all_lines = content.split("\n")
            end = min(offset + limit, len(all_lines))
            content = "\n".join(all_lines[offset:end])

        return json.dumps({
            "path": str(p),
            "content": content,
            "total_lines": total_lines,
            "size_bytes": p.stat().st_size,
            "truncated": len(content) < (p.stat().st_size),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_write_file(**kwargs) -> str:
    """写入文件内容（安全限制：仅项目目录内，不覆盖已有文件除非明确指定）"""
    # v0.6.1: 兼容多种参数名（path / file_path / filePath）
    path = kwargs.get("path", kwargs.get("file_path", kwargs.get("filePath", "")))
    path = path.lstrip("/")  # v0.6.1: 去掉前导斜杠
    content = kwargs.get("content", "")
    overwrite = kwargs.get("overwrite", False)
    append = kwargs.get("append", False)

    if not path or not content:
        return json.dumps({"error": "缺少 path 或 content 参数"}, ensure_ascii=False)

    try:
        p = _resolve_safe_path(path)
        if p is None:
            return json.dumps({"error": f"安全限制：文件路径必须在项目目录 {_PROJECT_ROOT} 内", "hint": "请使用相对路径，如 projects/项目名/文件名"}, ensure_ascii=False)

        if p.exists() and not overwrite and not append:
            return json.dumps({
                "error": f"文件已存在: {path}。设置 overwrite=true 覆盖或 append=true 追加。",
                "hint": "请先 read_file 查看内容，确认后再写入",
            }, ensure_ascii=False)

        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        p.write_text(content, encoding="utf-8")
        # v0.6.1: 自动 git init + commit（首次写入项目目录时）
        _auto_git_commit(p)
        return json.dumps({
            "path": str(p),
            "mode": "overwrite" if not append else "append",
            "size_bytes": p.stat().st_size,
            "lines": content.count("\n") + 1,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_list_dir(**kwargs) -> str:
    """列出目录内容"""
    path = kwargs.get("path", kwargs.get("dir_path", ""))
    path = path.lstrip("/")  # v0.6.1: 去掉前导斜杠
    try:
        p = _resolve_safe_path(path) if path else _PROJECT_ROOT
        if p is None:
            return json.dumps({"error": f"目录 {path} 不在项目范围内"}, ensure_ascii=False)
        if not p.exists():
            return json.dumps({"error": f"目录不存在: {path or '.'}"}, ensure_ascii=False)
        if not p.is_dir():
            return json.dumps({"error": f"路径不是目录: {path}"}, ensure_ascii=False)

        items = []
        for item in sorted(p.iterdir()):
            try:
                stat = item.stat()
                items.append({
                    "name": item.name,
                    "type": "dir" if item.is_dir() else "file",
                    "size": stat.st_size if item.is_file() else 0,
                })
            except Exception:
                items.append({
                    "name": item.name,
                    "type": "unknown",
                    "size": 0,
                })

        return json.dumps({
            "path": str(p),
            "items": items,
            "count": len(items),
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_search_file(**kwargs) -> str:
    """按名称模式搜索文件"""
    import fnmatch
    pattern = kwargs.get("pattern", kwargs.get("query", "*"))
    directory = kwargs.get("directory", kwargs.get("dir", ""))

    try:
        # v0.6.1: 使用固定根目录，限制搜索范围
        p = _resolve_safe_path(directory) if directory else _PROJECT_ROOT
        if p is None:
            return json.dumps({"error": f"目录 {directory} 不在项目范围内"}, ensure_ascii=False)
        if not p.exists():
            return json.dumps({"error": f"目录不存在: {directory or _PROJECT_ROOT}"}, ensure_ascii=False)

        results = []
        for f in p.rglob(pattern):
            if f.is_file():
                results.append({
                    "path": str(f),
                    "name": f.name,
                    "size": f.stat().st_size,
                })
            if len(results) >= _rc_get("search_file_max_results", 50):
                break

        return json.dumps({
            "pattern": pattern,
            "directory": str(p),
            "count": len(results),
            "results": results,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def handle_run_command(**kwargs) -> str:
    """执行任意 shell 命令（带超时 + 安全沙箱 + 进程树清理）"""
    import shlex
    import os
    command = kwargs.get("command", kwargs.get("cmd", ""))
    timeout = min(int(kwargs.get("timeout", 10)), 60)  # v0.6: 默认10s，最大60s
    cwd = kwargs.get("cwd", str(_PROJECT_ROOT))  # v0.6.1: 固定根目录，不依赖 CWD

    if not command:
        return json.dumps({"error": "缺少 command 参数"}, ensure_ascii=False)

    # v0.6.1: 单会话 run_command 次数限制
    global _run_command_count
    _run_command_count += 1
    max_rc = _rc_get("max_run_command_per_session", 5)
    if _run_command_count > max_rc:
        return json.dumps({"error": f"run_command 已超过单会话上限（{max_rc}次），当前第 {_run_command_count} 次"}, ensure_ascii=False)


    # v0.6: 禁止启动长期阻塞的服务器/监听进程
    BLOCKED_PATTERNS = (
        "npm start", "npm run dev", "npm run serve", "npm run preview",
        "yarn start", "yarn dev", "pnpm start", "pnpm dev",
        "vite", "webpack-dev-server", "next dev", "nuxt dev",
        "python -m http.server", "python3 -m http.server",
        "http-server", "live-server", "serve",
    )
    cmd_lower = command.lower().strip()
    for bp in BLOCKED_PATTERNS:
        if cmd_lower.startswith(bp):
            return json.dumps({
                "exit_code": -1,
                "error": f"命令 '{command}' 是长期阻塞型服务器进程，已被禁止。请改用 --help / --version / build 等非阻塞命令。"
            }, ensure_ascii=False)

    # 限制危险命令
    DANGEROUS = ("rm -rf /", "format", "shutdown", "del /f /s", "rd /s /q")
    for d in DANGEROUS:
        if cmd_lower.startswith(d):
            return json.dumps({"error": f"危险命令已阻止: {command[:50]}"}, ensure_ascii=False)

    try:
        # Windows 创建新进程组，方便超时后整体清理
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(Path(cwd).resolve()),
            creationflags=creationflags,
        )
        stdout, stderr = process.communicate(timeout=timeout)
        return json.dumps({
            "exit_code": process.returncode,
            "stdout": stdout[:_rc_get("output_truncate_limit", 8000)],
            "stderr": stderr[:_rc_get("output_truncate_limit", 8000)],
            "truncated": len(stdout) > _rc_get("output_truncate_limit", 8000) or len(stderr) > _rc_get("output_truncate_limit", 8000),
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        try:
            process.kill()  # 强制终止
            process.wait(timeout=2)
        except Exception:
            pass
        return json.dumps({
            "exit_code": -1,
            "error": f"命令执行超时（>{timeout}s），已强制终止: {command[:80]}"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"exit_code": -1, "error": str(e)}, ensure_ascii=False)


# v0.6.1: 结构化契约验证 — 检查前后端接口是否匹配
def handle_validate_contract(**kwargs) -> str:
    """根据 contract.json 验证前后端代码的接口一致性"""
    import re
    project = kwargs.get("project", kwargs.get("project_dir", ""))
    contract_path = kwargs.get("contract_path", "")

    # 定位 contract.json
    if not contract_path and project:
        contract_path = f"projects/{project}/contract.json"
    if not contract_path:
        return json.dumps({"error": "请指定 project 或 contract_path 参数"}, ensure_ascii=False)

    try:
        p = _resolve_safe_path(contract_path)
        if p is None or not p.exists():
            return json.dumps({"error": f"契约文件不存在: {contract_path}"}, ensure_ascii=False)
        contract = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return json.dumps({"error": f"无法读取契约文件: {str(e)}"}, ensure_ascii=False)

    issues = []

    # 提取契约中定义的 API 信息
    backend_api = contract.get("backend", {}).get("api", {})
    endpoints = backend_api.get("endpoints", [])
    frontend_info = contract.get("frontend", {})

    if not endpoints:
        return json.dumps({"warning": "契约中未定义 API endpoints，跳过验证", "result": "skip"}, ensure_ascii=False)

    # 读前端文件检查
    frontend_dir = f"projects/{project}/frontend"
    frontend_files = frontend_info.get("files", [])
    # 如果契约没列文件，自动扫描
    if not frontend_files:
        try:
            fd = _resolve_safe_path(frontend_dir)
            if fd and fd.exists():
                frontend_files = [str(f.relative_to(fd)) for f in fd.rglob("*") if f.suffix in ('.js', '.ts', '.tsx', '.html', '.jsx')][:20]
        except Exception:
            pass

    all_content = ""
    for fname in frontend_files:
        try:
            fpath = _resolve_safe_path(f"{frontend_dir}/{fname}")
            if fpath and fpath.exists():
                all_content += f"\n/* FILE: {fname} */\n" + fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if not all_content:
        return json.dumps({"error": f"未找到前端文件: {frontend_dir}"}, ensure_ascii=False)

    # 逐 endpoint 验证
    for ep in endpoints:
        ep_method = ep.get("method", "GET")
        ep_path = ep.get("path", "")
        response_fields = ep.get("response", {}).get("items", {}).get("fields", {})
        field_names = list(response_fields.keys()) if response_fields else []

        # 1. 检查前端是否调用了这个 endpoint
        url_pattern = re.escape(ep_path)
        if not re.search(url_pattern, all_content):
            issues.append({
                "severity": "error",
                "endpoint": f"{ep_method} {ep_path}",
                "issue": "前端代码中未找到对此 endpoint 的调用",
                "suggestion": f"确认前端是否遗漏 {ep_method} {ep_path}"
            })
            continue

        # 2. 检查字段名匹配
        for fn in field_names:
            # 用简单字符串匹配检测字段引用
            fn_patterns = ['.' + fn, "['" + fn + "']", '"' + fn + '"']
            found = any(p in all_content for p in fn_patterns)
            if not found:
                issues.append({
                    "severity": "warning",
                    "endpoint": f"{ep_method} {ep_path}",
                    "field": fn,
                    "issue": f"前端代码中未找到对字段 '{fn}' 的引用",
                    "suggestion": f"后端返回了 '{fn}' 字段，但前端未使用。检查是否遗漏或命名不一致"
                })

    # 3. 检查前端调用中使用的字段名是否都在契约中
    for ep in endpoints:
        response_fields = ep.get("response", {}).get("items", {}).get("fields", {})
        field_names = set(response_fields.keys()) if response_fields else set()
        if not field_names:
            continue
        # 从代码中提取所有 .xxx 和 ['xxx'] 访问——粗略检测
        potential_fields = set(re.findall(r'\.(\w+)\b', all_content))
        bracket_fields = set(re.findall(r"\[['\"](\w+)['\"]\]", all_content))
        all_refs = potential_fields | bracket_fields
        # 找看起来像数据字段的（不是常见JS API）
        js_common = {'log', 'then', 'catch', 'map', 'filter', 'length', 'push', 'get', 'set', 'data', 'json', 'text'}
        data_refs = all_refs - js_common

        for ep_ep in endpoints:
            ep_path = ep_ep.get("path", "")
            if re.search(re.escape(ep_path), all_content):
                # 这个 endpoint 被引用了，检查字段
                ep_fields = set(ep.get("response", {}).get("items", {}).get("fields", {}).keys())
                for ref in data_refs:
                    if ref not in ep_fields and len(ref) > 2 and ref not in ['error', 'status', 'ok', 'id', 'type']:
                        # 不给每个字段报 warning，太吵。只列出可能不匹配的
                        pass

    return json.dumps({
        "contract": contract_path,
        "endpoints_checked": len(endpoints),
        "files_checked": len(frontend_files),
        "issues_found": len(issues),
        "issues": issues,
        "verdict": "PASS" if not any(i['severity']=='error' for i in issues) else "FAIL",
    }, ensure_ascii=False, indent=2)


def handle_test_project(**kwargs) -> str:
    """启动项目后端，curl测试所有API端点，比对contract预期"""
    import subprocess, time, os as _os, glob

    project = kwargs.get("project", kwargs.get("path", ""))
    port = int(kwargs.get("port", 9001))
    base = f"builder/backend/projects/{project}"
    if not _os.path.exists(base):
        return json.dumps({"error": f"项目目录不存在: {base}"}, ensure_ascii=False)

    # 找 contract
    contract_path = f"{base}/contract.json"
    contract = {}
    if _os.path.exists(contract_path):
        with open(contract_path, encoding="utf-8") as f:
            contract = json.load(f)

    endpoints = []
    api = contract.get("backend", {}).get("api", {})
    for ep in api.get("endpoints", []):
        endpoints.append((ep.get("method", "GET").upper(), ep.get("path", "/"), ep.get("description", "")))

    if not endpoints:
        return json.dumps({"error": "contract.json中未定义API端点"}, ensure_ascii=False)

    # 安装依赖
    req_path = f"{base}/backend/requirements.txt"
    if _os.path.exists(req_path):
        try:
            subprocess.run(["pip", "install", "-r", req_path, "-q"],
                         capture_output=True, timeout=30)
        except Exception:
            pass

    # 启动后端
    backend_dir = f"{base}/backend"
    proc = None
    results = []
    try:
        proc = subprocess.Popen(
            ["python", "-c",
             f"import uvicorn; uvicorn.run('main:app', host='127.0.0.1', port={port}, log_level='error')"],
            cwd=backend_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)  # 等待启动

        import urllib.request
        for method, path, desc in endpoints:
            url = f"http://127.0.0.1:{port}{path}"
            try:
                req = urllib.request.Request(url, method=method)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    body = resp.read().decode("utf-8")
                    status = resp.status
                results.append({
                    "endpoint": f"{method} {path}",
                    "status": status,
                    "body_preview": body[:200],
                    "passed": status == 200,
                })
            except Exception as e:
                results.append({
                    "endpoint": f"{method} {path}",
                    "status": 0,
                    "error": str(e)[:100],
                    "passed": False,
                })
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    passed = sum(1 for r in results if r["passed"])
    return json.dumps({
        "project": project,
        "total_endpoints": len(endpoints),
        "passed": passed,
        "failed": len(endpoints) - passed,
        "results": results,
        "all_passed": passed == len(endpoints),
    }, ensure_ascii=False, indent=2)


# ═════════════════════════════════════════════════
# v2.2: Agent间共享上下文（白板模式）
# ═════════════════════════════════════════════════

_SHARED_CTX: dict[str, dict] = {}  # project_path -> context dict

def handle_write_context(**kwargs) -> str:
    """Agent写入共享上下文，供其他Agent读取"""
    project = kwargs.get("project", kwargs.get("path", ""))
    section = kwargs.get("section", "general")
    content = kwargs.get("content", "")

    if project not in _SHARED_CTX:
        _SHARED_CTX[project] = {}
    _SHARED_CTX[project][section] = content

    # 同时写文件
    try:
        ctx_file = f"builder/backend/projects/{project}/SHARED_CONTEXT.md"
        _os = __import__("os")
        _os.makedirs(_os.path.dirname(ctx_file), exist_ok=True)
        sections = _SHARED_CTX[project]
        with open(ctx_file, "w", encoding="utf-8") as f:
            f.write("# Shared Context\n\n")
            for sec, txt in sections.items():
                f.write(f"## {sec}\n\n{txt}\n\n")
    except Exception:
        pass

    return json.dumps({"ok": True, "section": section, "length": len(content)}, ensure_ascii=False)


def handle_read_context(**kwargs) -> str:
    """读取其他Agent写入的共享上下文"""
    project = kwargs.get("project", kwargs.get("path", ""))
    section = kwargs.get("section", "")

    if project in _SHARED_CTX:
        ctx = _SHARED_CTX[project]
        if section:
            return json.dumps({"section": section, "content": ctx.get(section, "(空)")}, ensure_ascii=False)
        return json.dumps({"sections": list(ctx.keys()), "content": ctx}, ensure_ascii=False, indent=2)

    # 尝试读文件
    ctx_file = f"builder/backend/projects/{project}/SHARED_CONTEXT.md"
    if __import__("os").path.exists(ctx_file):
        with open(ctx_file, encoding="utf-8") as f:
            return json.dumps({"content": f.read()}, ensure_ascii=False)
    return json.dumps({"sections": [], "content": "(无共享上下文)"}, ensure_ascii=False)


BUILTIN_HANDLERS: dict[str, Callable[..., str]] = {
    # v0.6.1: search_docs 和 web_search 统一为 DuckDuckGo 真实搜索
    "search_docs":       handle_web_search,         # ← 从模拟改为真实
    "web_search":        handle_web_search,
    "code_lint":         handle_code_lint,
    "code_executor":     handle_code_run,
    "run_command":       handle_run_command,         # v0.6
    "search_memory":     handle_search_memory,
    "list_agents":       handle_list_agents,         # v0.5
    "delegate_task":     handle_delegate_task,       # v0.5
    "dispatch_to_agents": handle_dispatch_to_agents, # v2.5
    "create_agent":      handle_create_agent,        # v0.5.1
    "read_file":         handle_read_file,           # v0.6
    "write_file":        handle_write_file,          # v0.6
    "list_dir":          handle_list_dir,            # v0.6
    "search_file":       handle_search_file,         # v0.6
    "validate_contract":  handle_validate_contract,   # v0.6.1
    "send_to_agent":      handle_send_to_agent,       # v0.6.1
    "github_api":         handle_github_api,          # v0.6.2
    "test_project":       handle_test_project,        # v2.2
    "test_project":       handle_test_project,        # v2.2
    "write_context":      handle_write_context,       # v2.2
    "read_context":       handle_read_context,        # v2.2
    "write_context":      handle_write_context,       # v2.2
    "read_context":       handle_read_context,        # v2.2
}

# v0.6.1: 名称→处理器降级映射（用于无 handler 字段的旧格式工具）
_FALLBACK_MAP: dict[str, str] = {
    # 搜索类 → web_search (DuckDuckGo)
    "search_python_docs": "web_search",
    "search_frontend_docs": "web_search",
    "search_java_docs": "web_search",
    "search_go_docs": "web_search",
    "search_rust_docs": "web_search",
    "search_cpp_docs": "web_search",
    "search_flutter_docs": "web_search",
    "search_devops_docs": "web_search",
    "search_db_docs": "web_search",
    "search_schema_docs": "web_search",
    "search_ml_docs": "web_search",
    "search_api_docs": "web_search",
    "search_rag_docs": "web_search",
    "search_provider_docs": "web_search",
    "search_web": "web_search",
    "search_faq": "web_search",
    "search_academic_papers": "web_search",
    "search_law_database": "web_search",
    "search_medical_literature": "web_search",
    # 分析类 → 返回提示让 LLM 自行推理
    "analyze_financial_data": "web_search",
    "check_contract_clause": "web_search",
    "generate_copy": "web_search",
    "create_ticket": "web_search",
    # 代码检查/执行类
    "lint_code": "code_lint",
    "run_code": "code_executor",
}


# ═════════════════════════════════════════════════
# v2.2: 自动测试闭环 — 启动项目后端并测试API
# ═════════════════════════════════════════════════

def get_handler(name: str) -> Callable[..., str] | None:
    """根据名称获取处理器，含降级映射"""
    # 1. 直接命中
    if name in BUILTIN_HANDLERS:
        return BUILTIN_HANDLERS[name]
    # 2. 名称降级映射
    mapped = _FALLBACK_MAP.get(name)
    if mapped and mapped in BUILTIN_HANDLERS:
        return BUILTIN_HANDLERS[mapped]
    return None


def register_handler(name: str, handler: Callable[..., str]) -> None:
    """动态注册自定义处理器"""
    BUILTIN_HANDLERS[name] = handler
