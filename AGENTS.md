# Hivemind AGENTS.md

本文件是这个项目的默认规则入口。每次在本项目内对话时，AI 都必须先按本文件理解项目目标、文件组织、准入标准和验证方式。

## 项目说明

---
name: Hivemind
type: code
audience: 
category: 
target_users: 
north_star: 
north_star_target: 
owner: 
requester: 
version_start: 1.0.0
active_version: 1.0.0
goal: 
initialized: false
created_at: 2026-06-17T06:49:00.131Z
---

# Hivemind

> (待初始化补充：一句话核心目标)

## 项目概览

| 字段 | 内容 |
|------|------|
| 类型 | code |
| 品类 | （待补） |
| 目标用户 | （待补） |
| 北极星指标 | （待补） |
| 起始版本 | 1.0.0 |
| 当前版本 | 1.0.0 |
| 产品负责人 | （待补） |
| 需求方 | （待补） |
| 创建日期 | 2026-06-17 |

## Mission

（待补充：1-3 段说明要解决什么问题、解决到什么程度算成功、目标用户在什么场景下用。init 时由 PRD-init Skill 基于收集到的字段生成首段，鼓励用户/AI 后续展开。）

## Memory
_AI 在对话中通过 `remember_project_memory` 工具沉淀的项目级关键信息。每条 `- YYYY-MM-DD — xxx`。_
_本段记的是"跨需求都生效"的事实；需求级记忆请到对应 `docs/prd/<version>/.memory/`。_

### Decisions

### Facts

### Glossary

### Notes

## Iterations

> 项目历经的版本与彼此关系。每开启一个新版本目录，AI/用户在此追加一行。

| 版本 | 状态 | 启动日期 | 关键改动 / 与上一版的关系 |
|------|------|---------|------------------------|
| 1.0.0 | drafting | 2026-06-17 | 项目起点 |

## 工作规则

- 在写入或修改项目文件前，先确认目标文件属于本项目。
- 优先维护清晰、可复用、可追溯的资料和交付物，不把临时聊天噪声沉淀为长期文件。
- 需要新增规则时，直接编辑本文件；后续对话会默认加载最新规则。

## 文件组织

- `docs/`：长期文档、需求、方案、调研、评审和验收材料。
- `assets/`：图片、截图、视频、音频、表格、演示稿等素材。
- `src/` 或 `code/`：可运行代码、脚本、配置和工程实现。
- `scratch/`：短期草稿和临时分析；内容稳定后再迁移到长期目录。
- 文件命名应表达主题和版本，避免只用 `test`、`final`、`new` 这类不可追踪名称。

## 文件准入与标准化

- 写入 `docs/` 的文件必须包含明确标题、背景或目的、正文结论，以及必要的来源或上下文。
- 写入 `assets/` 的素材需要保留可识别名称；同一主题的素材应放在同一子目录。
- 写入 `src/` 或 `code/` 的代码必须说明运行方式、输入输出和依赖条件。
- 从聊天沉淀出的内容需要去掉寒暄、重复和过程噪声，保留可复用的信息结构。

## 索引与渐进式加载

- 本文件维护 1~2 级轻量索引，帮助 AI 先判断需要读取哪些目录和文件。
- 新增或重组重要文件后，应更新下方索引；不要把全文复制进索引。
- 回答项目问题时，先阅读本文件，再按索引渐进式读取相关文件。

### 文件索引

- `AGENTS.md`：项目规则、文件组织和索引。

## 历史迁移记录

- Migrated from: PROJECT.md
- PROJECT.md sha256: cd8b18ca35da442884fbb6d82d1a4c02d06749bb26f13402376d17da57cc14c0
- Legacy files are preserved on disk for auditability; runtime rules should use this AGENTS.md.
- Generated at: 2026-06-27T13:35:04.595Z
