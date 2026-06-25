# Hivemind 项目目录架构设计

> 本文档定义 Hivemind 的工程目录结构与关注点边界。所有新增文件应能在本文档找到归属;
> 若找不到,先更新本文档再落地代码。

## 0. 设计原则

1. **src-layout(源码隔离)**:真正的包放在 `src/hivemind/` 下,避免"当前目录恰好能 import"
   的假象,保证测试运行的是已安装的包,杜绝隐式相对路径依赖。
2. **关注点分层**:代码 / 配置 / 资源 / 环境初始化 / 部署 / 运行时状态 各占独立顶层目录,
   彼此不混放。一眼能分清"哪些进版本库、哪些是机器本地状态"。
3. **配置三层叠加**:打包默认值 → 部署配置文件 → 环境变量/密钥。代码永不硬编码白名单、端口、密钥。
4. **运行时状态外置且 gitignore**:日志、PID、持久化注册表快照、pipe-pane 落盘全部进 `var/`,
   与源码彻底隔离,删了不影响代码。
5. **包内单向依赖**:`tmux / dingtalk / hooks`(基础设施层)→ `core`(领域层)→ `app`(编排层),
   依赖只能从外向内,core 不反向依赖任何 I/O 适配器。
6. **资源就近打包**:运行时必需的模板(钉钉卡片、hook 脚本、tmux profile)作为包资源随包走,
   用 `importlib.resources` 读取,保证以任意 cwd / launchd 启动都能定位。

---

## 1. 顶层目录树

