# Next.js SQLite SaaS CLAUDE.md Template

This template is for a greenfield SaaS using Next.js 15 App Router, React 19,
TypeScript, and SQLite through `better-sqlite3` or Turso/libSQL.

## Install

Copy `CLAUDE.md` to the root of the target project:

```bash
cp templates/nextjs-sqlite-saas/CLAUDE.md /path/to/project/CLAUDE.md
```

## Context Validation Notes

Claude Code should be able to answer these without asking clarifying questions
after reading the file:

- Where should database connection code live?
- What migration naming format should be used?
- Should a dashboard data component default to Server or Client Component?
- Which commands should be run before reporting completion?
- Why are broad tenant-scoped deletes an anti-pattern?

Expected interpretation:

- Database connection ownership is `db/client.ts`.
- Migrations are append-only `YYYYMMDDHHMMSS_short_description.sql` files.
- SaaS dashboard screens default to Server Components unless browser-only
  behavior is needed.
- `pnpm lint`, `pnpm typecheck`, focused tests, and sometimes `pnpm build` are
  the baseline checks.
- Broad tenant-scoped deletes risk cross-tenant data loss and must include
  explicit tenant and authorization filters.
