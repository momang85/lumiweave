"""
AI Agent Hub — CLI 入口

用法:
    # 指定 Agent 文件启动
    python cli.py ../agents/python-backend.yaml

    # 交互式选择 Agent
    python cli.py

    # 查看 Agent 信息
    python cli.py ../agents/python-backend.yaml --info
"""

from __future__ import annotations

import argparse
import os
import sys

# 确保 runner 包可导入（从上级目录运行时）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loader import load_agent, list_available_agents, LoadError
from runner import AgentRunner

# ── 尝试导入 Rich，不支持时降级 ──
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from rich.table import Table
    from rich import box

    console = Console()
    _RICH = True
except ImportError:
    console = None
    _RICH = False


# ──────────────────────────────────────────────
# 格式化输出辅助
# ──────────────────────────────────────────────

def cprint(text: str, style: str = "", end: str = "\n"):
    """条件 Rich 输出"""
    if _RICH and console:
        console.print(text, style=style, end=end)
    else:
        print(text, end=end)


def print_panel(text: str, title: str = "", style: str = ""):
    """条件 Rich Panel"""
    if _RICH:
        console.print(Panel(text.strip(), title=title, border_style=style))
    else:
        if title:
            print(f"── {title} ──")
        print(text.strip())
        print()


def print_table(headers: list[str], rows: list[list[str]], title: str = ""):
    """条件 Rich Table"""
    if _RICH:
        table = Table(title=title, box=box.ROUNDED)
        for h in headers:
            table.add_column(h, style="cyan" if headers.index(h) == 0 else "")
        for row in rows:
            table.add_row(*row)
        console.print(table)
    else:
        if title:
            print(f"\n── {title} ──")
        for row in rows:
            print(f"  {'  |  '.join(row)}")
        print()


# ──────────────────────────────────────────────
# 交互式聊天循环
# ──────────────────────────────────────────────

def interactive_chat(runner: AgentRunner):
    """进入交互式对话循环"""

    # ── 欢迎界面 ──
    print_panel(
        runner.welcome_message,
        title=f"{runner.agent_avatar}  {runner.agent_name}",
        style="bold green",
    )

    # 推荐问题
    if runner.suggested_questions:
        print_table(
            ["#", "推荐问题（输入编号快速提问）"],
            [[str(i + 1), q] for i, q in enumerate(runner.suggested_questions)],
            title="💡 快速开始",
        )

    # 操作提示
    cprint("输入消息开始对话，或输入 " +
           ("[/bold cyan]/help[/] " if _RICH else "/help ") +
           "查看命令列表", style="dim")
    cprint("─" * 60, style="dim")

    _chat_loop(runner)


def _chat_loop(runner: AgentRunner):
    """对话主循环"""
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            cprint("\nBye!", style="bold yellow")
            break

        if not user_input:
            continue

        # ── 处理斜杠命令 ──
        if user_input.startswith("/"):
            handled = _handle_command(user_input, runner)
            if not handled:
                break
            continue

        # ── 处理推荐问题快捷输入 ──
        if user_input.isdigit():
            idx = int(user_input) - 1
            if 0 <= idx < len(runner.suggested_questions):
                user_input = runner.suggested_questions[idx]
                cprint(f"已选择: {user_input}", style="dim italic")

        # ── 调用 Agent ──
        try:
            cprint("⏳ 思考中...", style="dim", end="\r")
            reply = runner.chat(user_input)
            # 清除"思考中"
            cprint(" " * 20, end="\r")

            cprint(f"{runner.agent_avatar} Agent: ", style="bold green", end="")
            if _RICH:
                console.print(Markdown(reply))
            else:
                print(reply)

            # 非 Mock 模式显示 Token 消耗
            if not runner.llm.is_mock:
                cprint(
                    f"   [本次消耗 ~{runner.llm.chat.__self__.chat} tokens]",
                    style="dim"
                )

            cprint("─" * 60, style="dim")

        except Exception as e:
            cprint(f"[ERROR] {e}", style="bold red")


def _handle_command(cmd: str, runner: AgentRunner) -> bool:
    """
    处理斜杠命令。
    Returns: True 继续循环，False 退出
    """
    parts = cmd.split(maxsplit=1)
    command = parts[0].lower()

    if command in ("/exit", "/quit", "/q"):
        cprint("Bye!", style="bold yellow")
        return False

    elif command == "/help":
        _show_help()
    elif command == "/reset":
        runner.reset()
        cprint("[OK] 对话已重置，上下文已清空", style="bold green")
    elif command == "/history":
        summary = runner.get_history_summary()
        print_panel(summary, title="📋 对话历史", style="blue")
    elif command == "/tools":
        tools = runner.list_tools()
        if tools:
            print_table(
                ["工具名", "描述", "类型"],
                [[t["name"], t["description"], t["type"]] for t in tools],
                title="🔧 可用工具",
            )
        else:
            cprint("当前 Agent 未定义任何工具", style="yellow")
    elif command == "/info":
        _show_agent_info(runner)
    elif command == "/suggestions":
        if runner.suggested_questions:
            print_table(
                ["#", "推荐问题"],
                [[str(i + 1), q] for i, q in enumerate(runner.suggested_questions)],
                title="💡 推荐问题",
            )
        else:
            cprint("当前 Agent 无推荐问题", style="yellow")
    else:
        cprint(f"未知命令: {command}，输入 /help 查看可用命令", style="yellow")

    return True


