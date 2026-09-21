"""Fail-closed local governance helpers for DecisionOS records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


@dataclass(frozen=True)
class AccessPolicy:
    principal_id: str
    allowed_resources: frozenset[str]
    masked_fields: frozenset[str] = frozenset()
    consent_required: bool = False


class GovernancePolicy:
    def __init__(self, policies: Mapping[str, AccessPolicy]) -> None:
        self._policies = dict(policies)

    def authorize(self, principal_id: str, resource: str, *, consent_granted: bool = False) -> None:
        policy = self._policies.get(principal_id)
        if policy is None or resource not in policy.allowed_resources and "*" not in policy.allowed_resources:
            raise PermissionError(f"{principal_id} is not authorized for {resource}")
        if policy.consent_required and not consent_granted:
            raise PermissionError(f"consent is required for {resource}")

    def project(self, principal_id: str, resource: str, record: Mapping[str, Any], *, consent_granted: bool = False) -> dict[str, Any]:
        self.authorize(principal_id, resource, consent_granted=consent_granted)
        masked = self._policies[principal_id].masked_fields
        return {key: ("[MASKED]" if key in masked else value) for key, value in record.items()}

    @staticmethod
    def retention_expired(expires_at: str | None, *, now: datetime | None = None) -> bool:
        if not expires_at:
            return False
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return (now or datetime.now(timezone.utc)) >= expiry