```
hivemind/
├── src/
│   └── hivemind/                 # ① 代码（唯一可 import 的包）
│       ├── __init__.py
│       ├── __main__.py           # python -m hivemind 入口
│       ├── app.py                # 组合根：装配各子系统 + asyncio 主循环
│       ├── cli.py                # 命令行参数 / 子命令 (run / doctor / version)
│       │
│       ├── config/               # 配置加载与校验（代码侧）
│       │   ├── __init__.py
│       │   ├── schema.py         # pydantic Settings 模型（类型+默认+校验）
│       │   └── loader.py         # 三层叠加：defaults.toml → 用户 toml → env
│       │
│       ├── core/                 # 领域层（无 I/O，纯逻辑，最易测）
│       │   ├── __init__.py
│       │   ├── models.py         # Terminal / TermState / Command / Event
│       │   ├── registry.py       # TerminalManager：终端生命周期 + 状态表
│       │   ├── router.py         # 寻址语法解析（@name /spawn /y …）+ 会话粘性
│       │   ├── queue.py          # 每终端命令队列（BUSY 时排队，防竞态）
│       │   └── errors.py         # 领域异常
│       │
│       ├── tmux/                 # 基础设施：tmux 适配器
│       │   ├── __init__.py
│       │   ├── client.py         # 薄封装：new/kill/list/send-keys/capture/pipe-pane
│       │   └── forwarder.py      # 安全注入序列：Esc 清场 → -l 文本 → 单发 Enter
│       │
│       ├── monitor/             # 基础设施：状态监控
│       │   ├── __init__.py
│       │   ├── detector.py       # detect_state：从 pane 文本判定状态（版本敏感，集中维护）
│       │   ├── differ.py         # 抓屏增量提取（去重、剥 UI 噪声）
│       │   └── poller.py         # 轮询循环：变化即上报 Bridge
│       │
│       ├── dingtalk/            # 基础设施：钉钉适配器
│       │   ├── __init__.py
│       │   ├── client.py         # Stream 出站长连接封装 + 重连
│       │   ├── handlers.py       # 收到消息 → 交给 router
│       │   └── renderer.py       # 渲染 Markdown / 交互卡片
│       │
│       ├── hooks/              # 基础设施：Claude hooks 事件接入（M3）
│       │   ├── __init__.py
│       │   ├── server.py         # 本地 HTTP 端点，仅听 127.0.0.1
│       │   └── events.py         # Stop / Notification / PostToolUse 事件模型
│       │
│       ├── resources/         # 运行时必需的打包资源（随 wheel 走）
│       │   ├── defaults.toml     # 配置默认值（唯一权威默认）
│       │   ├── dingtalk/         #   钉钉卡片 / Markdown 模板
│       │   ├── hooks/            #   注入给 Claude 的 hook 脚本模板
│       │   └── tmux/             #   tmux session profile / 启动模板
│       │
│       └── utils/             # 跨层通用工具（日志、时间、重试）
│           ├── __init__.py
│           └── logging.py
│
├── config/                       # ② 配置（部署侧，机器本地，可改不进核心逻辑）
│   ├── hivemind.toml             # 用户配置：终端清单、轮询间隔、端口…（可入库做样例）
│   └── hivemind.local.toml       # 本机覆盖（gitignore，含环境特定值）
│
├── assets/                       # ③ 资源（开发/文档用静态物，非运行时必需）
│   ├── diagrams/                 # 架构图源文件 / 导出图
│   └── screenshots/              # 钉钉交互截图、状态机示意
│
├── scripts/                      # ④ 环境初始化 & 运维脚本（一次性/手动）
│   ├── bootstrap.sh              # 装 tmux/claude/依赖 + 建 venv（幂等）
│   ├── setup_tmux.sh             # 按 config 批量创建 cc-* session
│   ├── install_hooks.sh          # 把 resources/hooks 注册进 ~/.claude
│   └── doctor.sh                 # 体检：依赖/版本/连通性自检
│
├── deploy/                       # ⑤ 部署托管（让它 7×24 活着）
│   ├── com.hivemind.bridge.plist # launchd 模板（${} 占位由 install 替换）
│   ├── install.sh                # 渲染 plist → load 服务 + pmset 常驻
│   ├── uninstall.sh
│   └── pmset.sh                  # 防休眠/合盖常驻配置
│
├── tests/                        # ⑥ 测试（镜像 src 结构）
│   ├── unit/                     # core 纯逻辑（router/registry/detector 优先覆盖）
│   ├── integration/              # 接真实 tmux 的端到端
│   ├── fixtures/                 # 真实 capture-pane 样本（校准 detector）
│   └── conftest.py
│
├── docs/                         # ⑦ 文档
│   ├── ARCHITECTURE_LAYOUT.md    # 本文件
│   ├── ROADMAP.md                # M0–M5 里程碑
│   └── RUNBOOK.md                # 运维手册：重启/排错/恢复
│
├── var/                          # ⑧ 运行时状态（全部 gitignore，删了不伤代码）
│   ├── log/                      # bridge.log 等
│   ├── run/                      # pid / sock
│   ├── state/                    # registry 持久化快照（重启恢复）
│   └── panes/                    # pipe-pane 落盘的终端原始输出
│
├── pyproject.toml                # 包元数据 + 依赖 + 工具配置（ruff/pytest/mypy）
├── .env.example                  # 密钥样例（AppKey/AppSecret），复制成 .env
├── .gitignore                    # 忽略 var/ .env *.local.toml .venv …
├── Makefile                      # 常用入口：make run / test / lint / deploy
└── README.md
```

---

## 2. 顶层目录职责表

| 目录 | 关注点 | 进版本库? | 备注 |
|------|--------|:--:|------|
| `src/hivemind/` | **代码**（唯一可 import 包） | ✅ | src-layout,测试跑已装包 |
| `config/` | **部署配置**(终端清单、间隔、端口) | 样例✅ / `.local`❌ | 改它不改逻辑 |
| `assets/` | **静态资源**(图、截图、文档媒体) | ✅ | 非运行时依赖 |
| `scripts/` | **环境初始化**(装依赖、建 session、装 hook) | ✅ | 幂等、可重复跑 |
| `deploy/` | **常驻托管**(launchd / pmset) | ✅ | 模板 + 安装脚本 |
| `tests/` | 测试 | ✅ | 结构镜像 src |
| `docs/` | 文档 | ✅ | 架构/路线图/运维 |
| `var/` | **运行时状态**(日志/pid/快照/落盘) | ❌ | 机器本地,gitignore |

