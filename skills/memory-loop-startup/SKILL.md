---
name: memory-loop-startup
description: Initialize Atlas Memory Loop or Memory Loop through a scan and four guided, validated question stages. Use after a new installation, for an empty or sparse memory vault, when the user asks to bootstrap or initialize Memory Loop, or when an interrupted initialization must resume.
---

# Memory Loop Startup

Initialize a useful baseline memory without turning onboarding into one long questionnaire. Communicate in the user's language and call the product **Atlas Memory Loop** or **Memory Loop**, never just **Atlas**.

## Preserve the boundary

- Treat this skill as one-time or resumable onboarding, not as a session-start hook.
- Keep hooks and the Memory Engine responsible for ongoing capture, indexing, and recall.
- Never store raw answers before the user validates the reformulation.
- Write reviewable memory candidates; never promote canonical knowledge silently.
- Do not claim completion while a stage or verification check is pending.

## Scan before asking

1. Resolve the current project scope and Memory Loop vault without guessing.
2. Call `atlas_health` when available. Otherwise run `atlas-memory doctor` with the resolved vault.
3. Search existing memory with `atlas_recall` for each of the four domains. If MCP is unavailable, inspect relevant Markdown titles and frontmatter without dumping unrelated private content.
4. Look for prior candidates whose type starts with `memory_loop_startup_`. Resume after the last validated stage instead of restarting.
5. Summarize what is already known, what appears contradictory, and which questions can be prefilled.

Read [references/four-domain-questionnaire.md](references/four-domain-questionnaire.md) completely before starting the interview.

## Run exactly four stages

Process the four domains in this order:

1. User and collaboration
2. Project and outcomes
3. Environment and methods
4. Memory governance

For each stage, complete this full cycle before moving on:

1. Announce the stage and its purpose.
2. Ask the complete question series for that stage in one message. Prefill answers supported by the scan and ask the user to confirm or correct them.
3. Wait for the user's answers.
4. Reformulate them into concise, durable statements. Separate stable facts from temporary context and flag contradictions.
5. Ask the user to validate or modify the reformulation.
6. If the user requests changes, revise and ask for validation again.
7. Only after explicit validation, create one candidate with `atlas_remember`:
   - `kind`: the stage candidate type defined in the reference;
   - `project`: the resolved project scope;
   - `content`: only the validated reformulation, using the reference template.
8. Confirm the candidate path, then proceed to the next stage.

Do not combine validation of one stage with questions for the next stage. Allow the user to pause after any validated stage.

If `atlas_remember` is unavailable, use the equivalent `atlas-memory remember` CLI command. If neither interface is available, stop and report that Memory Loop is not operational; do not create an undocumented fallback file.

## Verify the initialization

After all four stages are validated and stored:

1. Run `atlas_health` or `atlas-memory doctor` and require a healthy vault and index.
2. Confirm that this initialization has one validated candidate for each of the four candidate types. Flag older duplicates instead of silently deleting them.
3. Run one bounded recall query per domain using a distinctive validated fact from that domain.
4. Require every query to return the expected candidate in the correct project scope.
5. Check that the stored candidates contain only validated reformulations and no obvious secret value that the user excluded in stage four.
6. If a check fails, explain it, repair only within the user's validated scope, and rerun the complete verification.

## Report completion

Return a compact report in this form:

```text
Memory Loop initialization
Scan: completed
Stages: 4/4 validated
Candidates: 4 confirmed
Health: passed
Recall: 4/4 passed
Status: complete
```

List the four candidate paths and remind the user that they remain reviewable until promoted through the vault's normal consolidation workflow. If any result is pending, set `Status: incomplete` and state the single next action.
