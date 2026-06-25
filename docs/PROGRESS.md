# Hivemind 构建进度与交接文档

> 用途:跨会话交接。**新会话只需读本文件 + `docs/ARCHITECTURE_LAYOUT.md`** 即可接续执行。
> 最后更新:2026-06-23 · 已完成 M0→M3,下一步 M4。

---

## 1. 项目是什么

用 tmux 把多个 **Claude Code** 终端变成常驻"脑区",通过**钉钉手机端**远程下发指令、定向指挥、实时监控。本机零入站端口,全程出站长连接,可 7×24 运行。

数据流:
```
手机钉钉 --出站WS--> Bridge --send-keys--> tmux:cc-<name> --> claude code
         <--webhook推送-- Monitor <--capture-pane / claude-hooks--/
```

---

## 2. 里程碑总览

| 里程碑 | 状态 | 内容 |
|---|---|---|
| **M0 环境** | ✅ 完成 | 项目骨架、pyproject、venv、scripts、deploy 全部就位 |
| **M1 MVP** | ✅ 完成 | Registry + Router(`@name`/slash 命令)+ Forwarder(send-keys 安全注入)+ DingTalk Stream 客户端 + Dispatcher + Bridge 编排(含重连退避) |
| **M2 监控** | ✅ 完成 | `detect_state` 状态机 + Monitor 抓屏 diff 轮询 + 状态迁移主动推送 + 钉钉 `session_webhook` 主动推送 |
| **M3 精确事件** | ✅ 完成 | hooks_server(aiohttp `127.0.0.1/event`)+ Monitor `handle_hook` 权威路径 + hook/poll 时间窗去重 + install-hooks.sh |
| **M4 健壮性** | ⬜ 待做 | 每终端消息队列、发送者白名单闸、权限确认闸、终端自愈重建 |
| **M5 上线** | ⬜ 待做 | launchd 托管验证 + pmset 常驻 + 全链路验收清单 |

---

## 3. 当前测试与质量基线

```
ruff check src tests   → All checks passed!
pytest                 → 46 passed, 1 skipped
```
- 唯一 skip:`tests/integration/test_tmux_smoke.py`(需真实 tmux,沙箱无)。
- 沙箱无 tmux,故 `load_presets` 在启动时会抛 traceback 并被 `_restore_terminals` 捕获 → **这是预期降级**,本机有 tmux 即正常。
- 已验证 Bridge 并发跑 3 个后台任务:`dingtalk-supervisor` + `monitor` + `hooks-server`,`/health` 和 `/event` 真实 HTTP 200。

运行验证命令:
```bash
cd <项目根> && source .venv/bin/activate
ruff check src tests && python -m pytest -q
```

---

## 4. 代码地图(已实现 = ✅,stub = ⬜)

```
src/hivemind/
├── __main__.py        ✅ python -m hivemind 入口
├── bridge.py          ✅ asyncio 编排:registry→presets→dingtalk supervisor→monitor→hooks-server
├── config.py          ✅ pydantic-settings 分层:defaults < hivemind.toml < .local.toml < env < .env;密钥只走 env
├── core/
│   ├── registry.py    ✅ Terminal/TermState + TerminalManager(spawn/kill/load_presets/update_state)
│   ├── state.py       ✅ detect_state + clean_tail + is_attention_state;marker 集中常量
│   └── queue.py       ⬜ TerminalQueue 已定义但【M4 才接入】
├── adapters/
│   ├── tmux.py        ✅ new/kill/list/capture_pane/send_escape/send_literal/send_enter;注入 HIVEMIND_TERM
│   ├── dingtalk.py    ✅ Stream 客户端 + IncomingMessage + WebhookRegistry + push_markdown 主动推送
│   └── claude_hooks.py✅ HookEvent/HookPayload(pydantic)
├── services/
│   ├── router.py      ✅ parse():@name / /ls /status /spawn /kill /y /n /help
│   ├── forwarder.py   ✅ forward():Esc→literal→Enter 安全协议
│   ├── dispatcher.py  ✅ Directive→动作→Markdown 回复;持有"默认终端"会话粘性
│   ├── monitor.py     ✅ poll_loop/tick/_poll_one + handle_hook + _emit 时间窗去重
│   └── hooks_server.py✅ aiohttp make_app + serve_forever;POST /event(校验,400)+ GET /health
└── utils/
    ├── logging.py     ✅ 控制台 + var/logs/bridge.log 轮转
    └── shell.py       ✅ run_cmd 异步 subprocess 封装
```

