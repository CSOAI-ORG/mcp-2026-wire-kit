# mcp-2026-wire-kit MCP server — stdlib-only, zero runtime deps.
# Glama listing requirement: image starts, server responds to introspection.
FROM python:3.12-slim
WORKDIR /kit
COPY . /kit
RUN python -m py_compile mcp_wire_server.py mcp2026_shim.py mcp_wire_audit.py
EXPOSE 8000
# stdio MCP server (default) — Docker/hosts that introspect over stdio
# launch the process directly; HTTP hosts can wrap with the vendored
# ShimASGI/ShimWSGI.
CMD ["python", "mcp_wire_server.py"]
