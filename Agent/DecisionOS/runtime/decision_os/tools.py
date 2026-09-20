"""Permission-first tool registration and dispatch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .models import PermissionDecision, ToolRequest, ToolResult

ToolHandler = Callable[[Mapping[str, Any]], Any]
PermissionChecker = Callable[[str, str], PermissionDecision]


@dataclass(frozen=True)
class ToolExecution:
    """Handler output with the provenance needed by the common result envelope."""

    data: Any
    source: tuple[str, ...] = ()
    definition: tuple[str, ...] = ()
    filters: Mapping[str, Any] = field(default_factory=dict)
    freshness: Mapping[str, Any] = field(default_factory=dict)
    query_metadata: Mapping[str, Any] = field(default_factory=dict)
    evidence_references: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler
    resource: str
    read_only: bool = True
    input_schema: Mapping[str, Any] = field(default_factory=dict)
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 5.0
    retry_limit: int = 0


class ToolDispatcher:
    def __init__(self, permission_checker: PermissionChecker) -> None:
        self._permission_checker = permission_checker
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools.values())

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

        validation_error = self._validate_input(spec, request.input)
        if validation_error:
            return ToolResult(
                status="failed",
                warnings=(validation_error,),
                request_id=request.request_id,
            )

        try:
            execution = spec.handler(request.input)
        except Exception as error:
            return ToolResult(
                status="failed",
                warnings=(f"Tool execution failed: {error}",),
                request_id=request.request_id,
            )

        if not isinstance(execution, ToolExecution):
            execution = ToolExecution(data=execution)
        return ToolResult(
            status="succeeded",
            data=execution.data,
            source=execution.source or (spec.name,),
            definition=execution.definition,
            filters=execution.filters or {},
            freshness=execution.freshness or {},
            warnings=execution.warnings,
            request_id=request.request_id,
            query_metadata=execution.query_metadata or {
                "tool": spec.name,
                "resource": spec.resource,
            },
            evidence_references=execution.evidence_references,
        )

    @staticmethod
    def _validate_input(spec: ToolSpec, inputs: Mapping[str, Any]) -> str | None:
        schema = spec.input_schema or {}
        missing = [name for name in schema.get("required", ()) if name not in inputs]
        if missing:
            return f"Missing required tool input: {', '.join(missing)}"
        for name, definition in schema.get("properties", {}).items():
            if name not in inputs or "type" not in definition:
                continue
            expected = {
                "string": str,
                "integer": int,
                "number": (int, float),
                "boolean": bool,
                "object": Mapping,
                "array": (list, tuple),
            }.get(definition["type"])
            if expected and not isinstance(inputs[name], expected):
                return f"Invalid type for tool input '{name}': expected {definition['type']}"
        return None


class PermissionMap:
    """Fail-closed principal-to-resource permission mapping."""

    def __init__(self, grants: Mapping[str, Iterable[str]]) -> None:
        self._grants = {principal: frozenset(resources) for principal, resources in grants.items()}

    def __call__(self, principal_id: str, resource: str) -> PermissionDecision:
        allowed_resources = self._grants.get(principal_id, frozenset())
        allowed = resource in allowed_resources or "*" in allowed_resources
        reason = "allowed" if allowed else f"{principal_id} is not authorized for {resource}"
        return PermissionDecision(allowed, principal_id, resource, reason)
