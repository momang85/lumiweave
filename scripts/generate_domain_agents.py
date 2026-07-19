"""
AI Agent Hub — 批量生成领域 Agent YAML

使用领域模板和 LLM 生成完整的 Agent 定义文件。
"""

import sys, os, yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.agent_generator import AgentGenerator, AgentDomain, DOMAIN_TEMPLATES
from shared.ir_models import ProviderType
from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent / "agents"

# 尝试创建 LLM adapter（可选，无 API Key 也能用模板降级）
adapter = None
for env_var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
    key = os.getenv(env_var)
    if key:
        try:
            from shared.adapters.openai_adapter import OpenAIAdapter
            from shared.ir_models import ProviderConfig
            adapter = OpenAIAdapter(ProviderConfig(
                provider=ProviderType.OPENAI, model="gpt-4o-mini", api_key=key,
            ))
            print(f"LLM adapter: {env_var}")
            break
        except Exception as e:
            print(f"LLM init failed: {e}")

gen = AgentGenerator(llm_adapter=adapter)

# 领域列表（排除已有编程技术栈的）
DOMAIN_INPUTS = {
    AgentDomain.LEGAL: "我要一个专业的法律顾问 AI，能解答法律咨询、审查合同条款、检索法律法规、提供合规建议。精通民法典、合同法、劳动法、公司法。回答时引用具体法条。",
    AgentDomain.FINANCE: "我要一个金融分析 AI，能分析财务报表（利润表/资产负债表/现金流）、评估投资组合风险、提供资产配置建议。熟悉中国A股、港股、美股市场。基于数据驱动给出结论。",
    AgentDomain.MEDICAL: "我要一个健康顾问 AI，基于循证医学提供健康科普。能解读体检报告指标、介绍常见疾病预防知识、回答药物相互作用问题。明确标注你是科普而非诊断，急症建议就医。",
    AgentDomain.EDUCATION: "我要一个教育导师 AI，能设计课程教学大纲、辅导学习方法（费曼/间隔重复/主动召回）、批改作业并给出建设性反馈、推荐学习资源。因材施教，用通俗语言解释复杂概念。",
    AgentDomain.MARKETING: "我要一个营销策略专家 AI，能写多平台广告文案（微信/小红书/抖音/知乎）、做SEO关键词分析、制定内容营销计划、分析用户画像。熟悉AARRR增长模型和私域运营。",
    AgentDomain.CUSTOMER_SERVICE: "我要一个智能客服 AI，能处理用户咨询和投诉、分类并创建工单、调用常见问题库快速回答、礼貌耐心地处理情绪化用户。无法解决的问题明确告知并升级给人工。",
    AgentDomain.CREATIVE: "我要一个创意内容创作 AI，能写品牌故事、广告语slogan、社交媒体种草笔记、视频脚本大纲、活动策划方案。风格多样化（文艺/幽默/温情/专业），按需求切换。",
    AgentDomain.SECURITY: "我要一个网络安全专家 AI，能进行代码安全审计、识别OWASP Top 10漏洞、提供安全加固建议、分析攻击向量。熟悉Web安全、API安全、云安全。给出可操作的安全方案。",
    AgentDomain.GENERAL: "我要一个通用AI助手，能回答各类知识问题、帮忙撰写文档、做总结归纳、提供生活建议。知识面广泛，回答准确且有建设性。",
}

generated = 0
for domain, user_input in DOMAIN_INPUTS.items():
    template = DOMAIN_TEMPLATES.get(domain)
    if not template:
        continue

    output_file = AGENTS_DIR / f"{domain.value}-assistant.yaml"
    if output_file.exists():
        print(f"  ⏭ 跳过（已存在）: {output_file.name}")
        continue

    print(f"  生成中: {template.default_avatar} {template.name_cn}...", end=" ", flush=True)
    try:
        result = gen.generate(user_input, domain_hint=domain)
        if result.success and result.yaml_content:
            output_file.write_text(result.yaml_content, encoding="utf-8")
            generated += 1
            print("OK")
        else:
            print(f"FAIL: {result.error}")
    except Exception as e:
        print(f"FAIL: {e}")

print(f"\n已生成 {generated} 个新 Agent YAML")
