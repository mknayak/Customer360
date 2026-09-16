"""Permission-first tool registration and dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .models import PermissionDecision, ToolRequest, ToolResult

ToolHandler = Callable[[Mapping[str, Any]], Any]
PermissionChecker = Callable[[str, str], PermissionDecision]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    resource: str
    read_only: bool = True


class ToolDispatcher:
    def __init__(self, permission_checker: PermissionChecker) -> None:
        self._permission_checker = permission_checker
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def dispatch(self, request: ToolRequest) -> ToolResult:
        spec = self._tools.get(request.tool_name)
        if spec is None:
            return ToolResult(
                status="failed",
                warnings=(f"Unknown tool: {request.tool_name}",),
                request_id=request.request_id,
            )

        decision = self._permission_checker(request.principal_id, spec.resource)
        if not decision.allowed:
            return ToolResult(
                status="denied",
                warnings=(decision.reason,),
                request_id=request.request_id,
            )

        try:
            data = spec.handler(request.input)
        except Exception as error:
            return ToolResult(
                status="failed",
                warnings=(f"Tool execution failed: {error}",),
                request_id=request.request_id,
            )

        return ToolResult(
            status="succeeded",
            data=data,
            source=(spec.name,),
            request_id=request.request_id,
        )
