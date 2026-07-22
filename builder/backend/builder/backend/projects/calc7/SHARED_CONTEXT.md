# Shared Context

## api_fields

# Web Calculator API 接口约定

## POST /api/calculate
请求体:
```json
{
  "expression": "5+3*2"  // 字符串格式的数学表达式
}
```
响应:
```json
{
  "success": true,
  "result": 11.0
}
```

## GET /api/history
查询参数:
- limit: int (可选，默认10) - 返回历史记录数量

响应:
```json
{
  "history": [
    {
      "expression": "5+3",
      "result": 8.0,
      "created_at": "2024-01-01 12:00:00"
    }
  ]
}
```

## GET /api/health
响应:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

## 数据库表结构
表名：calculations
- id: INTEGER PRIMARY KEY AUTOINCREMENT
- expression: TEXT NOT NULL (计算的表达式)
- result: REAL NOT NULL (计算结果)
- created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP

## 前端数据格式
- currentOperand: string - 当前输入的数字
- previousOperand: string - 前一个操作数
- operation: string | null - 当前运算符
- shouldResetScreen: boolean - 是否重置屏幕

