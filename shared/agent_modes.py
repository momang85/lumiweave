"""
AI Agent Hub — Agent 运行模式定义 v0.5

三种默认模式，Agent YAML 可通过 mode 字段指定：
- ReAct:     Thought → Action → Observation 循环推理
- Planner:   LLM 拆解任务 → Planner 顺序执行步骤
- Reflection: 生成 → 自评 → 发现错误 → 修正再生
- Simple:    纯函数调用循环（默认，向后兼容）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ══════════════════════════════════════════════
# 枚举
# ══════════════════════════════════════════════

class AgentMode(str, Enum):
    """Agent 运行模式"""

    REACT = "react"              # Thought → Action → Observation 循环
    PLANNER = "planner"          # LLM 拆解任务 → 顺序执行步骤
    REFLECTION = "reflection"    # 生成 → 自评 → 纠错 → 再生
    SIMPLE = "simple"            # 纯函数调用循环（默认）


# ══════════════════════════════════════════════
# 模式配置
# ══════════════════════════════════════════════

@dataclass
class ModeConfig:
    """
    模式运行时配置。

    可通过 Agent YAML 的 `runtime.mode_config` 覆盖默认值。
    """

    mode: AgentMode = AgentMode.SIMPLE

    # ── 通用上限 ──
    max_iterations: int = 10           # 最大循环/步骤数
    max_step_tokens: int = 8000        # 单步最大输出字符数

    # ── ReAct 专用 ──
    react_max_rounds: int = 15         # 最大 Thought→Action→Observation 轮次
    react_thought_tag: str = "Thought" # Thought 段落标签
    react_action_tag: str = "Action"   # Action 段落标签
    react_final_tag: str = "Final Answer"  # 最终回答标签

    # ── Planner 专用 ──
    planner_max_steps: int = 10        # 计划最多步骤
    planner_step_complete_tag: str = "[STEP_COMPLETE]"

    # ── Reflection 专用 ──
    enable_self_critique: bool = True
    max_reflection_rounds: int = 3     # 最大反思修正轮次
    reflection_prompt: str = ""        # 空则使用默认模板

    @property
    def effective_reflection_prompt(self) -> str:
        """获取实际反射提示词"""
        return self.reflection_prompt or DEFAULT_REFLECTION_PROMPT

    @property
    def effective_planner_prompt(self) -> str:
        """获取实际规划提示词"""
        return DEFAULT_PLANNER_PROMPT

    @property
    def effective_react_system_append(self) -> str:
        """ReAct 模式下追加到 system_prompt 的指令"""
        return DEFAULT_REACT_SYSTEM_APPEND

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "max_iterations": self.max_iterations,
            "max_step_tokens": self.max_step_tokens,
            "react_max_rounds": self.react_max_rounds,
            "planner_max_steps": self.planner_max_steps,
            "enable_self_critique": self.enable_self_critique,
            "max_reflection_rounds": self.max_reflection_rounds,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ModeConfig":
        mode_val = d.get("mode", "simple")
        try:
            mode = AgentMode(mode_val)
        except ValueError:
            mode = AgentMode.SIMPLE

        return cls(
            mode=mode,
            max_iterations=d.get("max_iterations", 10),
            max_step_tokens=d.get("max_step_tokens", 8000),
            react_max_rounds=d.get("react_max_rounds", 15),
            planner_max_steps=d.get("planner_max_steps", 10),
            enable_self_critique=d.get("enable_self_critique", True),
            max_reflection_rounds=d.get("max_reflection_rounds", 3),
            reflection_prompt=d.get("reflection_prompt", ""),
        )

    @classmethod
    def default_for_mode(cls, mode: AgentMode) -> "ModeConfig":
        """为指定模式创建默认配置"""
        mc = cls(mode=mode)
        if mode == AgentMode.REACT:
            mc.max_iterations = mc.react_max_rounds
        elif mode == AgentMode.PLANNER:
            mc.max_iterations = mc.planner_max_steps
        elif mode == AgentMode.REFLECTION:
            mc.max_iterations = mc.max_reflection_rounds
        return mc


# ══════════════════════════════════════════════
# 默认提示词模板
# ══════════════════════════════════════════════

# 兼容旧引用
DEFAULT_REACT_THOUGHT_TAG = "Thought"
DEFAULT_REACT_ACTION_TAG = "Action"
DEFAULT_REACT_FINAL_TAG = "Final Answer"

DEFAULT_REACT_SYSTEM_APPEND = """
【运行模式：ReAct（推理+行动）】

