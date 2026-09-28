"""LLM Text-to-SQL agent over a pruned, governed warehouse schema context."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .model_provider import ModelProvider, ModelRequest


class SQLExecutionError(ValueError):
    """Validation or runtime error the model may repair by rewriting the SQL."""


ContextFetcher = Callable[[str, str], Mapping[str, Any]]
SQLExecutor = Callable[[str, str], Mapping[str, Any]]


@dataclass(frozen=True)
class SQLPlan:
    answerable: bool
    sql: str = ""
    assumptions: tuple[str, ...] = ()
    reason: str = ""


@dataclass
class SQLAgentResult:
    status: str
    question: str
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    assumptions: tuple[str, ...] = ()
    reason: str = ""
    attempts: list[dict[str, Any]] = field(default_factory=list)
    context_tables: list[str] = field(default_factory=list)
    business_rules: list[str] = field(default_factory=list)
    execution: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


GENERATION_INSTRUCTIONS = (
    "Task: write one SQLite query that answers the question using ONLY the tables, columns and join paths listed.",
    'Return JSON only: {"answerable": true|false, "sql": "<single SELECT or WITH query>", "assumptions": ["..."], "reason": "<why not answerable, if false>"}',
    "Apply every listed business rule. Join only along the listed join paths.",
    "Aggregate in SQL. For ranking questions (which/top/most/least) return the full ranked breakdown (LIMIT 20) with each group's value and share_of_total so the leader can be compared.",
    "Use descriptive snake_case column aliases and round money to 2 decimals.",
    "If a needed table has row_count 0 or a join column has a high null_fraction, still write the query when a correct result is possible and state the coverage gap in assumptions.",
    "If the question needs data that is not in the schema, set answerable to false, leave sql empty and name the missing data in reason. Never substitute a different metric.",
)


class SQLAgent:
    def __init__(self, model: ModelProvider, fetch_context: ContextFetcher, execute_sql: SQLExecutor, max_attempts: int = 3, max_prompt_rows: int = 50) -> None:
        self.model = model
        self.fetch_context = fetch_context
        self.execute_sql = execute_sql
        self.max_attempts = max_attempts
        self.max_prompt_rows = max_prompt_rows

    def run(self, question: str, principal_id: str) -> SQLAgentResult:
        context = self.fetch_context(question, principal_id)
        result = SQLAgentResult(
            status="failed",
            question=question,
            context_tables=[table["name"] for table in context.get("tables", ())],
            business_rules=list(context.get("business_rules", ())),
        )
        for attempt in range(1, self.max_attempts + 1):
            try:
                plan = self.generate(question, context, result.attempts)
            except (ValueError, TypeError, KeyError) as error:
                result.attempts.append({"attempt": attempt, "sql": "", "error": f"Invalid model output: {error}"})
                continue
            if not plan.answerable:
                result.status, result.reason, result.assumptions = "unanswerable", plan.reason or "The warehouse schema does not contain the data needed.", plan.assumptions
                result.attempts.append({"attempt": attempt, "sql": "", "error": None, "answerable": False})
                return result
            try:
                execution = self.execute_sql(plan.sql, principal_id)
            except SQLExecutionError as error:
                result.attempts.append({"attempt": attempt, "sql": plan.sql, "error": str(error)})
                continue
            result.attempts.append({"attempt": attempt, "sql": plan.sql, "error": None})
            result.status = "answered"
            result.sql = str(execution.get("sql", plan.sql))
            result.columns = list(execution.get("columns", ()))
            result.rows = list(execution.get("rows", ()))
            result.assumptions = plan.assumptions
            result.execution = {key: value for key, value in execution.items() if key != "rows"}
            return result
        result.reason = f"No valid SQL after {self.max_attempts} attempts."
        return result

    def generate(self, question: str, context: Mapping[str, Any], previous: Sequence[Mapping[str, Any]] = ()) -> SQLPlan:
        prompt_context = [render_schema_context(context), *GENERATION_INSTRUCTIONS]
        for item in previous:
            if item.get("error"):
                prompt_context.append(f"Previous attempt failed. SQL: {item.get('sql') or '(none)'} Error: {item['error']}. Fix the query.")
        response = self.model.complete(ModelRequest(question, tuple(prompt_context), ("analytics.sql",), max_output_tokens=900, response_format={"type": "json_object"}))
        payload = _parse_json(response.text)
        answerable = payload.get("answerable", True)
        sql = payload.get("sql") or ""
        assumptions = payload.get("assumptions") or []
        if not isinstance(answerable, bool) or not isinstance(sql, str) or not isinstance(assumptions, list):
            raise ValueError("Model returned an invalid SQL plan")
        if answerable and not sql.strip():
            raise ValueError("Model marked the question answerable without SQL")
        return SQLPlan(answerable, sql.strip(), tuple(str(item) for item in assumptions), str(payload.get("reason") or ""))

    def synthesize(self, result: SQLAgentResult, evidence_id: str) -> str:
        if result.status != "answered":
            return result.reason
        rows = result.rows[: self.max_prompt_rows]
        context = (
            f"Evidence ID: {evidence_id}",
            f"SQL: {result.sql}",
            f"Columns: {json.dumps(result.columns)}",
            f"Rows ({len(result.rows)} returned{', truncated' if result.execution.get('truncated') else ''}): {json.dumps(rows, default=str)}",
            f"Query assumptions: {json.dumps(list(result.assumptions))}",
            "Data classification: synthetic.",
            "Answer in 2-4 sentences using only these rows. Lead with the direct answer and its value or share. "
            "If a placeholder group such as 'Uncategorized' or 'Unknown' dominates, say the breakdown is not meaningful because the attribute is missing. "
            "Cite the evidence ID. Do not claim causality.",
        )
        return self.model.complete(ModelRequest(result.question, context, (), max_output_tokens=400)).text.strip()


def summarize_rows(result: SQLAgentResult) -> str:
    if result.status != "answered":
        return result.reason
    if not result.rows:
        return "The query returned no rows."
    first = ", ".join(f"{key}={value}" for key, value in result.rows[0].items())
    return f"Top result: {first} ({len(result.rows)} row(s) returned)."


def render_schema_context(context: Mapping[str, Any]) -> str:
    lines = [f"Dialect: {context.get('dialect', 'sqlite')}. Max rows returned: {context.get('max_rows', 200)}."]
    for table in context.get("tables", ()):
        lines.append(f"TABLE {table['name']} [{table.get('domain', '')}; grain: {table.get('grain', '')}; rows={table.get('row_count', '?')}]: {table.get('description', '')}")
        for column in table.get("columns", ()):
            extras = []
            if column.get("values"):
                extras.append(f"values={json.dumps(column['values'], default=str)}")
            if column.get("range"):
                extras.append(f"range={column['range'][0]}..{column['range'][1]}")
            if column.get("null_fraction") is not None:
                extras.append(f"null_fraction={column['null_fraction']}")
            suffix = f" ({'; '.join(extras)})" if extras else ""
            lines.append(f"  - {column['name']} {column.get('type', '')}: {column.get('description', '')}{suffix}")
    if context.get("join_paths"):
        lines.append("JOIN PATHS:")
        lines.extend(f"  - {join['left']} = {join['right']} ({join.get('description', '')})" for join in context["join_paths"])
    if context.get("unlinked_tables"):
        lines.append(f"No join path exists to: {', '.join(context['unlinked_tables'])}; do not join them.")
    if context.get("business_rules"):
        lines.append("BUSINESS RULES:")
        lines.extend(f"  - {rule}" for rule in context["business_rules"])
    return "\n".join(lines)


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removeprefix("json").removesuffix("```").strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("Model output must be a JSON object")
    return payload
