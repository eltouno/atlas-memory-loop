# Four-domain initialization questionnaire

Use these four stages in order. Adapt wording to the user's language and level, but preserve the intent of every question. When the scan already provides an answer, present it as a proposed answer to confirm instead of asking the user to repeat it.

## Shared candidate template

Write one candidate after each validated stage:

```markdown
## Initialization domain

<domain name>

## Validated memory

- <durable statement>
- <durable statement>

## Temporary context

- <time-bound statement, with date or review condition>

## Boundaries and uncertainty

- <explicit exclusion, contradiction, or uncertainty>
```

Omit empty sections. Never include the raw interview transcript.

## Stage 1 — User and collaboration

Candidate type: `memory_loop_startup_collaboration`

Purpose: establish how an AI agent should collaborate with the user.

Questions:

1. How should the agent address you, and which language should it use by default?
2. What is your level of expertise in the main subjects involved, and how much explanation do you prefer?
3. What response or deliverable format helps you most: concise answer, structured analysis, patch, checklist, examples, or another format?
4. How autonomous may the agent be, and which decisions or actions always require your explicit approval?

Reformulate preferences as operational instructions. Avoid personality judgments that the user did not state.

## Stage 2 — Project and outcomes

Candidate type: `memory_loop_startup_project`

Purpose: define why the current project exists and what success means.

Questions:

1. What is the project's primary purpose, and what problem should it solve?
2. Who uses or benefits from it, including the user alone when it is a personal project?
3. What is inside the current scope, and what is explicitly outside it?
4. What are the present maturity, priorities, and observable criteria for success?

Mark current priorities as temporary unless the user explicitly describes them as durable.

## Stage 3 — Environment and methods

Candidate type: `memory_loop_startup_methods`

Purpose: record the sources of truth and practical working conventions.

Questions:

1. Which tools, platforms, technologies, and environments are central to the project?
2. Which files, repositories, applications, or services are authoritative sources of truth?
3. Which workflows, commands, conventions, and validation steps should an agent follow?
4. Which recurring constraints, failure modes, compatibility requirements, or edge cases should it anticipate?

Prefer exact names and paths when the user confirms them. Do not infer credentials, secrets, or access rights.

## Stage 4 — Memory governance

Candidate type: `memory_loop_startup_governance`

Purpose: define what Memory Loop may retain and how stored knowledge should evolve.

Questions:

1. Which categories of information should Memory Loop retain by default?
2. Which information must never be stored, or should require confirmation before storage?
3. How should Memory Loop handle contradictions, corrections, obsolete facts, and time-bound information?
4. How often should candidates be reviewed or consolidated, and how much recalled context should be injected into future tasks?

Treat exclusions as hard boundaries. When the user is uncertain, default to reviewable candidates and minimal recall rather than automatic retention.
