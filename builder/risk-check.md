# AI Agent Hub Builder — 代码风险检查报告

## 一、安全风险分析

### 🔴 高风险

#### 1.1 代码执行工具（code_executor）

**位置**: `runner/tool_handlers.py:handle_code_run()`

**风险**: 用户可通过 Agent 对话触发任意 Python 代码在服务器上执行。

**现有防护**:
- ✅ `subprocess` 子进程隔离
- ✅ `timeout` 参数（默认 10s，最大 30s）
- ✅ 临时目录执行
- ✅ stdout/stderr 输出截断（2000 字符）
- ⚠️ 缺少网络隔离（代码可访问外网）
- ⚠️ 缺少文件系统限制（可读写用户临时目录以外的路径）
- ⚠️ 缺少资源限制（无 CPU/内存配额）

**建议加固**:
```python
# 添加资源限制
import resource
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))    # CPU 5 秒
resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))  # 256MB 内存
```

**止损措施**: 已有 `requires_approval: true` 标记，前端可弹窗确认。

#### 1.2 任意 YAML 导入触发远程代码执行？ ❌ 不存在

**位置**: `builder/backend/agent_service.py:import_from_yaml()`

**分析**: 仅使用 `yaml.safe_load()`（不是 `yaml.load()`），不执行任意 Python 对象。✅ 安全。

### 🟡 中风险

#### 2.1 ChromaDB 数据未加密

**位置**: `builder/backend/rag_engine.py`

**风险**: 知识库向量数据明文存储在磁盘上。

**建议**:
- 生产环境使用 ChromaDB 的认证功能
- 敏感知识库使用加密存储

#### 2.2 跨站请求伪造（CSRF）

**位置**: `builder/backend/main.py`

**分析**: CORS 配置为 `allow_origins=["*"]`。在本地开发环境可接受，生产环境必须收紧为具体域名。

**建议**:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    ...
)
```

#### 2.3 SSE 连接无认证

**位置**: `builder/backend/main.py:/api/chat`

**风险**: 任何人只要知道 agent_id 就能通过 SSE 调用聊天接口消耗 API Token。

**建议**: 生产环境加入 JWT/Bearer Token 认证。

#### 2.4 文件上传无大小限制

**位置**: `builder/backend/main.py:api_upload_knowledge()`

**风险**: 超大文件可能导致内存溢出或磁盘占满。

**建议**:
```python
# FastAPI 内置限制
app = FastAPI(max_upload_size=50 * 1024 * 1024)  # 50MB
```

### 🟢 低风险

#### 3.1 System Prompt 注入攻击

**位置**: Builder 用户可自定义 system_prompt。

**风险**: 恶意用户可能创建包含有害指令的 Agent（如"忽略所有安全规则"），当被他人使用时可能产生不良输出。

**建议**: 
- 模板市场的官方模板可信，用户自建 Agent 加风险标签
- 后续加入 system_prompt 静态扫描
- 对话中加入隐式的安全护栏 prompt

#### 3.2 前端 XSS（ChatMessage 组件）

**位置**: `builder/frontend/src/components/ChatMessage.tsx`

**分析**: 使用了 `dangerouslySetInnerHTML` 渲染 Markdown。

**现有防护**:
- ✅ `formatContent()` 中先执行了 `escapeHTML`（& → &amp;, < → &lt;, > → &gt;）
- ✅ 代码块使用 `<pre><code>` 渲染，不会被解析为 HTML

**结论**: 安全。XSS 向量已被覆盖。

---

## 二、性能风险

| 问题 | 风险 | 建议 |
|---|---|---|
| `handle_code_run` 同步执行会阻塞 FastAPI 事件循环 | 中 | 使用 `run_in_executor` 或 `asyncio.create_subprocess_exec` |
| ChromaDB 使用 `all-MiniLM-L6-v2` 每次加载模型 | 低 | 已实现单例延迟加载，首次加载 ~1s 可接受 |
| Agent YAML 导出每次都重新 `yaml.dump()` | 低 | 可缓存，但当前数据量小，无影响 |
| 前端 `setMessages` 在 SSE 每个 token 都更新 | 低 | React 18 自动批处理，可用 `useDeferredValue` 优化 |

---

## 三、兼容性风险

| 问题 | 状态 | 说明 |
|---|---|---|
| v0.1 Agent YAML 加载 | ✅ 兼容 | `to_openai_tools()` 自动转换扁平参数 |
| Windows GBK 编码 | ✅ 已修复 | 所有 emoji 替换为 ASCII 安全字符 |
| 缺少 Node.js 时的前端运行 | ⚠️ | 需要 Node.js 18+ 安装依赖 |
| 缺少 Python 3.10+ 时的后端运行 | ⚠️ | 依赖类型注解语法 |

---

## 四、总结

| 风险等级 | 数量 | 处理方式 |
|---|---|---|
| 🔴 高风险 | 2 | code_executor 已有多层防护但建议加固；YAML 导入无 RCE 风险 |
| 🟡 中风险 | 4 | 开发环境可接受，生产上线前需修复 |
| 🟢 低风险 | 2 | 已有基础防护 |

**总体评估**: 代码在开发/演示阶段风险可控。生产上线前需重点处理：CORS 收紧、认证机制、上传大小限制、code_executor 资源限制。
