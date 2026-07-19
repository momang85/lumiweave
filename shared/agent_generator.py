"""
AI Agent Hub — 自然语言 → Agent YAML 生成管线 v0.3

两阶段生成：
1. LLM 分析意图 → JSON 骨架
2. 补全细节 → 完整 YAML
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .ir_models import (
    AgentIR,
    MessageIR,
    ProviderType,
    ToolDefIR,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
# 领域模板
# ══════════════════════════════════════════════

class AgentDomain(str, Enum):
    """Agent 应用领域"""
    BACKEND = "backend"
    FRONTEND = "frontend"
    FULLSTACK = "fullstack"
    MOBILE = "mobile"
    AI_ML = "ai_ml"
    DATA_SCIENCE = "data_science"
    DEVOPS = "devops"
    SECURITY = "security"
    DATABASE = "database"

    LEGAL = "legal"
    FINANCE = "finance"
    MEDICAL = "medical"
    EDUCATION = "education"
    MARKETING = "marketing"
    ECOMMERCE = "ecommerce"
    CUSTOMER_SERVICE = "customer_service"

    CREATIVE = "creative"
    GENERAL = "general"


@dataclass
class DomainTemplate:
    """领域预设模板"""
    domain: AgentDomain
    name_cn: str
    default_avatar: str
    default_tools: list[ToolDefIR] = field(default_factory=list)
    knowledge_sources: list[dict[str, str]] = field(default_factory=list)
    system_prompt_skeleton: str = ""  # 含 {agent_name} 等占位符
    suggested_questions: list[str] = field(default_factory=list)
    example_system_prompt: str = ""


# ── 领域模板库 ──

DOMAIN_TEMPLATES: dict[AgentDomain, DomainTemplate] = {
    AgentDomain.LEGAL: DomainTemplate(
        domain=AgentDomain.LEGAL,
        name_cn="法律助手",
        default_avatar="⚖️",
        default_tools=[
            ToolDefIR("search_law_database", "搜索法律法规数据库",
                      parameters={"query": {"type": "string", "description": "搜索关键词"},
                                  "jurisdiction": {"type": "string", "enum": ["中国", "国际"],
                                                    "default": "中国"}},
                      required=["query"]),
            ToolDefIR("check_contract_clause", "检查合同条款合规性",
                      parameters={"clause": {"type": "string", "description": "合同条款文本"}},
                      required=["clause"]),
        ],
        knowledge_sources=[
            {"type": "url", "source": "https://flk.npc.gov.cn/"},
            {"type": "url", "source": "https://wenshu.court.gov.cn/"},
        ],
        system_prompt_skeleton=(
            "你是一名资深法律顾问，专精中国法律法规。"
            "你的职责：\n"
            "1. 解答法律咨询，引用具体法条\n"
            "2. 审查合同条款，标注风险点\n"
            "3. 提供合规建议\n"
            "注意：你提供的是法律参考意见，不构成正式法律意见。"
        ),
        suggested_questions=[
            "帮我审查这份劳动合同的竞业限制条款",
            "创业公司股权分配有哪些法律风险？",
            "数据隐私法（个保法）对公司有什么要求？",
        ],
    ),
    AgentDomain.FINANCE: DomainTemplate(
        domain=AgentDomain.FINANCE,
        name_cn="金融分析师",
        default_avatar="💰",
        default_tools=[
            ToolDefIR("analyze_financial_data", "分析财务数据",
                      parameters={"data": {"type": "string", "description": "财务数据"},
                                  "metrics": {"type": "array", "items": {"type": "string"}}},
                      required=["data"]),
        ],
        knowledge_sources=[
            {"type": "url", "source": "https://www.sse.com.cn/"},
            {"type": "url", "source": "https://www.cninfo.com.cn/"},
        ],
        system_prompt_skeleton=(
            "你是一名资深金融分析师。职责：财务报表分析、投资建议、风险评估。"
            "基于数据驱动给出结论，标注不确定性和假设前提。"
            "提醒：不构成投资建议。"
        ),
        suggested_questions=[
            "帮我分析这家公司的资产负债表健康状况",
            "当前市场环境下的资产配置策略建议",
            "如何评估一家创业公司的估值？",
        ],
    ),
    AgentDomain.MEDICAL: DomainTemplate(
        domain=AgentDomain.MEDICAL,
        name_cn="健康顾问",
        default_avatar="🏥",
        default_tools=[
            ToolDefIR("search_medical_literature", "搜索医学文献",
                      parameters={"query": {"type": "string"}},
                      required=["query"]),
        ],
        knowledge_sources=[
            {"type": "url", "source": "https://pubmed.ncbi.nlm.nih.gov/"},
        ],
        system_prompt_skeleton=(
            "你是一名健康知识顾问。基于循证医学提供健康信息。"
            "明确说明：你提供的是健康科普，不能替代医生诊断。"
            "遇到急症症状，应建议立即就医。"
        ),
        suggested_questions=[
            "长期久坐办公有哪些健康风险？如何改善？",
            "帮我解读这份体检报告的关键指标",
            "失眠的常见原因和非药物治疗方法",
        ],
    ),
    AgentDomain.EDUCATION: DomainTemplate(
        domain=AgentDomain.EDUCATION,
        name_cn="教育导师",
        default_avatar="📚",
        default_tools=[
            ToolDefIR("search_academic_papers", "搜索学术论文",
                      parameters={"query": {"type": "string"},
                                  "field": {"type": "string", "default": "all"}},
                      required=["query"]),
        ],
        knowledge_sources=[
            {"type": "url", "source": "https://scholar.google.com/"},
            {"type": "url", "source": "https://arxiv.org/"},
        ],
        system_prompt_skeleton=(
            "你是一名教育导师。职责：课程设计、学习方法指导、论文辅导、知识讲解。"
            "用通俗语言解释复杂概念，因材施教。"
        ),
        suggested_questions=[
            "帮我设计一个为期一个月的Python入门学习计划",
            "怎么写好一篇学术论文的文献综述？",
            "费曼学习法怎么应用到编程学习中？",
        ],
    ),
    AgentDomain.MARKETING: DomainTemplate(
        domain=AgentDomain.MARKETING,
        name_cn="营销专家",
        default_avatar="📊",
        default_tools=[
            ToolDefIR("generate_copy", "生成营销文案",
                      parameters={"product": {"type": "string"}, "tone": {"type": "string",
                                            "enum": ["专业", "活泼", "感人", "幽默"], "default": "专业"},
                                  "platform": {"type": "string", "default": "通用"}},
                      required=["product"]),
        ],
        knowledge_sources=[],
        system_prompt_skeleton=(
            "你是一名资深营销专家。职责：广告文案、SEO优化、品牌策略、用户分析。"
            "文案要突出卖点，符合平台调性。"
        ),
        suggested_questions=[
            "帮我为这款SaaS产品写一个落地页文案",
            "小红书和抖音的营销内容策略有什么不同？",
            "如何用数据分析优化广告投放ROI？",
        ],
    ),
    AgentDomain.CUSTOMER_SERVICE: DomainTemplate(
        domain=AgentDomain.CUSTOMER_SERVICE,
        name_cn="客服助手",
        default_avatar="💬",
        default_tools=[
            ToolDefIR("search_faq", "搜索常见问题库",
                      parameters={"query": {"type": "string"}},
                      required=["query"]),
            ToolDefIR("create_ticket", "创建工单",
                      parameters={"issue": {"type": "string"}, "priority": {"type": "string",
                                            "enum": ["低", "中", "高", "紧急"], "default": "中"}},
                      required=["issue"]),
        ],
        knowledge_sources=[],
        system_prompt_skeleton=(
            "你是一名专业客服。职责：解答用户问题、处理投诉、创建工单。"
            "态度礼貌耐心，问题分级处理。无法解决的问题明确告知并升级。"
        ),
        suggested_questions=[
            "如何处理用户对产品功能的投诉？",
            "帮我设计一个客服对话脚本",
        ],
    ),
    AgentDomain.CREATIVE: DomainTemplate(
        domain=AgentDomain.CREATIVE,
        name_cn="创意文案",
        default_avatar="🎨",
        default_tools=[],
        knowledge_sources=[],
        system_prompt_skeleton=(
            "你是一名创意文案专家。擅长品牌故事、广告语、社交媒体内容创作。"
            "风格多样，按需求切换。注意版权和原创性。"
        ),
        suggested_questions=[
            "帮我为新产品写一句品牌slogan",
            "怎么写一篇吸引人的小红书种草笔记？",
        ],
    ),
    AgentDomain.GENERAL: DomainTemplate(
        domain=AgentDomain.GENERAL,
        name_cn="通用助手",
        default_avatar="🤖",
        default_tools=[
            ToolDefIR("search_web", "网络搜索",
                      parameters={"query": {"type": "string"}},
                      required=["query"]),
        ],
        knowledge_sources=[],
        system_prompt_skeleton=(
            "你是一个通用AI助手。提供广泛的知识问答、任务辅助、信息检索。"
        ),
        suggested_questions=["帮我总结今天的重要新闻", "推荐几本值得读的书"],
    ),
}


# ══════════════════════════════════════════════
# NL → Agent 生成 Prompt 模板 v0.5
# 严格注入智能 Agent 结构化规范 V1.0
# ══════════════════════════════════════════════

AGENT_GENERATION_SYSTEM_PROMPT = """你是一个 JSON 生成器。你的唯一任务是：根据用户需求输出一个 JSON 对象。