def _show_help():
    commands = [
        ("/help", "显示此帮助"),
        ("/info", "查看 Agent 详细信息"),
        ("/tools", "列出 Agent 的可用工具"),
        ("/suggestions", "显示推荐问题"),
        ("/reset", "重置对话上下文"),
        ("/history", "查看对话历史摘要"),
        ("/exit, /quit, /q", "退出 Runner"),
        ("数字 (1/2/3...)", "快速选择推荐问题"),
    ]
    print_table(
        ["命令", "说明"],
        commands,
        title="📖 可用命令",
    )


def _show_agent_info(runner: AgentRunner):
    cfg = runner.config
    info_lines = [
        f"ID:          {cfg.meta.id}",
        f"名称:        {cfg.meta.name}",
        f"版本:        {cfg.meta.version}",
        f"作者:        {cfg.meta.author}",
        f"描述:        {cfg.meta.description}",
        f"标签:        {', '.join(cfg.meta.tags)}",
        f"许可证:      {cfg.meta.license}",
        f"模型:        {cfg.model.model_name}",
        f"Provider:    {cfg.model.provider}",
        f"降级:        {cfg.model.fallback or '(无)'}",
        f"Temperature: {cfg.model.parameters.temperature}",
        f"Max Tokens:  {cfg.model.parameters.max_tokens}",
        f"运行时语言:  {cfg.runtime.language}",
        f"工具数量:    {len(cfg.tools)}",
        f"知识源数量:  {len(cfg.knowledge)}",
        f"LLM 模式:    {'Mock (演示)' if runner.llm.is_mock else 'OpenAI (云端)'}",
    ]
    print("\n".join(info_lines))
    print()


# ──────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI Agent Hub Runner — 加载并运行 AI Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py agents/python-backend.yaml
  python cli.py agents/frontend-react.yaml
  python cli.py                      # 交互式选择
  python cli.py agents/python-backend.yaml --info  # 仅查看信息
        """,
    )
    parser.add_argument(
        "agent_file",
        nargs="?",
        help="Agent YAML 文件路径（不指定则交互式选择）",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="仅显示 Agent 信息，不进入对话",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用 Agent",
    )

    args = parser.parse_args()

    # ── 列出所有 Agent ──
    if args.list:
        agents = list_available_agents(
            os.path.join(os.path.dirname(__file__), "..", "agents")
        )
        if agents:
            rows = []
            for p in agents:
                try:
                    cfg = load_agent(p)
                    rows.append([p.name, cfg.meta.name, cfg.meta.description[:50]])
                except LoadError:
                    rows.append([p.name, "(加载失败)", ""])
            print_table(["文件", "Agent 名称", "描述"], rows, title="可用 Agent 列表")
        else:
            print("未找到 Agent 文件")
        return

    # ── 确定 Agent 文件 ──
    agent_path = args.agent_file

    if not agent_path:
        # 交互式选择
        agents_dir = os.path.join(os.path.dirname(__file__), "..", "agents")
        agents = list_available_agents(agents_dir)

        if not agents:
            print("[ERROR] 未找到任何 Agent 文件")
            sys.exit(1)

        print_table(
            ["#", "Agent 名称", "描述"],
            [
                [str(i + 1), load_agent(p).meta.name,
                 load_agent(p).meta.description[:60]]
                for i, p in enumerate(agents)
            ],
            title="请选择 Agent",
        )

        try:
            choice = input("输入编号 (1-{})：".format(len(agents))).strip()
            idx = int(choice) - 1
            if idx < 0 or idx >= len(agents):
                print("无效选择")
                sys.exit(1)
            agent_path = str(agents[idx])
        except (ValueError, EOFError, KeyboardInterrupt):
            print("\n已取消")
            sys.exit(0)

    # ── 加载 Agent ──
    try:
        runner = AgentRunner(agent_path)
    except LoadError as e:
        print(f"[ERROR] 加载失败: {e}")
        sys.exit(1)

    # ── 模式分支 ──
    if args.info:
        _show_agent_info(runner)
    else:
        interactive_chat(runner)


if __name__ == "__main__":
    main()
