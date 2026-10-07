# mcp-2026-wire-kit

**Migrate any Model Context Protocol server to the 2026-07-28 stateless wire — audit, translate, verify.**

The 2026-07-28 MCP specification (the largest revision since launch) removed the
`initialize` handshake and `Mcp-Session-Id`, made `Mcp-Method` mandatory on every
request and `Mcp-Name` mandatory on `tools/call` / `resources/read` / `prompts/get`,
added `server/discover`, and started a **12-month deprecation clock (July 2027)**.
Most deployed servers still speak the old wire. This kit tells you which wire *your*
server speaks and moves it forward without breaking existing clients.

## Three tools, zero dependencies (Python stdlib only)

| Tool | What it does |
|---|---|
| `mcp_wire_audit.py` | Classifies server source by wire era (`pre-2025-06` / `2025-06` / `2025-11` / `2026-07` / `unknown`) and assigns one of four migration classes (`none` / `header-add` / `handshake-removal` / `full`). JSONL out + summary report. |
| `mcp2026_shim.py` | Bidirectional wire translation: legacy `initialize` handshakes get a local 2025-11-25 answer (no session), stateless 2026 requests get `_meta.protocolVersion` injected and `Mcp-Session-Id` stripped, `Mcp-Name` is derived from `params.name` when possible and rejected with `-32602` when not, `server/discover` is answered, MRTR `resultType` passes through untouched. Ships as pure functions plus ASGI/WSGI wrappers. |
| `mcp2026_proxy_proof.py` | Live end-to-end proof: starts a real WSGI server wrapping a *legacy* MCP app with the shim and exercises both wires over HTTP. 7/7 assertions. |

Plus `MCP_2026_WIRE_MIGRATION_PLAN.md` — the four-class migration runbook with
per-class code steps and a phase table to the July-2027 deadline.

## Quickstart

```bash
# 1. What wire does my server speak?
python3 mcp_wire_audit.py audit --local /path/to/my-mcp-server
python3 mcp_wire_audit.py report --in audit.jsonl

# 2. Run both wires through one port (bridge, not fork)
python3 -c "
from mcp2026_shim import ShimASGI  # or ShimWSGI
app = ShimASGI(my_mcp_asgi_app)     # legacy + 2026 clients both work
"

# 3. Prove it
python3 mcp2026_proxy_proof.py     # 7/7 PASS
python3 test_mcp_wire.py           # 91 tests, stdlib only
```

## Migration classes (from the plan)

- **`none`** — already on 2026-07-28. Re-audit monthly.
- **`header-add`** (most common) — pin `mcp>=2.0.0`, wire the shim at the
  transport, emit `params._meta.protocolVersion`, drop `Mcp-Session-Id`.
- **`handshake-removal`** — delete `initialize` / `notifications/initialized`
  handlers and session bookkeeping; the shim answers handshake-era clients.
- **`full`** — both, oldest pin first.

## Why this exists

An audit of 422 production MCP servers (2026-10-07) found **zero** on the new wire
and 421 needing at least the `header-add` class. The kit is that audit's execution
half: measure → translate → prove.

Links: [MCP specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) ·
built by [CSOAI-ORG](https://github.com/CSOAI-ORG) for the
[MEOK AI OS](https://meok.ai) sovereign estate.

## License

MIT. Evidence-grade: every claim above was executed (91 tests + 7/7 live proofs) —
not asserted.