你需要使用以下格式来思考和行动：

{thought_tag}: [你对当前情况的推理分析]
{action_tag}: [你要执行的动作，可以是工具调用或直接回答]
... (观察结果后)
{thought_tag}: [基于观察的新一轮推理]
{action_tag}: [下一步动作]
...
{final_tag}: [最终答案]

规则：
1. 每轮只执行一个动作
2. 如果使用工具，必须等观察结果后再推理
3. 当你确信答案时，用 {final_tag}: 输出最终回答
4. 不要跳过思考步骤直接给答案
""".format(
    thought_tag=DEFAULT_REACT_THOUGHT_TAG,
    action_tag=DEFAULT_REACT_ACTION_TAG,
    final_tag=DEFAULT_REACT_FINAL_TAG,
)

DEFAULT_REFLECTION_PROMPT = (
    "请仔细检查你刚才的回答，找出可能的问题：\n"
    "1. 事实是否正确？\n"
    "2. 逻辑是否连贯？\n"
    "3. 是否遗漏了重要信息？\n"
    "4. 格式是否符合要求？\n"
    "5. 是否有更优的解决方案？\n"
    "如果发现问题，请修正后重新输出完整、正确的回答。"
)

DEFAULT_PLANNER_PROMPT = (
    "你需要完成以下任务。\n"
    "第一步：先列出详细的执行计划（每个步骤一个编号）。\n"
    "第二步：依次执行每个步骤，每步结束后报告结果和状态。\n"
    "第三步：如果某一步失败，说明原因并尝试替代方案。\n"
    "第四步：所有步骤完成后，给出最终综合结果。\n\n"
    "使用以下格式输出计划：\n"
    "[PLAN]\n"
    "1. 步骤1描述\n"
    "2. 步骤2描述\n"
    "...\n"
    "[/PLAN]\n\n"
    "然后逐一执行每个步骤。"
)


# ══════════════════════════════════════════════
# 模式元信息（供 UI 展示）
# ══════════════════════════════════════════════

MODE_META: dict[AgentMode, dict[str, str]] = {
    AgentMode.SIMPLE: {
        "name": "简单模式",
        "icon": "💬",
        "description": "标准 LLM 对话 + Function Calling，适合大多数场景",
        "best_for": "问答、翻译、代码生成、知识检索",
        "max_rounds": "最多 10 轮工具调用",
    },
    AgentMode.REACT: {
        "name": "ReAct 推理模式",
        "icon": "🧠",
        "description": "交替推理（Thought）和行动（Action），观察结果后继续推理，适合需要多步推理的复杂任务",
        "best_for": "多步数学推理、逻辑分析、信息检索与综合",
        "max_rounds": "最多 15 轮 推理→行动→观察",
    },
    AgentMode.PLANNER: {
        "name": "Planner 规划模式",
        "icon": "📋",
        "description": "LLM 先拆解任务为步骤清单，再按依赖顺序依次执行并动态更新状态",
        "best_for": "项目管理、复杂工作流、代码架构设计",
        "max_rounds": "最多 10 个执行步骤",
    },
    AgentMode.REFLECTION: {
        "name": "Reflection 反思模式",
        "icon": "🪞",
        "description": "生成回答后自评检查，发现错误则自动修正并重新输出，经历 生成→评估→纠错→再生 循环",
        "best_for": "高准确率要求的任务、代码生成、学术写作",
        "max_rounds": "最多 3 轮反思修正",
    },
}


def get_mode_meta(mode: AgentMode | str) -> dict[str, str]:
    """获取模式元信息（供 UI）"""
    if isinstance(mode, str):
        try:
            mode = AgentMode(mode)
        except ValueError:
            mode = AgentMode.SIMPLE
    return MODE_META.get(mode, MODE_META[AgentMode.SIMPLE])


def list_modes() -> list[dict[str, Any]]:
    """列出所有可用模式（供 API 返回）"""
    return [
        {"mode": m.value, **meta}
        for m, meta in MODE_META.items()
    ]


__all__ = [
    "AgentMode", "ModeConfig",
    "get_mode_meta", "list_modes",
    "MODE_META",
    "DEFAULT_REFLECTION_PROMPT", "DEFAULT_PLANNER_PROMPT",
    "DEFAULT_REACT_SYSTEM_APPEND",
    "DEFAULT_REACT_THOUGHT_TAG", "DEFAULT_REACT_ACTION_TAG", "DEFAULT_REACT_FINAL_TAG",
]
