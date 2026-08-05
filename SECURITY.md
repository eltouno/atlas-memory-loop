# Security policy

Atlas Memory Loop is local-first, but hook payloads can contain secrets.

- Redaction occurs before events are written to disk.
- Runtime journals should not be committed.
- Keep the vault and runtime directory under user-controlled permissions.
- Do not expose the MCP server over HTTP without authentication and transport security.

Please report vulnerabilities privately to the repository owner rather than opening a public issue.
