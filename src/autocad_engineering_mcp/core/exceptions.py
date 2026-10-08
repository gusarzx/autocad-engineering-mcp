"""Domain errors returned to MCP clients without tracebacks or secrets."""


class CadError(Exception):
    """Expected drawing, platform or safety error."""
