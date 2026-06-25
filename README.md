# Hivemind

> Remote-command multiple **Claude Code** terminals from your phone (DingTalk) — via tmux, outbound-only, runnable 24/7 on your Mac.

Each terminal is an independent tmux session (`cc-<name>`) acting as a "brain region".
A long-running asyncio **Bridge** connects to DingTalk over an outbound Stream WebSocket
(no inbound ports), routes your messages to the right terminal, injects them safely with
`tmux send-keys`, and pushes state changes (done / waiting-for-confirm / error) back to your phone.

```
phone(DingTalk) <--outbound WS--> Bridge --send-keys--> tmux:cc-web   --> claude code
                                        \--send-keys--> tmux:cc-infra --> claude code
                       capture-pane / claude-hooks --> Monitor --> push back to phone
```

## Quick start

```bash
git clone <repo> && cd hivemind
cp .env.example .env          # fill DingTalk credentials
./scripts/bootstrap.sh        # create venv, install deps, run doctor
./scripts/doctor.sh           # verify tmux / claude / connectivity
./scripts/dev.sh              # run in foreground for debugging
```

Install as a 24/7 launchd service:

```bash
./deploy/install-service.sh
```

## Layout

See [`docs/ARCHITECTURE_LAYOUT.md`](docs/ARCHITECTURE_LAYOUT.md) for the full directory design.

| Path | Purpose |
|------|---------|
| `src/hivemind/` | All source code (the only import root) |
| `config/`       | User-editable config (defaults in git, `.local.toml` overrides) |
| `assets/`       | Static resources: card templates, prompts, hooks templates |
| `scripts/`      | Environment bootstrap & ops scripts |
| `deploy/`       | launchd / pmset / service install |
| `tests/`        | Unit + integration tests |
| `var/`          | Runtime data (logs / pid / state) — gitignored |

## License

MIT
