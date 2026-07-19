# Agent DSL 规范 v0.1 → 大规模/多样化场景 评估报告

## 结论：主体可用，但 4 个关键缺口需修复后才能支撑规模化

---

## 一、已具备的能力 ✅

| 维度 | 评估 | 说明 |
|------|------|------|
| Agent 身份标识 | ✅ | `meta.id` reverse-domain 形式天然适合索引和去重 |
| 标签分类 | ✅ | `tags` 支持多维搜索，可扩展为层级标签 |
| 多模型 | ✅ | provider + fallback 双保险，可水平扩展 provider |
| 工具定义 | ⚠️ | 字段够用但参数定义偏简单，见下文 |
| 知识源 | ✅ | file/url/text 三种类型覆盖主流场景 |
| 运行时约束 | ✅ | language + min_version + packages 足够描述环境 |
| UI 元数据 | ✅ | avatar + welcome + suggestions 可直驱前端渲染 |
| 语义化版本 | ✅ | `meta.version` 支持 SemVer，版本兼容逻辑留待 Runner 实现 |

## 二、需修复的 4 个关键缺口 🔴

### 缺口 1：Tool 参数定义不支持嵌套对象 —— 阻塞 Function Calling

**现状**：`parameters` 是扁平列表 `[{name, type, required}]`，无法描述嵌套结构。

**影响**：OpenAI Function Calling 要求 JSON Schema 格式，必须有 `properties` 嵌套。像 `run_code` 的参数 `{code: {type: string, description: ...}}` 用当前格式无法表达。

**修复**：`ToolConfig` 增加 `properties: dict` 字段，提供 JSON Schema 级的参数定义。

```yaml
tools:
  - name: "run_code"
    type: "function"
    handler: "code_executor"        # ← 新增：指定处理函数
    parameters:                     # 兼容旧格式
      properties:                   # 新格式：JSON Schema
        code:
          type: "string"
          description: "要执行的 Python 代码"
        python_version:
          type: "string"
          default: "3.12"
      required: ["code"]
    timeout: 30                     # ← 新增：执行超时
```

### 缺口 2：缺少 Tool 执行安全控制 —— 安全风险

**现状**：无 timeout、无 sandbox 标记、无权限声明。

**影响**：`run_code` 类工具可能造成死循环；敏感工具（如文件写入）无法被 Runner 感知并拦截。

**修复**：`ToolConfig` 增加：
- `timeout`: 执行超时（秒）
- `requires_approval`: 是否需要用户确认
- `sandbox`: 是否在沙箱中运行

### 缺口 3：模型配置缺少 Tool Call 开关 —— 功能不完整

**现状**：`model.parameters` 只有 temperature/max_tokens/top_p。

**影响**：无法声明 Agent 是否启用 Tool Calling，无法控制工具选择策略（auto/none/required）。

**修复**：`ModelParameters` 增加：
- `tool_choice`: "auto" | "none" | "required" | 具体工具名
- `parallel_tool_calls`: 是否允许并行调用

### 缺口 4：缺少示例对话 —— 影响 Few-shot 效果

**现状**：只有 system_prompt，无 few-shot examples。

**影响**：复杂 Agent（如多步推理）缺乏行为模板，LLM 输出不稳定。

**修复**：AgentConfig 增加可选 `examples` 字段。

---

## 三、规模化考量（暂不阻塞，但需规划）

| 问题 | 现状 | 建议 |
|------|------|------|
| Agent 包过大（含知识库文件） | 无限制 | 后续需 max_bundle_size 限制 |
| 千人并发下载 | 静态 YAML 无压力 | 需 CDN + 去重存储 |
| Agent 间依赖引用 | 不支持 | 后续 `extends` 字段（类似 Docker FROM） |
| 变量替换 | 不支持 `{{var}}` | 后续 `variables` 配置块 |
| 审核状态 | 无字段 | 后续 `meta.status: draft|reviewed|published|banned` |
| 统计信息 | 无字段 | 后续 `stats: {downloads, rating, usage_count}` |

---

## 四、v0.2 升级清单

基于以上分析，规范升级到 v0.2 的最小变更：

1. `ToolConfig.type` 增加 `"function"` 类型（对应 OpenAI function calling）
2. `ToolConfig` 增加 `handler`、`properties`、`timeout`、`requires_approval`
3. `ToolParam` 增加 `description`、`items`（支持数组类型）
4. `ModelParameters` 增加 `tool_choice`、`parallel_tool_calls`
5. `AgentConfig` 增加可选的 `examples` 字段
