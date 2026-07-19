"""LumiWeave — exe 启动入口（PyInstaller打包用）
双击 lumiweave.exe 自动启动服务并打开浏览器
"""
import sys
import os
import time
import threading
import webbrowser
import subprocess


def main():
    """启动后端服务 + 自动打开浏览器"""

    # 1. 设置代理（从环境变量读取）
    proxy = os.getenv("LLM_PROXY", os.getenv("HTTP_PROXY", ""))
    if proxy:
        os.environ.setdefault("HTTP_PROXY", proxy)
        os.environ.setdefault("HTTPS_PROXY", proxy)

    # 2. 确定工作目录
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 3. 确保路径
    sys.path.insert(0, ".")
    sys.path.insert(0, "shared")
    sys.path.insert(0, "runner")
    sys.path.insert(0, "builder/backend")

    # 4. 启动后端
    port = int(os.getenv("LUMIWEAVE_PORT", "8000"))

    def start_server():
        import uvicorn
        uvicorn.run("main:app", host="127.0.0.1", port=port, log_level="info",
                    app_dir=os.path.join(os.getcwd(), "builder", "backend"))

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 5. 等待服务就绪
    print(f"\n  LumiWeave 启动中...")
    print(f"  浏览器即将打开 http://localhost:{port}\n")
    for _ in range(30):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{port}/api/health", timeout=1)
            break
        except Exception:
            time.sleep(1)

    # 6. 打开浏览器
    webbrowser.open(f"http://localhost:{port}")

    # 7. 保持运行
    print(f"  LumiWeave 已就绪！按 Ctrl+C 停止\n")
    try:
        while server_thread.is_alive():
            server_thread.join(1)
    except KeyboardInterrupt:
        print("\n  LumiWeave 已停止")


if __name__ == "__main__":
    main()
