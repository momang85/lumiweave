"""
AI Agent Hub — Agent 运行器 v0.2

新增功能：
- 完整的 Function Calling 循环（send → receive tool_call → execute → send back）
- 真实 Tool Handler 集成
- 安全防护：超时、最大迭代次数、输出截断
"""

from __future__ import annotations

import json
import textwrap
from typing import Callable

try:
    from .loader import AgentConfig, load_agent
    from .llm import BaseLLM, Message, ToolCall, LLMResponse, create_llm, MockLLM
    from .tool_handlers import get_handler
except ImportError:
    from loader import AgentConfig, load_agent
    from llm import BaseLLM, Message, ToolCall, LLMResponse, create_llm, MockLLM
    from tool_handlers import get_handler

# 模式定义（支持包导入、脚本导入、runner/目录运行）
try:
    from shared.agent_modes import AgentMode, ModeConfig
except ImportError:
    try:
        from agent_modes import AgentMode, ModeConfig
    except ImportError:
        import sys, os
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, _root)
        from shared.agent_modes import AgentMode, ModeConfig


# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

MAX_TOOL_ITERATIONS = 10   # 单轮对话最多连续调用工具 10 次
MAX_TOOL_OUTPUT_CHARS = 4000  # 单个工具输出最大字符数


# ──────────────────────────────────────────────
# Agent 运行器
# ──────────────────────────────────────────────

