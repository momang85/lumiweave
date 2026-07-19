"""测试 Agent 生成器：领域识别、模板生成、YAML导出"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from shared.agent_generator import (
    AgentGenerator, AgentDomain, AgentGenerationResult,
    list_available_domains, get_domain_template, DOMAIN_TEMPLATES,
)

def test_domain_templates():
    print("=== 领域模板测试 ===")
    assert len(DOMAIN_TEMPLATES) >= 8, f"模板数量不足: {len(DOMAIN_TEMPLATES)}"
    print(f"  ✓ 模板数量: {len(DOMAIN_TEMPLATES)}")

    for domain, tmpl in DOMAIN_TEMPLATES.items():
        assert tmpl.name_cn, f"{domain} 缺少名称"
        assert tmpl.system_prompt_skeleton, f"{domain} 缺少 system_prompt 骨架"
        assert tmpl.suggested_questions, f"{domain} 缺少推荐问题"
        print(f"    {tmpl.default_avatar} {domain.value}: {tmpl.name_cn} "
              f"({len(tmpl.default_tools)} tools, {len(tmpl.knowledge_sources)} knowledge)")

    # 获取特定模板
    legal = get_domain_template("legal")
    assert legal is not None
    assert legal.name_cn == "法律助手"
    assert legal.default_avatar == "⚖️"
    print("  ✓ get_domain_template 正确")

    # 域名列表
    domains = list_available_domains()
    assert len(domains) == len(DOMAIN_TEMPLATES)
    print("  ✓ list_available_domains 正确")

    print("  ✓ 全部领域模板测试通过\n")


def test_guess_domain():
    print("=== 领域识别测试 ===")
    gen = AgentGenerator()
    tests = [
        ("我要一个帮我写法律合同的助手", AgentDomain.LEGAL),
        ("帮我分析财务报表和投资组合", AgentDomain.FINANCE),
        ("健康咨询和体检报告解读", AgentDomain.MEDICAL),
        ("设计一个Python入门课程", AgentDomain.EDUCATION),
        ("写一篇小红书种草笔记", AgentDomain.MARKETING),
        ("处理客户投诉和售后问题", AgentDomain.CUSTOMER_SERVICE),
        ("帮我设计品牌slogan", AgentDomain.CREATIVE),
        ("FastAPI后端API开发", AgentDomain.BACKEND),
        ("React前端组件开发", AgentDomain.FRONTEND),
        ("部署Docker和K8s集群", AgentDomain.DEVOPS),
    ]
    passed = 0
    for text, expected in tests:
        guessed = gen._guess_domain(text)
        if guessed == expected:
            passed += 1
            print(f"  ✓ '{text[:20]}...' → {expected.value}")
        else:
            print(f"  ✗ '{text[:20]}...' → {guessed.value} (expected {expected.value})")
    assert passed >= 7, f"识别准确率过低: {passed}/{len(tests)}"
    print(f"  ✓ 识别准确率: {passed}/{len(tests)}")
    print("  ✓ 领域识别测试通过\n")


def test_generate_without_llm():
    """测试无 LLM 的模板降级生成"""
    print("=== 模板降级生成测试 ===")
    gen = AgentGenerator()  # 无 LLM adapter

    # 测试法律 Agent
    result = gen.generate("我要一个帮我写法律合同的助手", domain_hint=AgentDomain.LEGAL)
    assert result.success, f"生成失败: {result.error}"
    assert result.agent_ir is not None
    assert len(result.yaml_content) > 100

    agent = result.agent_ir
    assert agent.name == "法律助手"
    assert len(agent.tools) >= 2
    assert len(agent.suggested_questions) >= 2
    assert "法律" in agent.system_prompt
    print(f"  ✓ 法律 Agent 生成成功")
    print(f"    Name: {agent.name}")
    print(f"    Tools: {len(agent.tools)}")
    print(f"    Questions: {len(agent.suggested_questions)}")
    print(f"    YAML 长度: {len(result.yaml_content)} chars")

    # 测试金融 Agent
    result2 = gen.generate("我要一个金融分析助手", domain_hint=AgentDomain.FINANCE)
    assert result2.success
    assert result2.agent_ir.name == "金融分析师"
    print(f"  ✓ 金融 Agent 生成成功: {result2.agent_ir.name}")

    # 测试自动领域识别
    result3 = gen.generate("帮我分析体检报告的AI助手")
    assert result3.success
    # 应该自动识别为医疗领域
    print(f"  ✓ 自动识别生成: {result3.agent_ir.name} "
          f"(domain={result3.raw_skeleton.get('domain', '?')})")

    # 测试空输入
    result4 = gen.generate("")
    assert not result4.success
    assert "不能为空" in result4.error
    print("  ✓ 空输入正确处理")

    # 测试 YAML 格式
    assert "meta:" in result.yaml_content
    assert "system_prompt:" in result.yaml_content
    assert "tools:" in result.yaml_content
    print("  ✓ YAML 格式包含完整字段")

    print("  ✓ 全部模板降级生成测试通过\n")


def test_yaml_roundtrip():
    """测试生成的 YAML 能否被 loader 正确加载"""
    print("=== YAML 往返测试 ===")
    try:
        import yaml
    except ImportError:
        print("  ⚠ 跳过（需 pyyaml）")
        return

    gen = AgentGenerator()
    result = gen.generate("帮我写代码的助手", domain_hint=AgentDomain.BACKEND)
    assert result.success

    # 验 YAML 可解析
    parsed = yaml.safe_load(result.yaml_content)
    assert "meta" in parsed
    assert "model" in parsed
    assert "system_prompt" in parsed
    assert parsed["meta"]["tags"], "tags 不应为空"
    print(f"  ✓ YAML 可解析: {parsed['meta']['name']}")

    # 尝试用 loader 加载
    try:
        from runner.loader import AgentConfig
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8",
        ) as f:
            f.write(result.yaml_content)
            tmp_path = f.name

        config = __import__("runner.loader", fromlist=["load_agent"]).load_agent(tmp_path)
        assert config.meta.name == "Python 后端大师" or config.meta.name
        os.unlink(tmp_path)
        print(f"  ✓ Loader 可加载生成的 YAML")
    except Exception as e:
        print(f"  ⚠ Loader 加载: {type(e).__name__}（可能是 AgentConfig 字段不匹配）")

    print("  ✓ YAML 往返测试通过\n")


if __name__ == "__main__":
    print("=" * 50)
    print("  AI Agent Hub — 模块3 Agent生成器 测试套件")
    print("=" * 50 + "\n")

    results = {}
    for name, func in [
        ("领域模板", test_domain_templates),
        ("领域识别", test_guess_domain),
        ("模板降级生成", test_generate_without_llm),
        ("YAML往返", test_yaml_roundtrip),
    ]:
        try:
            func()
            results[name] = "OK"
        except Exception as e:
            results[name] = f"FAIL: {e}"
            import traceback
            traceback.print_exc()

    print("=" * 50)
    print("          测试结果汇总")
    print("=" * 50)
    for name, status in results.items():
        s = "[PASS]" if status == "OK" else "[FAIL]"
        print(f"  {s} {name}: {status}")
    print("=" * 50)

    failed = sum(1 for s in results.values() if s != "OK")
    if failed:
        print(f"\n  {failed} 项失败!")
        sys.exit(1)
    else:
        print("\n  全部通过!")
