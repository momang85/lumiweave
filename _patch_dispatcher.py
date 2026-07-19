import os

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shared', 'agent_dispatcher.py')
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_tools = '''            _injected_file_tools = [
                {
                    "name": "write_file",
                    "description": "写入文件内容。路径相对于项目根目录。",
                    "type": "function",
                    "parameters": [
                        {"name": "path", "type": "string", "required": True, "description": "文件相对路径"},
                        {"name": "content", "type": "string", "required": True, "description": "文件内容"},
                        {"name": "overwrite", "type": "boolean", "required": False, "description": "是否覆盖"},
                    ],
                },
                {
                    "name": "read_file",
                    "description": "读取文件。可读自己或其他Agent写的文件，查看接口格式/字段定义。",
                    "type": "function",
                    "parameters": [
                        {"name": "path", "type": "string", "required": True, "description": "文件相对路径"},
                    ],
                },
                {
                    "name": "list_dir",
                    "description": "列出目录内容。查看其他Agent创建了哪些文件。",
                    "type": "function",
                    "parameters": [
                        {"name": "path", "type": "string", "required": True, "description": "目录相对路径"},
                    ],
                },
                {
                    "name": "search_file",
                    "description": "搜索文件。查找其他Agent的生成文件（如 pattern='*.py' 找后端代码）。",
                    "type": "function",
                    "parameters": [
                        {"name": "pattern", "type": "string", "required": True, "description": "文件名通配符"},
                        {"name": "directory", "type": "string", "required": False, "description": "搜索目录"},
                    ],
                },
                {
                    "name": "send_to_agent",
                    "description": "给另一个Agent发消息并获取回复。用于确认接口格式、询问字段含义。",
                    "type": "function",
                    "parameters": [
                        {"name": "target_agent_id", "type": "string", "required": True, "description": "目标Agent的ID"},
                        {"name": "message", "type": "string", "required": True, "description": "要发送的消息/问题"},
                    ],
                },
            ]
'''

# Find and replace: lines 448-475 (0-indexed: 447-474)
new_lines = lines[:447] + [new_tools] + lines[475:]
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Patched agent_dispatcher.py with 5 injected tools (including send_to_agent + search_file)')
