# Shared Context

## api_fields

# Angry Birds 游戏模块接口约定

## 物理引擎 (physics.py)
- `PhysicsEngine`: 物理引擎类
  - `__init__()`: 初始化物理空间、重力设置
  - `update(dt)`: 更新物理世界状态
  - `check_collisions()`: 检测实体间碰撞
  - `add_entity(entity)`: 添加实体到物理世界
  - `remove_entity(entity)`: 从物理世界移除实体

## 实体类 (entities.py)
- `BaseEntity`: 基类
  - `__init__(x, y, width, height)`: 初始化位置、尺寸
  - `update(dt)`: 更新实体状态
  - `draw(surface)`: 绘制实体
  - `get_rect()`: 获取碰撞矩形
- `Bird(BaseEntity)`: 小鸟实体
  - `__init__(x, y)`: 初始化小鸟
  - `shoot(force, angle)`: 发射小鸟
  - `is_moving()`: 判断是否正在移动
- `Pig(BaseEntity)`: 猪实体
  - `__init__(x, y)`: 初始化猪
  - `is_destroyed()`: 判断是否被击倒
- `Block(BaseEntity)`: 障碍物方块
  - `__init__(x, y, width, height)`: 初始化方块
  - `health`: 方块生命值
- `Slingshot(BaseEntity)`: 弹弓
  - `__init__(x, y)`: 初始化弹弓位置
  - `drag(mouse_pos)`: 处理拖拽
  - `get_launch_vector()`: 获取发射向量

## 游戏管理 (game.py)
- `Game`: 游戏主管理类
  - `__init__()`: 初始化游戏状态
  - `update(dt)`: 更新游戏逻辑
  - `draw(surface)`: 绘制游戏画面
  - `handle_event(event)`: 处理用户输入
  - `next_level()`: 进入下一关
  - `reset_level()`: 重置当前关卡
  - `get_score()`: 获取当前分数
  - `get_level()`: 获取当前关卡号

## 主入口 (main.py)
- 初始化 Pygame
- 创建 Game 实例
- 主循环：事件处理→更新→绘制→刷新
- 退出机制

