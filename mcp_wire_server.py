#!/usr/bin/env python3
"""mcp_wire_server.py — the kit's own MCP server (stdio, zero dependencies).

Makes mcp-2026-wire-kit a *working MCP server* so it can be listed (Glama
requires: starts, responds to introspection, exposes real tools). It serves
the kit itself as tools:

  - wire_audit       classify server source text by wire era + migration class
  - wire_translate   run a JSON-RPC message through the 2026<->legacy shim
  - wire_status      kit version, spec versions, deadline countdown

Wire behavior (eating our own dog food): negotiates BOTH the legacy
initialize handshake and the 2026-07-28 stateless wire. A legacy client gets
protocolVersion 2025-11-25; a client offering 2026-07-28 gets 2026-07-28.

Run:  python3 mcp_wire_server.py            (stdio, for MCP clients)
Test: python3 test_mcp_wire.py              (91 estate tests)
      python3 mcp_wire_server.py --selftest (server introspection proof)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

WIRE_2026 = "2026-07-28"
WIRE_LEGACY = "2025-11-25"
DEADLINE = "2027-07-28"
KIT_VERSION = "0.2.0"

# Import the kit's own modules (same directory).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp2026_shim import translate_request  # noqa: E402

SERVER_INFO = {"name": "mcp-2026-wire-kit", "version": KIT_VERSION}
CAPABILITIES = {"tools": {"listChanged": False}}


# ------------------------------------------------------------------ tools ----
TOOLS = [
    {
        "name": "wire_status",
        "description": "Kit version, MCP spec versions it speaks, and the "
                       "2026-07-28 deprecation deadline countdown.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "wire_audit",
        "description": "Classify MCP server source text by wire era "
                       "(pre-2025-06/2025-06/2025-11/2026-07/unknown) and "
                       "migration class (none/header-add/handshake-removal/full).",
        "inputSchema": {
            "type": "object",
            "properties": {"source": {"type": "string",
                                      "description": "server source code or manifest text"}},
            "required": ["source"],
        },
    },
    {
        "name": "wire_translate",
        "description": "Translate one JSON-RPC MCP message between the legacy "
                       "handshake wire and the 2026-07-28 stateless wire. "
                       "Input: {headers:{}, body:{}}. Output: translated pair + notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "headers": {"type": "object"},
                "body": {"type": "object"},
            },
            "required": ["body"],
        },
    },
]

# Era signals (shared vocabulary with mcp_wire_audit.py).
ERA_SIGNALS = [
    ("2026-07", ("Mcp-Method", "server/discover", "2026-07-28")),
    ("2025-11", ("2025-11-25",)),
    ("2025-06", ("2025-06-18",)),
    ("pre-2025-06", ("2024-11-05", "2025-03-26")),
]
CORE_SIGNALS = ("initialize", "protocolVersion", "Mcp-Session-Id", "tools/call")


def audit_source(source: str) -> dict:
    """Classify one source blob — mirrors mcp_wire_audit's rule shape."""
    era, migration = "unknown", "header-add"
    for candidate, sigs in ERA_SIGNALS:
        if any(s in source for s in sigs):
            era = candidate
            break
    has_core = any(s in source for s in CORE_SIGNALS)
    discover = "server/discover" in source
    headers = "Mcp-Method" in source and "Mcp-Name" in source
    handshake = '"initialize"' in source or "'initialize'" in source
    session = "Mcp-Session-Id" in source
    if era == "2026-07" or (discover and headers):
        era, migration = "2026-07", "none"
    elif handshake and headers:
        migration = "handshake-removal"
    elif not has_core:
        era, migration = "unknown", "none"
    elif handshake and not headers:
        migration = "full" if era == "pre-2025-06" else "header-add"
    return {"era": era, "migration": migration,
            "signals": {"handshake": handshake, "session_id": session,
                        "headers": headers, "discover": discover}}


def days_to_deadline() -> int:
    import datetime
    d = datetime.date.fromisoformat(DEADLINE)
    return (d - datetime.date.today()).days


def call_tool(name: str, args: dict) -> dict:
    if name == "wire_status":
        return {"kit": f"mcp-2026-wire-kit {KIT_VERSION}",
                "speaks": [WIRE_2026, WIRE_LEGACY],
                "deadline": DEADLINE, "days_left": days_to_deadline(),
                "tests": 91}
    if name == "wire_audit":
        return audit_source(args.get("source", ""))
    if name == "wire_translate":
        headers = {str(k): str(v) for k, v in (args.get("headers") or {}).items()}
        h2, b2, notes = translate_request(headers, args.get("body") or {})
        return {"headers": h2, "body": b2, "notes": notes}
    raise KeyError(name)


# ------------------------------------------------------------ json-rpc core ---
def handle(msg: dict) -> dict | None:
    """Handle one JSON-RPC message. Notifications (no id) -> None."""
    method = msg.get("method", "")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if mid is None and method.startswith("notifications/"):
        return None

    if method == "initialize":
        # Legacy clients get the legacy answer; 2026 offerers get 2026.
        offered = params.get("protocolVersion") or WIRE_LEGACY
        negotiated = WIRE_2026 if str(offered).startswith("2026") else WIRE_LEGACY
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": negotiated, "capabilities": CAPABILITIES,
            "serverInfo": SERVER_INFO}}

    if method == "server/discover":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": WIRE_2026, "capabilities": CAPABILITIES,
            "serverInfo": SERVER_INFO}}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        name = (params or {}).get("name", "")
        try:
            payload = call_tool(name, (params or {}).get("arguments") or {})
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text",
                                            "text": json.dumps(payload, sort_keys=True)}],
                               "isError": False}}
        except KeyError:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602, "message": f"unknown tool: {name}"}}

    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def selftest() -> int:
    """Introspection proof: initialize (both wires) + discover + list + calls."""
    ok = True

    def check(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    r = handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"}})
    check("legacy initialize -> 2025-11-25",
          r["result"]["protocolVersion"] == WIRE_LEGACY)
    r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": WIRE_2026}})
    check("2026 initialize -> 2026-07-28",
          r["result"]["protocolVersion"] == WIRE_2026)
    r = handle({"jsonrpc": "2.0", "id": 2, "method": "server/discover"})
    check("server/discover", r["result"]["protocolVersion"] == WIRE_2026)
    r = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    check("tools/list exposes 3 tools", len(r["result"]["tools"]) == 3)
    r = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "wire_status", "arguments": {}}})
    check("wire_status returns deadline", "2027-07-28" in r["result"]["content"][0]["text"])
    r = handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {"name": "wire_audit", "arguments": {
                    "source": 'session = headers.get("Mcp-Session-Id"); "initialize"'}}})
    check("wire_audit classifies legacy source",
          '"header-add"' in r["result"]["content"][0]["text"]
          or '"full"' in r["result"]["content"][0]["text"])
    n = handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    check("notification -> no reply", n is None)
    print("ALL PASS" if ok else "SELFTEST FAILED")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    # stdio loop: newline-delimited JSON-RPC (MCP stdio transport)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