> 注意区分两类"资源":**运行时必需模板**(钉钉卡片/hook 脚本/tmux profile)放 `src/hivemind/resources/`
> 随包走、用 `importlib.resources` 读;**开发/文档静态物**(架构图/截图)放顶层 `assets/`。
> 这样以 launchd(cwd 不确定)启动时,运行时资源永远能被定位。

---

## 3. 包内分层与依赖方向

```
        app.py / cli.py          ← 编排层(组合根)：只它能 import 所有人
              │
        ┌─────┴──────┐
        ▼            ▼
   基础设施层      core(领域层)    ← 纯逻辑,无 I/O,依赖只进不出
  tmux/ dingtalk/      ▲
  monitor/ hooks/      │
        └──────────────┘
   （基础设施依赖 core 的模型/接口，core 绝不反向依赖 I/O）
```

- **core** 不 import `tmux/dingtalk/monitor/hooks` 任何一个 → 保证 router/registry/detector 可纯单元测试。
- I/O 副作用(subprocess、socket、HTTP)全锁在基础设施层,便于在测试里替身(fake)。
- `app.py` 是唯一组合根:读 config → 实例化各适配器 → 注入 core → 启动 asyncio 循环。

---

## 4. 配置三层叠加策略

优先级从低到高(后者覆盖前者):

| 层 | 文件/来源 | 放什么 | 入库 |
|----|-----------|--------|:--:|
| 1 默认 | `src/hivemind/resources/defaults.toml` | 全部键的权威默认值 | ✅ |
| 2 部署 | `config/hivemind.toml` | 本项目通用配置(终端清单、轮询间隔) | ✅(样例) |
| 3 本机 | `config/hivemind.local.toml` | 环境特定覆盖 | ❌ |
| 4 环境 | `.env` / 环境变量 | **密钥**(钉钉 AppKey/Secret)、敏感项 | ❌ |

- `loader.py` 负责依次合并并交给 `schema.py` 的 pydantic 模型做**类型与约束校验**(端口范围、间隔下限、白名单非空)。
- 密钥**只走环境变量**,绝不写进任何 `.toml`;`.env.example` 给样板。
- 校验失败 → 启动即 fail-fast,不带病运行。

---

## 5. 命名与约定

- 包/模块:全小写 `snake_case`;tmux session:`cc-<name>`;launchd label:`com.hivemind.bridge`。
- 测试镜像源码路径:`src/hivemind/core/router.py` ↔ `tests/unit/core/test_router.py`。
- `detector.py` 的 UI 特征字符串(`esc to interrupt`、`❯ 1. Yes`)集中此一处,
  附 `tests/fixtures/` 的真实样本回归,Claude 版本升级只改这一文件。
- 入口统一:`python -m hivemind run` / `make run`,launchd 也调它,避免多入口漂移。

---

## 6. 目录与里程碑映射

| 里程碑 | 新增/激活的目录与文件 |
|--------|----------------------|
| M0 环境 | `pyproject.toml` `scripts/bootstrap.sh` `scripts/setup_tmux.sh` `config/` `.env.example` |
| M1 MVP | `src/hivemind/{app,cli}.py` `core/{models,registry,router}.py` `tmux/{client,forwarder}.py` `dingtalk/*` |
| M2 监控 | `monitor/{detector,differ,poller}.py` `tests/fixtures/` |
| M3 事件 | `hooks/{server,events}.py` `resources/hooks/` `scripts/install_hooks.sh` `var/panes/` |
| M4 健壮 | `core/queue.py` 白名单(config)+ 权限闸 + `var/state/` 自愈恢复 |
| M5 上线 | `deploy/*` `docs/RUNBOOK.md` 验收清单 |