配置 / 资源 / 脚本 / 部署:见 `docs/ARCHITECTURE_LAYOUT.md`,均已就位。
- `config/`:hivemind.toml / terminals.toml / whitelist.toml ✅(whitelist 尚未被代码读取,M4 接)
- `assets/claude-hooks/settings.hooks.json` ✅(`@PORT@` 占位)
- `scripts/`:bootstrap / doctor / install-hooks / tmux-spawn / dev ✅
- `deploy/`:launchd plist / pmset-setup / install-service ✅(M5 才实测)

---

## 5. 关键设计决策(避免新会话重复踩坑)

1. **三层架构**:`core`(纯逻辑,不知道钉钉/tmux)/ `adapters`(封装外部系统)/ `services`(编排)。脆弱的"依赖 Claude UI 字符串"逻辑只在 `core/state.py`,配 `tests/fixtures/*.txt` 回归。
2. **send-keys 安全协议**(forwarder):必须 ① 先 Esc 清场 ② `-l` literal 发文本 ③ **单独**发 Enter。绝不能把文本和回车合并。
3. **hook 与 poll 协作**:两条信号都汇入 `Monitor._emit()`,用 `(终端,状态)` + 时间窗(默认 10s)去重 → hook 拿秒级精度,poll 兜底全覆盖,手机端不重复刷屏。
4. **"有意义迁移"才推送**:推 `BUSY→IDLE`(完成)、`→WAITING`(等确认)、`→ERROR`、`→DEAD`;静默 `IDLE→BUSY`(用户刚发的)和首次观测。
5. **配置分层**:密钥(钉钉 AppKey/Secret)只走 `.env`/env,永不进 `.toml`。`var/` 整目录 gitignore。

---

## 6. 下一步:M4 健壮性(待执行)

按优先级,四个子任务:

### 4.1 每终端消息队列(BUSY 不竞态)
- 接入已存在的 `core/queue.py::TerminalQueue`。
- Dispatcher 的 `/send` 路径改为:终端 BUSY → 入队;Monitor 观测到该终端回到 IDLE → 触发队列 drain → forward 下一条。
- 需要 Monitor 在 `_emit` 完成迁移到 IDLE 时回调一个 "terminal_idle" 钩子给 Bridge/Dispatcher。
- 测试:BUSY 时连发 3 条,断言按序注入。

### 4.2 发送者白名单闸
- 读 `config/whitelist.toml` 的 `senders.allow`;在 `bridge.on_message`(当前有 `TODO(M4)` 锚点)最前面拦截。
- 非白名单:按 `policy.reply_on_reject` 决定礼貌拒绝或静默。
- 把 staffId 加入 `Settings`(新增 `WhitelistSettings` 或独立加载)。
- 测试:白名单内放行、白名单外拒绝两条路径。

### 4.3 权限确认闸
- 当终端处于 WAITING,只有白名单用户的 `/y` `/n` 能放行(router 已能解析 CONFIRM)。
- dispatcher 对 CONFIRM:校验目标终端确实 WAITING 才发 `1`/`2`,否则提示。

### 4.4 终端自愈重建
- Monitor 检测到 `DEAD` 时,按 `terminals.toml` 预设自动 `spawn` 重建(可加重建次数上限/退避,防崩溃循环)。
- 推送"终端已自动重启"卡片。
- 测试:模拟 capture 抛错→DEAD→断言触发 respawn。

---

## 7. 在本机跑起来(给用户的操作)

```bash
cd <Hivemind 项目根>
cp .env.example .env          # 填 HIVEMIND_DINGTALK__CLIENT_ID / __CLIENT_SECRET
brew install tmux jq          # 沙箱没有;本机需要
./scripts/bootstrap.sh        # 建 venv 装依赖(已验证可用)
# 编辑 config/terminals.toml 填你的项目路径
./scripts/install-hooks.sh    # 写入 ~/.claude/settings.json(M3 hooks)
./scripts/dev.sh              # 前台启动;手机钉钉私聊机器人发 /ls 测试
./scripts/doctor.sh           # 体检 tmux/claude/.env/hooks
```

---

## 8. 新会话接续提示词(复制即用)

> 我在继续构建 Hivemind 项目(钉钉远程指挥 Claude Code 多终端)。请先读 `docs/PROGRESS.md` 和 `docs/ARCHITECTURE_LAYOUT.md` 了解现状:M0–M3 已完成并通过测试(46 passed)。现在开始 **M4 健壮性**,按 PROGRESS.md 第 6 节四个子任务推进,先做 4.1 每终端消息队列。每步用 `pytest` + `ruff` 验证。
