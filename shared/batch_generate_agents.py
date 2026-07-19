"""
AI Agent Hub — 批量生成领域 Agent YAML 文件

使用 AgentGenerator（模板模式）为所有领域生成完整的 Agent YAML。
LLM 模式下会调用 LLM 补充 system_prompt 细节，无 LLM 时使用领域模板。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from shared.agent_generator import (
    AgentGenerator, AgentDomain, AgentGenerationResult,
    list_available_domains, DOMAIN_TEMPLATES,
)

AGENTS_DIR = os.path.join(_ROOT, "agents")


def generate_all_domains(use_llm: bool = False):
    """
    为所有领域生成 Agent YAML。

    Args:
        use_llm: 是否使用 LLM 增强生成（需要 API Key）
    """
    gen = AgentGenerator()  # 无 LLM 时使用模板降级

    # 领域 → 用户描述映射
    domain_descriptions = {
        AgentDomain.LEGAL: "我要一个法律合同审查助手，能搜索法律法规数据库，检查合同条款合规性，提供法律风险分析",
        AgentDomain.FINANCE: "我要一个金融分析助手，能分析财务报表，评估投资风险，提供资产配置建议",
        AgentDomain.MEDICAL: "我要一个健康医疗顾问，能解读体检报告，提供循证健康建议，搜索医学文献",
        AgentDomain.EDUCATION: "我要一个教育辅导专家，能设计课程大纲，辅导学术写作，解释复杂概念",
        AgentDomain.MARKETING: "我要一个营销文案专家，能写广告文案和品牌故事，做SEO优化建议，分析用户画像",
        AgentDomain.ECOMMERCE: "我要一个电商运营助手，能做商品描述优化，分析竞品数据，制定促销策略",
        AgentDomain.CUSTOMER_SERVICE: "我要一个智能客服助手，能回答常见问题，处理用户投诉，创建和追踪工单",
        AgentDomain.CREATIVE: "我要一个创意内容设计师，能写品牌故事和slogan，生成社交媒体内容，提供视觉设计建议",
        AgentDomain.GENERAL: "我要一个通用AI助手，能回答各类知识问题，提供信息检索，进行多领域对话",
        AgentDomain.SECURITY: "我要一个网络安全专家，能分析安全漏洞，提供安全加固建议，解读安全合规标准",
        AgentDomain.DATA_SCIENCE: "我要一个数据分析师，能清洗和分析数据，做可视化建议，提供统计建模方案",
    }

    results = []

    for domain, description in domain_descriptions.items():
        if domain not in DOMAIN_TEMPLATES:
            continue

        template = DOMAIN_TEMPLATES[domain]
        filename = f"agent-{domain.value.replace('_', '-')}.yaml"
        filepath = os.path.join(AGENTS_DIR, filename)

        print(f"\n{'='*50}")
        print(f"  生成: {template.default_avatar} {template.name_cn} ({domain.value})")
        print(f"{'='*50}")

        # 生成
        result = gen.generate(
            user_input=description,
            domain_hint=domain,
        )

        if not result.success:
            print(f"  ✗ 生成失败: {result.error}")
            results.append((domain, False, result.error))
            continue

        # 写入文件
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(result.yaml_content)

            agent = result.agent_ir
            print(f"  ✓ 已保存: {filename}")
            print(f"    Tools: {len(agent.tools)}, Questions: {len(agent.suggested_questions)}")
            print(f"    YAML: {len(result.yaml_content)} chars")

            # 验证可加载
            try:
                from runner.loader import load_agent
                cfg = load_agent(filepath)
                assert cfg.meta.name
                print(f"  ✓ Loader 验证通过: {cfg.meta.name}")
            except Exception as e:
                print(f"  ⚠ Loader 验证失败: {e}")

            results.append((domain, True, filename))
        except Exception as e:
            print(f"  ✗ 写入失败: {e}")
            results.append((domain, False, str(e)))

    # ── 汇总 ──
    print(f"\n{'='*60}")
    print("  批量生成结果")
    print(f"{'='*60}")
    ok = sum(1 for _, s, _ in results if s)
    fail = sum(1 for _, s, _ in results if not s)
    print(f"  成功: {ok}/{len(results)}")
    if fail:
        print(f"  失败: {fail}")
        for domain, status, info in results:
            if not status:
                print(f"    ✗ {domain.value}: {info}")
    print(f"{'='*60}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="批量生成领域 Agent YAML")
    parser.add_argument("--llm", action="store_true", help="使用 LLM 增强生成")
    args = parser.parse_args()

    generate_all_domains(use_llm=args.llm)
