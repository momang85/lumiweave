"""
AI Agent Hub — 内置模板市场数据

每个模板是一个完整的 AgentConfig 字典，可直接导入 Builder。
"""

BUILTIN_TEMPLATES = [
    {
        "id": "template-customer-service",
        "name": "智能客服机器人",
        "icon": "🎧",
        "category": "客服",
        "description": "7x24 小时自动解答用户问题，支持 FAQ 匹配和工单创建",
        "tags": ["客服", "FAQ", "自动化"],
        "system_prompt": (
            "你是一名专业的客服助手，负责解答用户关于公司产品的疑问。\n\n"
            "规则：\n"
            "1. 始终使用礼貌、耐心的语气\n"
            "2. 先理解用户问题，再给出解答\n"
            "3. 如果无法解决，引导用户创建工单\n"
            "4. 不要承诺超出权限范围的事情\n"
            "5. 结尾询问'还有其他问题吗？'"
        ),
        "model": {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "parameters": {"temperature": 0.5, "max_tokens": 2048},
        },
        "tools": [
            {
                "name": "search_faq",
                "description": "搜索常见问题库",
                "type": "function",
                "handler": "search_docs",
                "properties": {
                    "query": {"type": "string", "description": "用户问题关键词"},
                },
                "required": ["query"],
            },
            {
                "name": "create_ticket",
                "description": "创建工单转人工处理",
                "type": "function",
                "handler": "",
                "properties": {
                    "title": {"type": "string", "description": "工单标题"},
                    "description": {"type": "string", "description": "问题描述"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "default": "medium",
                    },
                },
                "required": ["title", "description"],
            },
        ],
        "suggested_questions": [
            "如何修改密码？",
            "订单怎么退款？",
            "产品什么时候发货？",
        ],
    },
    {
        "id": "template-code-assistant",
        "name": "代码助手",
        "icon": "💻",
        "category": "开发",
        "description": "帮你写代码、Debug、Review，支持 Python/JS/Go/Rust 等多语言",
        "tags": ["代码", "debug", "review", "多语言"],
        "system_prompt": (
            "你是一名资深软件工程师，精通多种编程语言。\n\n"
            "你的职责：\n"
            "1. 根据需求编写可运行的完整代码\n"
            "2. 解释代码逻辑和设计决策\n"
            "3. 指出潜在问题和优化方向\n"
            "4. 回答时使用对应语言的代码块格式"
        ),
        "model": {
            "provider": "openai",
            "model_name": "gpt-4o",
            "parameters": {"temperature": 0.3, "max_tokens": 4096},
        },
        "tools": [
            {
                "name": "run_code",
                "description": "执行代码并返回结果",
                "type": "function",
                "handler": "code_executor",
                "properties": {
                    "code": {"type": "string", "description": "要执行的代码"},
                },
                "required": ["code"],
                "timeout": 15,
            },
            {
                "name": "lint_code",
                "description": "检查代码语法和风格",
                "type": "function",
                "handler": "code_lint",
                "properties": {
                    "code": {"type": "string", "description": "要检查的代码"},
                    "language": {"type": "string", "default": "python"},
                },
                "required": ["code"],
            },
        ],
        "suggested_questions": [
            "帮我写一个 Python 快速排序",
            "这段 JavaScript 代码有什么问题？",
            "SQL 查询太慢怎么优化？",
        ],
    },
    {
        "id": "template-translator",
        "name": "多语言翻译官",
        "icon": "🌐",
        "category": "工具",
        "description": "专业翻译助手，支持中英日韩法德等 20+ 语言互译",
        "tags": ["翻译", "多语言", "本地化"],
        "system_prompt": (
            "你是一名专业翻译，精通中英日韩法德等语言。\n\n"
            "规则：\n"
            "1. 保持原文语义和风格\n"
            "2. 技术术语使用业界标准译法\n"
            "3. 提供直译 + 意译两个版本（如适用）\n"
            "4. 标注不确定的翻译"
        ),
        "model": {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "parameters": {"temperature": 0.3, "max_tokens": 4096},
        },
        "tools": [],
        "suggested_questions": [
            "把以下英文翻译成中文",
            "这段日文是什么意思？",
            "帮我把产品描述翻译成英文和法文",
        ],
    },
    {
        "id": "template-data-analyst",
        "name": "数据分析师",
        "icon": "📊",
        "category": "数据",
        "description": "帮你分析数据、生成图表建议、编写 SQL 和 Python 数据处理脚本",
        "tags": ["数据分析", "SQL", "Python", "可视化"],
        "system_prompt": (
            "你是一名数据分析师，擅长从数据中提取洞察。\n\n"
            "能力：\n"
            "1. 编写 SQL 查询提取数据\n"
            "2. 使用 Python/Pandas 进行数据处理\n"
            "3. 推荐合适的可视化图表类型\n"
            "4. 用通俗语言解释统计概念\n"
            "5. 给出可落地的业务建议"
        ),
        "model": {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "parameters": {"temperature": 0.3, "max_tokens": 4096},
        },
        "tools": [
            {
                "name": "run_code",
                "description": "执行数据处理代码",
                "type": "function",
                "handler": "code_executor",
                "properties": {
                    "code": {"type": "string", "description": "Python 数据处理代码"},
                },
                "required": ["code"],
                "timeout": 20,
            },
        ],
        "suggested_questions": [
            "帮我分析这份销售数据的趋势",
            "这个指标异常可能是什么原因？",
            "适合展示销售额变化的图表类型有哪些？",
        ],
    },
    {
        "id": "template-writer",
        "name": "文案写手",
        "icon": "✍️",
        "category": "内容",
        "description": "帮你撰写营销文案、公众号文章、产品介绍、周报等",
        "tags": ["写作", "文案", "营销", "内容创作"],
        "system_prompt": (
            "你是一名经验丰富的文案写手。\n\n"
            "风格：\n"
            "1. 清晰、简洁、有感染力\n"
            "2. 根据不同文体调整语气（正式/轻松/幽默）\n"
            "3. 使用数据增强说服力\n"
            "4. 提供 A/B 版本供选择"
        ),
        "model": {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "parameters": {"temperature": 0.8, "max_tokens": 4096},
        },
        "tools": [],
        "suggested_questions": [
            "帮我写一个新产品发布的公众号文章",
            "这个产品卖点怎么包装？",
            "帮我写一份周报",
        ],
    },
]