【输出格式 — 只输出 JSON，不要任何其他文字】
```json
{
    "meta": {
        "domain": "领域英文",
        "name": "Agent名称（≤6字）",
        "description": "一句话描述",
        "tags": ["标签"],
        "domain_category": "legal|finance|medical|education|marketing|customer_service|creative|backend|frontend|ai_ml|devops|general"
    },
    "architecture": {
        "mode": "simple|react|planner|reflection",
        "max_steps": 15,
        "stop_token": "<FINAL_ANSWER>"
    },
    "system_prompt_modules": {
        "role_definition": "角色定义（50字以上）",
        "capability_declaration": "可用工具列表（30字以上）",
        "output_format": "输出格式说明，含<THOUGHT>/<ACTION>/<FINAL_ANSWER>标签示例（80字以上）",
        "planning_instruction": "规划指令：拆解步骤→逐步执行（60字以上）",
        "reflection_instruction": "反思指令：失败时输出<REFLECTION>（50字以上）",
        "safety_boundary": "安全边界：禁止操作/脱敏/免责（30字以上）"
    },
    "suggested_tools": [
        {"name": "工具名", "description": "描述", "parameters": [{"name":"参数","type":"string","description":"说明","required":true}]}
    ],
    "suggested_knowledge": ["知识源"],
    "suggested_questions": ["推荐问题3-5个"],
    "memory_config": {"short_term_window": 10, "working_memory_keys": ["Key名"]}
}
```

