# Shared Context

## api_fields

# 计算器项目接口约定

## 文件结构
- `projects/calc8/frontend/index.html` - 主页面
- `projects/calc8/frontend/style.css` - 样式文件
- `projects/calc8/frontend/app.js` - JavaScript逻辑

## 功能说明
- 支持基本运算：加(+)、减(-)、乘(×)、除(÷)、取模(%)
- 支持清除(AC)、删除(DEL)功能
- 支持键盘输入
- 显示屏显示当前输入和之前的运算

## 数据格式
- 数字：字符串格式，支持小数
- 运算符：字符串格式 (+, -, ×, ÷, %)
- 操作：字符串格式 (clear, delete, calculate)

## 类定义
- Calculator类：包含所有计算逻辑
  - appendNumber(number) - 添加数字
  - chooseOperation(operation) - 选择运算符
  - compute() - 执行计算
  - clear() - 清除所有
  - delete() - 删除最后一位
  - updateDisplay() - 更新显示

