<!--
已知限制清单（Known Limitations）
维护约定：任何被识别到的解析/兼容/能力边界都必须登记于此，随里程碑维护；
禁止只遇到不记录（防止未来重复踩坑）。任务事实源见 PLAN.md。
-->

# 已知限制清单

> 维护者：朱世航 ｜ 最后更新：2026-08-13

| 编号 | 里程碑 | 限制 | 影响 | 规避/备注 |
|------|--------|------|------|-----------|
| L-001 | M2 | sqlglot 对复杂 HiveQL（嵌套 UDTF、某些 lateral view、专有函数）支持有限 | ER/校验覆盖度 | 只承诺 DDL 子集；预规范化后解析；复杂语句登记待扩展 |
| L-002 | M2 | Hive 外部表/分区表等方言特性的语义差异 | 解析结果与真实库不完全等价 | 以"参考性 ER/校验"定位，标注方言；L2 真实库校验为准 |
| L-003 | M3 | 企业微信文档/微盘 API 权限与成熟度限制 | 企微存储功能受限 | DocStorage 抽象隔离；备选"本地为主 + 企微机器人通知" |
| L-004 | M4 | 需系统安装 svn 客户端（Python 无成熟纯库） | svn 功能依赖外部命令 | 当前用 LocalFakeSvnClient 模拟；接入真实 CLI 时文档明确要求安装，Windows 提示 TortoiseSVN CLI |
| L-005 | M6 | 原生依赖（sqlite-vec）在不同平台存在兼容风险 | 部署兼容 | VectorStore 接口可切 Redis/pgvector；uv 本地安装规避；2026-08-13 已移除 chromadb（Windows+Py3.12 Rust 绑定崩溃） |
| L-006 | M3 | LLM 服务不可用时部分能力受限 | kb_ask/mindmap 降级 | 无 Key 时 kb_search/标题解析降级路径可用；Embedding 缓存降本 |
| L-007 | M4 | SQLite 默认不启用外键约束（PRAGMA foreign_keys=ON 未开） | 级联删除不自动生效 | project_remove 手动级联删除 tasks/milestones；后续迁移可开启 |
| L-008 | M5 | mindmap_from_doc 的 LLM 提炼依赖 llm_api_key，且真实调用走标准库 urllib（非 SDK） | 无 Key 时仅标题降级；高级能力受限 | 无 Key 自动降级按 Markdown 标题层级；OpenAI SDK/httpx 统一留 M7 |
| L-009 | M5 | OPML 导出为 XMind/FreeMind 通用 outline 结构，未含脑图特有样式（图标/优先级/备注） | 导入后样式丢失 | 以大纲层级为准；样式增强待后续扩展 |
| L-010 | M5 | Mermaid mindmap 解析支持常见形状（(( ))等）与缩进层级，超集语法（含 id 前缀外的形状装饰）不保证 | 复杂 mermaid 可能拒收 | 以"标题+层级"语义为主；校验失败返回可读错误 |

> 新增限制必须追加行并引用触发里程碑。