class AgentRunner:
    """
    Agent 运行时核心 v0.2。

    增强的 chat() 方法：
    1. 发送用户消息
    2. LLM 可能返回 tool_calls
    3. 执行工具 → 将结果注入对话
    4. 再次调用 LLM
    5. 重复直到 LLM 返回纯文本或达到上限
    """

    def __init__(self, agent_path: str):
        # 1. 加载 Agent
        self.config: AgentConfig = load_agent(agent_path)

        # 2. 读取运行模式
        raw_mode = getattr(self.config.runtime, "mode", "simple") or "simple"
        raw_mode_config = getattr(self.config.runtime, "mode_config", {}) or {}
        try:
            self._mode = AgentMode(raw_mode)
        except ValueError:
            self._mode = AgentMode.SIMPLE
        self._mode_config = ModeConfig.from_dict(raw_mode_config)
        self._mode_config.mode = self._mode

        # 3. 创建 LLM 客户端
        self.llm: BaseLLM = create_llm(
            provider=self.config.model.provider,
            model=self.config.model.model_name,
            agent_tags=self.config.meta.tags,
        )

        # 4. 转换 tools 为 OpenAI 格式
        self._openai_tools: list[dict] = self.config.to_openai_tools()
        self._tool_configs: dict[str, object] = {
            t.name: t for t in self.config.tools
        }

        # 5. 初始化对话历史
        self._messages: list[Message] = []
        self._build_initial_messages()

        # 6. 统计
        self._tool_call_count = 0

    # ── 公共属性 ──

    @property
    def agent_name(self) -> str:
        return self.config.meta.name

    @property
    def agent_avatar(self) -> str:
        return self.config.ui.avatar

    @property
    def welcome_message(self) -> str:
        return self.config.ui.welcome_message

    @property
    def suggested_questions(self) -> list[str]:
        return self.config.ui.suggested_questions

    @property
    def conversation_count(self) -> int:
        return sum(1 for m in self._messages if m.role == "user")

    @property
    def total_tokens_used(self) -> int:
        return self._total_tokens

    @property
    def tool_call_count(self) -> int:
        """累计工具调用次数"""
        return self._tool_call_count

    @property
    def has_tools(self) -> bool:
        """是否有可用工具"""
        return len(self._openai_tools) > 0

    @property
    def mode(self) -> str:
        """当前运行模式"""
        return self._mode.value

    @property
    def mode_label(self) -> str:
        """模式显示名"""
        from shared.agent_modes import get_mode_meta
        return get_mode_meta(self._mode)["name"]

    # ── 核心方法 ──

    def chat(self, user_input: str) -> str:
        """模式分发入口"""
        if self._mode == AgentMode.REACT:
            return self._chat_react(user_input)
        elif self._mode == AgentMode.PLANNER:
            return self._chat_planner(user_input)
        elif self._mode == AgentMode.REFLECTION:
            return self._chat_reflection(user_input)
        else:
            return self._chat_simple(user_input)

    def _chat_simple(self, user_input: str) -> str:
        """
        简单模式：标准 Function Calling 循环（v0.2 默认）。

        流程：
        user → LLM → [tool_calls? → execute → LLM → ...] → final text
        """
        self._messages.append(Message(role="user", content=user_input))

        iteration = 0
        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1
            response = self._safe_llm_call()

            if response.is_tool_call and response.tool_calls:
                self._total_tokens += response.total_tokens
                self._messages.append(Message(
                    role="assistant", content=response.content,
                    tool_calls=response.tool_calls,
                ))
                for tc in response.tool_calls:
                    tool_result = self._execute_tool(tc)
                    self._messages.append(Message(
                        role="tool", content=tool_result,
                        tool_call_id=tc.id, name=tc.name,
                    ))
                    self._tool_call_count += 1
                continue

            self._total_tokens += response.total_tokens
            self._messages.append(Message(role="assistant", content=response.content or ""))
            return response.content or ""

        return (
            f"[!] 工具调用达到上限（{MAX_TOOL_ITERATIONS} 次），已停止。"
            f"请简化你的问题或稍后再试。"
        )

    # ── ReAct 模式 ──

    def _chat_react(self, user_input: str) -> str:
        """
        ReAct 模式：Thought → Action → Observation 循环。

        将 system_prompt 注入 ReAct 格式指令，引导 LLM 按
        Thought / Action / Observation / Final Answer 结构输出。
        """
        from shared.agent_modes import DEFAULT_REACT_SYSTEM_APPEND

        # 确保 system prompt 含 ReAct 指令
        if "Thought" not in str(self._messages[0].content if self._messages else ""):
            react_instruction = DEFAULT_REACT_SYSTEM_APPEND
            if self._messages:
                current_sp = self._messages[0].content or ""
                self._messages[0] = Message(role="system", content=current_sp + "\n\n" + react_instruction)

        self._messages.append(Message(role="user", content=user_input))

        max_rounds = self._mode_config.react_max_rounds
        round_num = 0
        observations: list[str] = []

        while round_num < max_rounds:
            round_num += 1
            response = self._safe_llm_call()

            text = response.content or ""
            self._total_tokens += response.total_tokens

            # 检查是否含工具调用（原生 Function Calling）
            if response.is_tool_call and response.tool_calls:
                self._messages.append(Message(
                    role="assistant", content=text,
                    tool_calls=response.tool_calls,
                ))
                for tc in response.tool_calls:
                    tool_result = self._execute_tool(tc)
                    obs_msg = f"Observation: {tool_result}"
                    observations.append(obs_msg)
                    self._messages.append(Message(
                        role="tool", content=tool_result,
                        tool_call_id=tc.id, name=tc.name,
                    ))
                    self._tool_call_count += 1
                continue

            # 文本模式：解析 Thought / Action / Final Answer
            if "Final Answer:" in text or "Final Answer：" in text:
                parts = text.split("Final Answer:", 1) if "Final Answer:" in text else text.split("Final Answer：", 1)
                final = parts[1].strip() if len(parts) > 1 else text
                self._messages.append(Message(role="assistant", content=final))
                return final

            # 没有最终答案 → 记录思考并继续
            self._messages.append(Message(role="assistant", content=text))

            if observations:
                for obs in observations[-2:]:  # 注入最近观察
                    self._messages.append(Message(role="system", content=obs))

        # 达到上限，取最后一轮输出
        last = self._messages[-1].content if self._messages else ""
        return last or f"[!] ReAct 达到上限（{max_rounds} 轮），已停止。"

    # ── Planner 模式 ──

    def _chat_planner(self, user_input: str) -> str:
        """
        Planner 模式：LLM 拆解任务为计划 → 顺序执行每一步。

        1. 先请求 LLM 生成计划 [PLAN]...[/PLAN]
        2. 逐步骤执行（每次调用 LLM 执行一步）
        3. 收集中间结果，最终综合
        """
        from shared.agent_modes import DEFAULT_PLANNER_PROMPT

        plan_prompt = f"{DEFAULT_PLANNER_PROMPT}\n\n用户任务：{user_input}"
        self._messages.append(Message(role="user", content=plan_prompt))

        # 第1轮：生成计划
        response = self._safe_llm_call()
        plan_text = response.content or ""
        self._messages.append(Message(role="assistant", content=plan_text))

        # 提取 [PLAN] 块
        has_plan = "[PLAN]" in plan_text
        max_steps = self._mode_config.planner_max_steps
        results: list[str] = []

        for step in range(1, max_steps + 1):
            step_prompt = (
                f"请执行第 {step} 步。完成后报告结果，"
                f"并在末尾标注 {self._mode_config.planner_step_complete_tag}"
            )
            self._messages.append(Message(role="user", content=step_prompt))

            response = self._safe_llm_call()
            step_result = response.content or ""
            self._total_tokens += response.total_tokens
            self._messages.append(Message(role="assistant", content=step_result))

            results.append(step_result)

            if self._mode_config.planner_step_complete_tag in step_result:
                # 检查是否所有步骤完成
                if "完成" in step_result or "任务完成" in step_result or "all done" in step_result.lower():
                    break
            else:
                # 没有完成标记，可能最终步
                if step >= 3 and len(step_result) < 200:
                    break

        # 最终综合
        final_prompt = "请基于以上执行结果，给出最终综合回答。"
        self._messages.append(Message(role="user", content=final_prompt))
        response = self._safe_llm_call()
        final = response.content or ""
        self._messages.append(Message(role="assistant", content=final))
        return final

    # ── Reflection 模式 ──

    def _chat_reflection(self, user_input: str) -> str:
        """
        Reflection 模式：生成 → 自评 → 发现错误 → 修正再生。

        1. 正常生成回答
        2. 触发反思提示词，让 LLM 自评
        3. 如有问题，重新生成
        4. 最多反思 N 轮
        """
        reflection_prompt = self._mode_config.effective_reflection_prompt
        max_rounds = self._mode_config.max_reflection_rounds

        self._messages.append(Message(role="user", content=user_input))

        # 第1轮：生成
        response = self._safe_llm_call()
        current_answer = response.content or ""
        self._total_tokens += response.total_tokens
        self._messages.append(Message(role="assistant", content=current_answer))

        if not self._mode_config.enable_self_critique:
            return current_answer

        # 反思循环
        for round_num in range(1, max_rounds + 1):
            critique_prompt = (
                f"【第 {round_num} 轮自我检查】\n\n"
                f"你上次的回答是：\n---\n{current_answer[:2000]}\n---\n\n"
                + reflection_prompt
            )
            self._messages.append(Message(role="user", content=critique_prompt))

            response = self._safe_llm_call()
            revised = response.content or ""
            self._total_tokens += response.total_tokens

            # 判断是否需要修正
            need_revision = any(kw in revised for kw in [
                "修正", "改正", "错误", "更正", "调整", "补充",
                "revise", "correct", "fix", "update", "improve",
            ])

            if need_revision:
                current_answer = revised
                self._messages.append(Message(role="assistant", content=revised))
            else:
                self._messages.append(Message(role="assistant", content=revised))
                # 未检测到修正意图，退出反思
                break

        return current_answer

    def reset(self):
        """重置对话"""
        self._build_initial_messages()
        self._total_tokens = 0
        self._tool_call_count = 0

    def get_history_summary(self) -> str:
        """返回对话摘要"""
        lines = []
        for msg in self._messages:
            if msg.role == "system":
                continue
            if msg.role == "tool":
                preview = textwrap.shorten(msg.content or "", width=60, placeholder="...")
                lines.append(f"🔧 [{msg.name}]: {preview}")
                continue
            if msg.tool_calls:
                names = [tc.name for tc in msg.tool_calls]
                lines.append(f"{self.agent_avatar} Agent → 调用工具: {', '.join(names)}")
                continue
            role_tag = "👤 你" if msg.role == "user" else f"{self.agent_avatar} Agent"
            preview = textwrap.shorten(msg.content or "", width=80, placeholder="...")
            lines.append(f"{role_tag}: {preview}")
        return "\n".join(lines) if lines else "(无对话记录)"

    def list_tools(self) -> list[dict]:
        """列出 Agent 定义的所有 Tool（含真实 handler 信息）"""
        result = []
        for t in self.config.tools:
            handler = get_handler(t.handler) if t.handler else None
            result.append({
                "name": t.name,
                "description": t.description,
                "type": t.type,
                "handler": t.handler or "(默认)",
                "handler_available": handler is not None,
                "parameters": [
                    {"name": p.name, "type": p.type, "required": p.required}
                    for p in t.parameters
                ] if t.parameters else list(t.properties.keys()) if t.properties else [],
            })
        return result

    # ── 内部方法 ──

    def _build_initial_messages(self):
        """构建初始消息列表"""
        msgs = [Message(role="system", content=self.config.system_prompt)]

        # 注入 few-shot 示例（作为历史消息，不计数）
        for ex in self.config.examples:
            msgs.append(Message(role="user", content=ex.user))
            msgs.append(Message(role="assistant", content=ex.assistant))

        self._messages = msgs

    def _safe_llm_call(self) -> LLMResponse:
        """安全调用 LLM，首次 401 失败自动降级 Mock"""
        try:
            return self._call_llm()
        except Exception as e:
            error_msg = str(e).lower()
            if any(kw in error_msg for kw in ("401", "auth", "api key", "incorrect")):
                if not getattr(self, "_fallback_attempted", False):
                    self._fallback_attempted = True
                    print(
                        "\n[!] API Key 无效，自动切换到 Mock 模式。\n"
                        "   设置有效 Key: set OPENAI_API_KEY=sk-xxx\n"
                    )
                    self.llm = MockLLM(
                        model=self.config.model.model_name,
                        agent_tags=self.config.meta.tags,
                    )
                    return self._call_llm()
            raise

    def _call_llm(self) -> LLMResponse:
        """调用 LLM，传入 tools"""
        return self.llm.chat(
            messages=self._messages,
            tools=self._openai_tools if self._openai_tools else None,
            temperature=self.config.model.parameters.temperature,
            max_tokens=self.config.model.parameters.max_tokens,
        )

    def _execute_tool(self, tool_call: ToolCall) -> str:
        """
        执行一个工具调用并返回结果字符串。

        1. 找到对应的 handler（显式指定 → 名称推断 → 默认）
        2. 执行并捕获异常
        3. 截断过长输出
        """
        tool_config = self._tool_configs.get(tool_call.name)

        # 确定 handler 名称
        handler_name = self._resolve_handler(tool_call.name, tool_config)
        handler_func = get_handler(handler_name)

        if handler_func is None:
            return json.dumps({
                "error": f"工具 '{tool_call.name}' 的处理器 '{handler_name}' 未实现",
                "hint": "请在 tool_handlers.py 中实现该处理器或修改 Agent YAML 中的 handler 字段",
            }, ensure_ascii=False)

        # 执行
        timeout = tool_config.timeout if tool_config else 30
        try:
            result = handler_func(**tool_call.arguments, timeout=timeout)
        except Exception as e:
            return json.dumps({
                "error": f"工具执行失败: {type(e).__name__}: {e}",
                "tool": tool_call.name,
            }, ensure_ascii=False)

        # 截断过长结果
        if len(result) > MAX_TOOL_OUTPUT_CHARS:
            result = result[:MAX_TOOL_OUTPUT_CHARS] + "\n...(输出已截断)"

        return result

    def _resolve_handler(self, tool_name: str, tool_config) -> str:
        """
        智能解析 handler 名称：
        1. 显式指定 handler 字段 → 直接使用
        2. 工具名包含 'search' → search_docs
        3. 工具名包含 'lint' → code_lint
        4. 工具名包含 'run_code' 或 'exec' → code_executor
        5. 否则 → 使用 tool_name 本身
        """
        if tool_config and tool_config.handler:
            return tool_config.handler

        name_lower = tool_name.lower()
        if "search" in name_lower:
            return "search_docs"
        if "lint" in name_lower:
            return "code_lint"
        if "run_code" in name_lower or "exec" in name_lower:
            return "code_executor"
        if "web" in name_lower:
            return "web_search"

        # 最后兜底
        return tool_name

    # ── 私有属性 ──
    _total_tokens: int = 0
