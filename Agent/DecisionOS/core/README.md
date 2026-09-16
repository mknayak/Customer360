# DecisionOS Core

DecisionOS Core is application- and industry-agnostic. It provides the reusable decision runtime and governance primitives.

## Core responsibilities

- Investigation lifecycle and state transitions
- Typed tool, evidence, claim, and decision contracts
- Permission-first tool dispatch
- Agent registration and delegation boundaries
- Memory and persistence interfaces
- Evidence validation and lineage requirements
- Evaluation and scenario-test interfaces
- Audit, retention, and versioning rules

## Core boundaries

Core does not know about customers, products, promotions, CRM systems, shopping carts, or finance-specific definitions. Those belong to a domain pack.

The current executable foundation is in `../runtime/`. It is intentionally dependency-free and uses replaceable ports for persistence and tools.

## Domain-pack contract

A domain pack supplies:

- Agents and prompts
- Skills and business procedures
- Tool adapters
- Semantic definitions and metrics
- Entity and relationship mappings
- Data permissions and ownership
- Evaluation scenarios

A domain pack must not modify core contracts to represent a domain-specific concept. It should implement an adapter or register a domain capability instead.
