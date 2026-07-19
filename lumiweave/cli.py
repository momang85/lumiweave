"""LumiWeave — AI Agent协作工作台"""
import sys
import os


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h"):
        print(__doc__)
        print(f"""
用法:
  lumiweave start             启动工作台 (http://localhost:8000)
  lumiweave start --port 8080 指定端口
  lumiweave run "做一个博客"   命令行运行任务
  lumiweave templates          查看内置项目模板
  lumiweave version            版本号

部署方式:
  pip install lumiweave         # pip 安装
  docker compose up -d          # Docker 一键启动
  lumiweave.exe                 # 双击即用 (Windows)
""")
        return

    cmd = args[0]

    if cmd == "start":
        port = "8000"
        for i, a in enumerate(args):
            if a == "--port" and i + 1 < len(args):
                port = args[i + 1]
        print(f"  LumiWeave 启动中...")
        print(f"  浏览器打开: http://localhost:{port}")
        _patch_sys_path()
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=int(port), log_level="info",
                    app_dir=os.path.join(os.path.dirname(__file__), "..", "builder", "backend"))

    elif cmd == "run":
        task = args[1] if len(args) > 1 else ""
        if not task:
            print("请提供任务描述: lumiweave run '做一个博客网站'")
            return
        print(f"  任务: {task}")
        print("  此功能开发中。请使用 lumiweave start 打开Web界面操作。")

    elif cmd == "templates":
        print("  内置项目模板:")
        for name, desc in [
            ("博客系统", "Markdown博客、文章CRUD、标签"),
            ("Todo应用", "CRUD、状态筛选、拖拽排序"),
            ("股票监控", "实时行情、异常警报、图表"),
            ("电商平台", "商品管理、购物车、订单"),
            ("知识库", "文档上传、RAG检索、问答"),
            ("聊天应用", "WebSocket、多房间"),
            ("API网关", "路由转发、限流、日志"),
            ("数据看板", "图表仪表盘、数据筛选"),
            ("爬虫系统", "定时抓取、清洗、通知"),
            ("表单收集", "动态表单、提交管理、CSV"),
        ]:
            print(f"    {name:12s} {desc}")

    elif cmd == "version":
        print("lumiweave v0.4.0")

    else:
        print(f"未知命令: {cmd}，lumiweave --help 查看帮助")


def _patch_sys_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for sub in ["shared", "runner", "builder/backend"]:
        p = os.path.join(root, sub)
        if p not in sys.path:
            sys.path.insert(0, p)
