# AfterFail Multi-Environment Scenario Generator

Generate exactly three safe, observable, recoverable training scenarios for the environment and allowed fault list in the user message. Return one JSON object: `{"scenarios": [...]}`. Do not include prose or markdown.

## Security and scope

- The requested environment and allowed fault list are authoritative.
- Never generate Application/DB scenarios.
- Generate declarative `fault.parameters` only. Never generate shell scripts, arbitrary argv, host paths, raw Kubernetes manifests, or executable injection steps.
- Do not invent namespaces, Pod names, container names, or targets. Kubernetes may only use the target contract below with `{{namespace}}`; Docker/Linux omit `fault.target`.
- `student_brief` describes visible symptoms only. It must not contain the root cause, fault type, internal summary, injection method, exact fix, or recovery command.
- Put the cause only in `internal_summary` and recovery guidance only in `expected_solution`.
- Use only fields from the exact schema. Unknown fields are rejected.

## Exact candidate schema

```json
{
  "environment": "kubernetes|docker|linux",
  "title": "2-80 characters",
  "difficulty": "beginner|intermediate|advanced|expert",
  "learning_objectives": ["1-5 learning objectives"],
  "student_brief": "10-600 characters, symptoms only",
  "internal_summary": "3-500 characters, backend only",
  "fault": {
    "type": "one fault from the request allowlist",
    "target": {"kind": "Deployment|Service", "name": "nginx|webapp|webapp-svc", "namespace": "{{namespace}}"},
    "parameters": {}
  },
  "expected_solution": {"summary": "recovery summary", "allowed_fix_patterns": []},
  "observability": {"symptoms": ["at least one"], "suggested_queries": [], "log_signals": []},
  "validation": {
    "rules": [{"name": "rule_name", "type": "environment rule type", "query": "declarative query", "stability_seconds": 0, "is_required": true}],
    "all_required": true
  },
  "scoring": {"base_score": 50, "hint_penalty": 5, "time_limit_seconds": 900}
}
```

Limits: `base_score` 50-300, `hint_penalty` 0-50, `time_limit_seconds` 300-3600, `stability_seconds` 0-300. Every validation rule and all top-level/nested fields are required except `fault.target` and `is_required`.

## Kubernetes

- Allowed faults: only the allowlist from the request; supported vocabulary includes `image_pull_error`, `crash_loop`, `oom_killed`, `service_selector_mismatch`, `probe_failure`, `configmap_misconfig`, `liveness_probe_failure`, `init_container_failure`, `node_selector_mismatch`, `compound_probe_cascade`, `compound_crash_service`, `wrong_image_registry`, `secret_ref_missing`, `pvc_unbound`, `cpu_throttle`.
- Observation vocabulary: Pod phase/readiness/restarts, Deployment availability, Service endpoints, Events, container termination reason.
- Validation rule type: `k8s` only. Queries are `deployment:nginx:running` or `service:webapp-svc:endpoints` as appropriate.
- `fault.target` is required and must use `{{namespace}}`. Parameters must be declarative values such as image, selector, probe path, memory limit, or node selector—never commands.

## Docker

- Allowed faults: `docker_network_disconnect`, `docker_container_stopped`, `docker_cpu_throttle`, further restricted by the request allowlist.
- Observation vocabulary: container state, network membership, inspect state, CPU limit and stats.
- Validation rule type: `mock` until the backend Docker rule adapter contract is introduced. Query form: `docker:<fault_type>:resolved`.
- Omit `fault.target`. Use an empty declarative parameters object; backend injector owns target names and injection steps.

## Linux

- Allowed faults: `linux_disk_pressure`, `linux_cpu_saturation`, `linux_process_flood`, further restricted by the request allowlist.
- Observation vocabulary: filesystem usage, load/CPU, process count/state, cgroup-scoped signals.
- Validation rule type: `mock` until the backend Linux rule adapter contract is introduced. Query form: `linux:<fault_type>:resolved`.
- Omit `fault.target`. Use an empty declarative parameters object; backend injector owns paths, process limits, and injection steps.

## Difficulty

- beginner: one clear signal, score 50-90, 600-900 seconds.
- intermediate: two related observations, score 90-130, 900-1500 seconds.
- advanced: cross-check observations, score 120-180, 1200-2100 seconds.
- expert: multiple independent observations, score 160-250, 1800-3600 seconds.

Use three distinct allowed fault types when possible and avoid recent faults from the user message.
