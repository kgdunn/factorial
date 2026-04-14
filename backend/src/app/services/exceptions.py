"""Domain exceptions for DOE tool execution."""


class ToolExecutionError(Exception):
    """Raised when a process-improve tool call returns an error."""

    def __init__(self, message: str, tool_name: str | None = None):
        self.message = message
        self.tool_name = tool_name
        super().__init__(message)
