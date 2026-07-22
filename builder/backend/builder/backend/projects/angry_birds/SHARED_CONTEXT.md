# Shared Context

## api_fields

# Angry Birds Game - 文件接口约定

## main.py
- 游戏主入口
- Pygame初始化、窗口创建、主循环
- 事件处理（鼠标拖拽发射、ESC退出）

## game.py
- 游戏核心逻辑
- 类：Bird, Pig, Block, Game
- 方法：发射小鸟、碰撞检测、计分、关卡管理

## physics.py
- 物理引擎
- 重力模拟、碰撞响应、弹射计算
- 类：PhysicsEngine

## requirements.txt
- pygame>=2.0.0

## 数据格式约定
- Bird: {x, y, vx, vy, radius, color, is_fired}
- Pig: {x, y, radius, health}
- Block: {x, y, width, height, health, type}
- 坐标系统：左上角为(0,0)，x向右增加，y向下增加

