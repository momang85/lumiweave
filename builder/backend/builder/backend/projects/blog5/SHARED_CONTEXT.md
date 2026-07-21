# Shared Context

## api_fields

# 博客系统 API 接口字段约定

## 文章相关 (Articles)

### 创建文章 POST /api/articles/
请求体 (ArticleCreate):
- title (string, 必填): 文章标题，最大200字符
- content (string, 必填): 文章正文
- summary (string, 可选): 文章摘要，最大500字符，默认空
- author (string, 可选): 作者名，默认"Anonymous"

响应 (ArticleResponse):
- id (int): 文章ID
- title (string): 文章标题
- content (string): 文章正文
- summary (string): 文章摘要
- author (string): 作者名
- created_at (datetime): 创建时间
- updated_at (datetime): 更新时间

### 获取文章列表 GET /api/articles/
查询参数:
- page (int, 默认1): 页码，从1开始
- page_size (int, 默认10, 范围1-100): 每页数量
- search (string, 可选): 搜索关键词（匹配标题或内容）

响应: List[ArticleResponse]

### 获取单篇文章 GET /api/articles/{article_id}
路径参数:
- article_id (int): 文章ID

响应: ArticleResponse

### 更新文章 PUT /api/articles/{article_id}
路径参数:
- article_id (int): 文章ID

请求体 (ArticleUpdate):
- title (string, 可选): 新标题
- content (string, 可选): 新正文
- summary (string, 可选): 新摘要
- author (string, 可选): 新作者名

响应: ArticleResponse

### 删除文章 DELETE /api/articles/{article_id}
路径参数:
- article_id (int): 文章ID

响应: {"message": "文章删除成功"}

## 评论相关 (Comments)

### 创建评论 POST /api/articles/{article_id}/comments/
路径参数:
- article_id (int): 文章ID

请求体 (CommentCreate):
- author (string, 必填): 评论者姓名
- content (string, 必填): 评论内容

响应 (CommentResponse):
- id (int): 评论ID
- article_id (int): 关联文章ID
- author (string): 评论者姓名
- content (string): 评论内容
- created_at (datetime): 创建时间

### 获取评论列表 GET /api/articles/{article_id}/comments/
路径参数:
- article_id (int): 文章ID

响应: List[CommentResponse]（按创建时间倒序）

### 更新评论 PUT /api/comments/{comment_id}
路径参数:
- comment_id (int): 评论ID

请求体 (CommentUpdate):
- author (string, 可选): 新作者名
- content (string, 可选): 新评论内容

响应: CommentResponse

### 删除评论 DELETE /api/comments/{comment_id}
路径参数:
- comment_id (int): 评论ID

响应: {"message": "评论删除成功"}

## 系统相关 (System)

### 健康检查 GET /api/health
响应: {"status": "ok", "message": "博客系统运行正常"}

## 错误响应
- 404: {"detail": "文章不存在"} 或 {"detail": "评论不存在"}
- 422: 请求体验证错误

## 分页说明
- 使用 page 和 page_size 参数实现分页
- 返回所有匹配的记录，前端自行处理分页显示
- 建议 page_size 不超过100

## 搜索说明
- 搜索关键词同时匹配文章标题和内容
- 使用 LIKE 模糊匹配（包含关键词即可）

## 时间格式
- 所有时间字段使用 ISO 8601 格式：YYYY-MM-DDTHH:MM:SS