【填充规则 — 按以下要求填写 system_prompt_modules 各字段的内容】
1. role_definition：指明确 Agent 的身份、专业领域、目标受众
2. capability_declaration：列出 Agent 可用的工具及用途
3. output_format：你拥有以下工具（见能力声明）。当你需要外部信息或执行操作时，请直接调用相应工具。系统会自动执行工具并将结果返回给你。收到结果后，你继续分析并给出最终回答。直接给出推理和结论，无需使用特殊标签格式。
4. planning_instruction：复杂任务先输出计划再逐步执行，每步评估结果
5. reflection_instruction：连续2次无进展或出错时输出 <REFLECTION>原因+修正</REFLECTION>
6. safety_boundary：严禁危险操作、信息脱敏、免责声明（如不构成法律/投资建议）

【模式选择】
- simple：问答/翻译 | react：多步推理 | planner：复杂工作流 | reflection：高准确率

再次强调：只输出 JSON，不要 Markdown 标题、不要解释、不要额外文字。"""


AGENT_REFINEMENT_PROMPT = """根据用户反馈，修改 Agent 定义。

当前定义：
{current_definition}

用户反馈：
{user_feedback}

输出修改后的完整 JSON 定义（格式同上，严格遵守所有规范要求）。"""


# ══════════════════════════════════════════════
# 生成器
# ══════════════════════════════════════════════

@dataclass
class AgentGenerationResult:
    """生成结果"""
    agent_ir: AgentIR | None = None
    raw_skeleton: dict[str, Any] = field(default_factory=dict)
    yaml_content: str = ""
    warnings: list[str] = field(default_factory=list)
    success: bool = False
    error: str = ""


class AgentGenerator:
    """
    自然语言 → Agent 生成器。

    两阶段流程：
    1. analyze_intent(): LLM 分析用户输入 → JSON 骨架
    2. build_agent(): 骨架 + 领域模板 → AgentIR + YAML

    使用方式：
        gen = AgentGenerator(llm_adapter=openai_adapter)
        result = gen.generate("我要一个帮我写法律合同的助手")
        if result.success:
            print(result.yaml_content)
    """

    def __init__(self, llm_adapter=None):
        """
        Args:
            llm_adapter: 任意 BaseAdapter 实例（用于 LLM 调用）
                        为 None 时使用模板直出（不调用 LLM）
        """
        self._llm = llm_adapter

    def generate(
        self,
        user_input: str,
        domain_hint: AgentDomain | None = None,
        provider: ProviderType = ProviderType.OPENAI,
        model: str = "gpt-4o-mini",
        available_tools: list[dict] | None = None,
        tool_presets_hint: str = "",
    ) -> AgentGenerationResult:
        """
        完整生成流程。

        Args:
            user_input: 用户自然语言描述
            domain_hint: 领域提示（可选）
            provider: 目标 Provider
            model: 目标模型
            available_tools: 可用工具预设清单（不含Key），供LLM选择
            tool_presets_hint: 工具预设说明文本，注入 system_prompt
        """
        result = AgentGenerationResult()
        warnings: list[str] = []

        # v0.6: 存储可用工具，供 _analyze_intent 引用
        self._available_tools = available_tools or []

        if not user_input.strip():
            result.error = "输入不能为空"
            return result

        # 阶段 1：意图分析
        skeleton = self._analyze_intent(user_input, domain_hint, result)
        if not skeleton:
            return result

        result.raw_skeleton = skeleton
        result.warnings = warnings

        # 阶段 2：构建 Agent
        agent_ir = self._build_agent(skeleton, provider, model, warnings)
        result.agent_ir = agent_ir
        result.success = True

        # 导出 YAML
        try:
            import yaml
            result.yaml_content = yaml.dump(
                agent_ir.to_yaml_dict(),
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
        except ImportError:
            result.yaml_content = json.dumps(agent_ir.to_dict(), ensure_ascii=False, indent=2)

        return result

    def _analyze_intent(
        self,
        user_input: str,
        domain_hint: AgentDomain | None,
        result: AgentGenerationResult,
    ) -> dict[str, Any] | None:
        """阶段 1：分析用户意图，返回 JSON 骨架"""

        if self._llm is not None:
            try:
                # v0.6: 注入可用工具提示
                tools_hint = ""
                if self._available_tools:
                    tool_list = "\n".join(
                        f"  - {t['name']}: {t.get('description','')} (handler: {t.get('handler','')})"
                        for t in self._available_tools
                    )
                    tools_hint = f"\n\n【可用工具清单 - 请从以下工具中选择合适的分发给 Agent】\n{tool_list}\n"
                    tools_hint += "注意：suggested_tools 中的工具名必须与上面清单中的 name 完全一致。"
                    tools_hint += "需要 API Key 的工具已标注 handler，创建后系统会自动注入密钥。"

                messages = [
                    MessageIR.system(AGENT_GENERATION_SYSTEM_PROMPT + tools_hint),
                    MessageIR.user(f"用户需求：{user_input}\n\n请生成 Agent 定义 JSON。"),
                ]
                response = self._llm.chat(messages, temperature=0.3, max_tokens=4000)

                if response.content:
                    skeleton = self._parse_json(response.content)
                    if skeleton:
                        return skeleton

                    # JSON 解析失败 → 尝试从 LLM 文本中提取内容合并到模板
                    extracted = self._extract_from_text(response.content, user_input, domain_hint)
                    if extracted:
                        result.warnings.append("LLM 返回格式非 JSON，已提取内容合并到模板")
                        return extracted

                result.warnings.append("LLM 返回值解析失败，使用模板生成")
            except Exception as e:
                logger.warning(f"LLM 调用失败，使用模板生成: {e}")
                result.warnings.append(f"LLM 调用异常: {e}")

        # 降级：基于模板 + 关键词匹配
        return self._template_fallback(user_input, domain_hint)

    def _template_fallback(
        self, user_input: str, domain_hint: AgentDomain | None
    ) -> dict[str, Any]:
        """无 LLM 时的模板降级方案（输出与 LLM 相同 schema）"""
        domain = domain_hint or self._guess_domain(user_input)
        template = DOMAIN_TEMPLATES.get(domain, DOMAIN_TEMPLATES[AgentDomain.GENERAL])

        return {
            "meta": {
                "domain": domain.value,
                "domain_category": domain.value,
                "name": template.name_cn,
                "description": f"{template.name_cn} - 基于模板生成",
                "tags": [domain.value],
            },
            "architecture": {
                "mode": "simple",
                "max_steps": 15,
                "stop_token": "<FINAL_ANSWER>",
            },
            "system_prompt_modules": {
                "role_definition": f"你是一个{template.name_cn}。" + template.system_prompt_skeleton,
                "capability_declaration": "你可以使用以下工具：" + ", ".join(
                    t.name for t in template.default_tools
                ) if template.default_tools else "暂无特殊工具。",
                "output_format": (
                    "你拥有以下工具（见能力声明）。当你需要外部信息或执行操作时，请直接调用相应工具。"
                    "系统会自动执行工具并将结果返回给你。收到结果后，你继续分析并给出最终回答。"
                    "直接给出你的推理和结论，无需使用特殊标签格式。"
                ),
                "planning_instruction": (
                    "面对复杂问题，必须先拆解为步骤列表，再逐步执行。"
                    "每一步执行后评估结果，决定下一步行动。"
                ),
                "reflection_instruction": (
                    "当连续2次行动无进展或收到明确错误时，必须输出反思：\n"
                    "<REFLECTION>\n"
                    "失败原因：[分析]\n"
                    "修正方案：[新方案]\n"
                    "</REFLECTION>"
                ),
                "safety_boundary": (
                    "严禁执行危险操作（如删除文件、修改系统配置、发送未经审核的消息）。"
                    "涉及个人信息时必须脱敏处理。"
                    "你提供的是参考建议，不构成法律/医疗/投资意见。"
                ),
            },
            "suggested_tools": [
                {"name": t.name, "description": t.description, "parameters": []}
                for t in template.default_tools
            ],
            "suggested_knowledge": [
                k["source"] for k in template.knowledge_sources
            ],
            "suggested_questions": template.suggested_questions,
            "memory_config": {
                "short_term_window": 10,
                "working_memory_keys": ["任务目标", "当前步骤", "中间结果"],
            },
            "_template_based": True,
        }

    def _build_agent(
        self,
        skeleton: dict[str, Any],
        provider: ProviderType,
        model: str,
        warnings: list[str],
    ) -> AgentIR:
        """阶段 2：将骨架构建为完整 AgentIR（v0.5 新 schema）"""
        # ── 兼容新旧 schema ──
        meta = skeleton.get("meta", skeleton)
        arch = skeleton.get("architecture", {})
        sp_modules = skeleton.get("system_prompt_modules", {})
        tools_data = skeleton.get("suggested_tools", [])
        knowledge_data = skeleton.get("suggested_knowledge", [])
        questions = skeleton.get("suggested_questions", [])
        mem_cfg = skeleton.get("memory_config", {})
        tags = meta.get("tags", skeleton.get("tags", []))

        domain_str = meta.get("domain_category", skeleton.get("domain", "general"))
        try:
            domain = AgentDomain(domain_str)
        except ValueError:
            domain = AgentDomain.GENERAL

        template = DOMAIN_TEMPLATES.get(domain, DOMAIN_TEMPLATES[AgentDomain.GENERAL])

        # ── 生成 ID ──
        agent_id = f"com.aihub.{uuid.uuid4().hex[:10]}"

        # ── 组装 6 模块 system_prompt ──
        system_prompt = self._assemble_system_prompt(sp_modules, template)

        # ── 解析模式 ──
        raw_mode = arch.get("mode", "simple")
        from .agent_modes import AgentMode
        try:
            mode = AgentMode(raw_mode)
        except ValueError:
            mode = AgentMode.SIMPLE

        # ── 构建工具 ──
        tools = list(template.default_tools)
        for tool_data in tools_data:
            if isinstance(tool_data, dict) and tool_data.get("name"):
                if not any(t.name == tool_data["name"] for t in tools):
                    # 解析参数
                    params = {}
                    required = []
                    for p in tool_data.get("parameters", []):
                        if isinstance(p, dict):
                            pname = p.get("name", "")
                            params[pname] = {
                                "type": p.get("type", "string"),
                                "description": p.get("description", ""),
                            }
                            if p.get("required"):
                                required.append(pname)
                    tools.append(ToolDefIR(
                        name=tool_data["name"],
                        description=tool_data.get("description", ""),
                        parameters=params,
                        required=required,
                    ))

        # ── 构建知识源 ──
        knowledge = list(template.knowledge_sources)
        for k in knowledge_data:
            source = k if isinstance(k, str) else k.get("source", str(k))
            if source and source not in [ks["source"] for ks in knowledge]:
                knowledge.append({"type": "url", "source": source})

        # ── 建议问题 ──
        suggested_questions = questions if questions else template.suggested_questions

        agent_name = meta.get("name", template.name_cn)
        agent_desc = meta.get("description", f"{template.name_cn} - AI生成")

        return AgentIR(
            id=agent_id,
            name=agent_name,
            version="1.0.0",
            author="AI Hub Generator",
            description=agent_desc,
            mode=mode,
            provider=provider,
            model_name=model,
            temperature=0.3,
            max_tokens=8192,
            system_prompt=system_prompt,
            tools=tools,
            knowledge_sources=knowledge,
            avatar=template.default_avatar,
            welcome_message=f"你好！我是{agent_name}。有什么可以帮你的？",
            suggested_questions=suggested_questions,
            tags=tags if tags else [domain.value],
        )

    @staticmethod
    def _assemble_system_prompt(
        sp_modules: dict[str, str],
        template: DomainTemplate,
    ) -> str:
        """
        将 6 模块组装为标准 system_prompt。

        输出格式严格遵循规范第6节：
        1. 角色定义
        2. 能力声明
        3. 输出格式说明
        4. 规划指令
        5. 反思指令
        6. 安全边界
        """
        # 回退值
        if not sp_modules or not isinstance(sp_modules, dict):
            return template.system_prompt_skeleton or "你是一个有用的AI助手。"

        role = sp_modules.get("role_definition", "")
        capability = sp_modules.get("capability_declaration", "")
        output_fmt = sp_modules.get("output_format", "")
        planning = sp_modules.get("planning_instruction", "")
        reflection = sp_modules.get("reflection_instruction", "")
        safety = sp_modules.get("safety_boundary", "")

        # 用模板值回填空缺模块
        if not role and template.system_prompt_skeleton:
            role = template.system_prompt_skeleton
        if not output_fmt:
            output_fmt = (
                "你拥有以下工具（见能力声明）。当你需要外部信息或执行操作时，请直接调用相应工具。"
                "系统会自动执行工具并将结果返回给你。收到结果后，你继续分析并给出最终回答。"
                "直接给出你的推理和结论，无需使用特殊标签格式。"
            )
        if not planning:
            planning = "遇到复杂问题请先拆解为步骤列表，再逐步执行。"
        if not reflection:
            reflection = "行动失败或连续无进展时，输出 <REFLECTION>分析原因并修正。</REFLECTION>"
        if not safety:
            safety = "严禁执行危险操作。涉及个人信息需脱敏。本回答不构成法律/医疗/投资建议。"

        parts = []
        if role:
            parts.append(f"## 角色定义\n{role}")
        if capability:
            parts.append(f"## 能力\n{capability}")
        if output_fmt:
            parts.append(f"## 输出格式\n{output_fmt}")
        if planning:
            parts.append(f"## 规划指令\n{planning}")
        if reflection:
            parts.append(f"## 反思指令\n{reflection}")
        if safety:
            parts.append(f"## 安全边界\n{safety}")

        return "\n\n".join(parts) if parts else "你是一个有用的AI助手。"

    @staticmethod
    def _guess_domain(text: str) -> AgentDomain:
        """根据关键词猜测领域"""
        text_lower = text.lower()

        keyword_map = {
            AgentDomain.LEGAL: ["法律", "合同", "律师", "合规", "法规", "诉讼"],
            AgentDomain.FINANCE: ["金融", "财务", "投资", "股票", "理财", "基金", "保险"],
            AgentDomain.MEDICAL: ["医疗", "健康", "医生", "诊断", "药物", "手术", "体检"],
            AgentDomain.EDUCATION: ["教育", "学习", "课程", "考试", "论文", "培训", "教学"],
            AgentDomain.MARKETING: ["营销", "广告", "推广", "品牌", "SEO", "文案", "运营"],
            AgentDomain.CUSTOMER_SERVICE: ["客服", "售后", "投诉", "咨询", "工单"],
            AgentDomain.CREATIVE: ["创意", "设计", "文案", "品牌故事", "slogan"],
            AgentDomain.BACKEND: ["后端", "api", "fastapi", "django", "数据库", "微服务"],
            AgentDomain.FRONTEND: ["前端", "react", "vue", "页面", "组件", "ui"],
            AgentDomain.AI_ML: ["机器学习", "深度学习", "模型", "训练", "llm", "rag"],
            AgentDomain.DEVOPS: ["运维", "部署", "docker", "k8s", "ci/cd", "监控"],
        }

        scores = {}
        for domain, keywords in keyword_map.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[domain] = score

        if scores:
            return max(scores, key=scores.get)
        return AgentDomain.GENERAL

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any] | None:
        """从 LLM 输出中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        import re
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取 { ... }
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _extract_from_text(
        text: str, user_input: str, domain_hint: AgentDomain | None
    ) -> dict[str, Any] | None:
        """
        从 LLM 返回的非 JSON 文本中提取有用信息，合并到模板结构中。

        适用于 LLM 返回了 Markdown 格式的系统提示词而非 JSON 的情况。
        """
        import re

        # 尝试从 Markdown 标题中拆分各模块
        modules: dict[str, str] = {}
        headings = [
            ("## 角色定义", "role_definition"),
            ("## 能力", "capability_declaration"),
            ("## 输出格式", "output_format"),
            ("## 规划指令", "planning_instruction"),
            ("## 反思指令", "reflection_instruction"),
            ("## 安全边界", "safety_boundary"),
        ]

        for heading, key in headings:
            # 匹配标题到下一个 ## 标题或文本结束
            pattern = rf'{heading}\s*\n(.*?)(?=\n##\s|\Z)'
            m = re.search(pattern, text, re.DOTALL)
            if m:
                modules[key] = m.group(1).strip()

        if not modules:
            return None  # 无法提取任何模块，放弃

        # 获取模板基础结构
        domain = domain_hint or AgentGenerator._guess_domain(user_input)
        template = DOMAIN_TEMPLATES.get(domain, DOMAIN_TEMPLATES[AgentDomain.GENERAL])

        # 尝试从文本中提取 Agent 名称（取第一段标题前的内容）
        name_match = re.search(r'^#+\s*(.+?)(?:\n|$)', text, re.MULTILINE)
        agent_name = name_match.group(1).strip()[:6] if name_match else template.name_cn

        # 合并：模板做基底，LLM 输出覆盖
        fallback = AgentGenerator._make_template_fallback(user_input, domain_hint)
        for key in [
            "role_definition", "capability_declaration", "output_format",
            "planning_instruction", "reflection_instruction", "safety_boundary",
        ]:
            if key in modules and modules[key]:
                fallback["system_prompt_modules"][key] = modules[key]

        fallback["meta"]["name"] = agent_name
        fallback["meta"]["description"] = f"{agent_name} - AI生成"
        fallback["_ai_text_extracted"] = True

        return fallback

    @staticmethod
    def _make_template_fallback(
        user_input: str, domain_hint: AgentDomain | None
    ) -> dict[str, Any]:
        """返回基础模板结构（不解析用户输入）"""
        # 这里借用 _template_fallback 的逻辑但作为独立静态方法
        domain = domain_hint or AgentGenerator._guess_domain(user_input)
        template = DOMAIN_TEMPLATES.get(domain, DOMAIN_TEMPLATES[AgentDomain.GENERAL])
        return {
            "meta": {
                "domain": domain.value, "domain_category": domain.value,
                "name": template.name_cn,
                "description": f"{template.name_cn} - 基于模板生成",
                "tags": [domain.value],
            },
            "architecture": {"mode": "simple", "max_steps": 15, "stop_token": "<FINAL_ANSWER>"},
            "system_prompt_modules": {
                "role_definition": f"你是一个{template.name_cn}。" + template.system_prompt_skeleton,
                "capability_declaration": "你可以使用以下工具：" + ", ".join(t.name for t in template.default_tools) if template.default_tools else "暂无特殊工具。",
                "output_format": "输出要求：\n- 需要行动时：<THOUGHT>推理过程</THOUGHT> <ACTION>工具调用</ACTION>\n- 给出答案时：<FINAL_ANSWER>完整回答</FINAL_ANSWER>\n- 失败/纠错时：<REFLECTION>失败原因+修正方案</REFLECTION>",
                "planning_instruction": "面对复杂问题，必须先拆解为步骤列表，再逐步执行。每一步执行后评估结果，决定下一步行动。",
                "reflection_instruction": "当连续2次行动无进展或收到明确错误时，必须输出反思：\n<REFLECTION>\n失败原因：[分析]\n修正方案：[新方案]\n</REFLECTION>",
                "safety_boundary": "严禁执行危险操作（如删除文件、修改系统配置、发送未经审核的消息）。涉及个人信息时必须脱敏处理。你提供的是参考建议，不构成法律/医疗/投资意见。",
            },
            "suggested_tools": [{"name": t.name, "description": t.description, "parameters": []} for t in template.default_tools],
            "suggested_knowledge": [k["source"] for k in template.knowledge_sources],
            "suggested_questions": template.suggested_questions,
            "memory_config": {"short_term_window": 10, "working_memory_keys": ["任务目标", "当前步骤", "中间结果"]},
            "_template_based": True,
        }


# ══════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════

def list_available_domains() -> list[dict]:
    """列出所有支持的领域模板"""
    result = []
    for domain, template in DOMAIN_TEMPLATES.items():
        result.append({
            "domain": domain.value,
            "name_cn": template.name_cn,
            "avatar": template.default_avatar,
            "tool_count": len(template.default_tools),
            "knowledge_count": len(template.knowledge_sources),
        })
    return result


def get_domain_template(domain: str) -> DomainTemplate | None:
    """获取指定领域的模板"""
    try:
        return DOMAIN_TEMPLATES.get(AgentDomain(domain))
    except ValueError:
        return None


__all__ = [
    "AgentDomain", "DomainTemplate", "DOMAIN_TEMPLATES",
    "AgentGenerator", "AgentGenerationResult",
    "list_available_domains", "get_domain_template",
]
