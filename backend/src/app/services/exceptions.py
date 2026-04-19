"""Domain exceptions for DOE tool execution."""


class ToolExecutionError(Exception):
    """Raised when a process-improve tool call returns an error."""

    http_status: int = 422

    def __init__(self, message: str, tool_name: str | None = None):
        self.message = message
        self.tool_name = tool_name
        super().__init__(message)


class ToolInputTooLargeError(ToolExecutionError):
    """Raised when tool input exceeds a size / cap limit before execution."""

    http_status = 413


class ToolTimeoutError(ToolExecutionError):
    """Raised when a tool call exceeds its wall-clock timeout."""

    http_status = 408


class ToolMemoryExceededError(ToolExecutionError):
    """Raised when the worker subprocess exceeds its memory cap."""

    http_status = 507


class ToolBudgetExceededError(ToolExecutionError):
    """Raised when the caller has consumed their daily CPU budget."""

    http_status = 429
