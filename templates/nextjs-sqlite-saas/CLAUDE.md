# CLAUDE.md

This project is a production SaaS built with Next.js 15 App Router and SQLite.
Follow these instructions as project policy. If code conflicts with this file,
prefer the existing code only after explaining the conflict and the smallest safe
change.

## Stack And Versions

- Runtime: Node.js 22 LTS. Reason: it is the current stable baseline for modern
  Next.js deployments and avoids version-specific fetch, crypto, and test runner
  differences.
- Package manager: `pnpm`. Reason: lockfile determinism and fast installs matter
  for CI and Claude Code task reproducibility.
- Framework: Next.js 15 App Router with React 19 and TypeScript strict mode.
  Reason: Server Components, Server Actions, route handlers, and typed props are
  the default architecture, not an add-on.
- Database: SQLite through either `better-sqlite3` for local/single-region
  deployments or Turso/libSQL for remote/edge-like deployments. Reason: both keep
  the SQL model simple while requiring different connection boundaries.
- Validation: Zod at every request, form, webhook, and environment boundary.
  Reason: TypeScript does not validate runtime input.
- Styling: Tailwind CSS plus small local components. Reason: SaaS product UI
  needs fast iteration and predictable design tokens without a heavy component
  framework.
- Auth and billing are integration boundaries. Reason: never build custom crypto,
  session storage, billing ledgers, or webhook trust from scratch.

## Dev Commands

Use these commands unless the repository defines a more specific script:

```bash
pnpm install
pnpm dev
pnpm lint
pnpm typecheck
pnpm test
pnpm db:migrate
pnpm db:studio
pnpm build
```

Run `pnpm lint`, `pnpm typecheck`, and focused tests before reporting a code task
complete. Run `pnpm build` when changing routing, metadata, Server Components,
database access, auth, billing, or environment handling.

## Folder Structure

Use this structure for greenfield work:

```text
app/
  (marketing)/
    page.tsx
  (app)/
    dashboard/
      page.tsx
      loading.tsx
      error.tsx
  api/
    webhooks/
      stripe/route.ts
  layout.tsx
  globals.css
components/
  ui/
  forms/
  navigation/
db/
  migrations/
  schema.sql
  client.ts
  migrate.ts
lib/
  auth/
  billing/
  env.ts
  errors.ts
  result.ts
  validators/
server/
  actions/
  queries/
  services/
tests/
  unit/
  integration/
  fixtures/
```

Rules:

- Put route-owned UI under `app/`. Reason: App Router colocates route state,
  loading, error, metadata, and layout concerns.
- Put reusable visual primitives under `components/ui/`, not `app/`. Reason:
  route folders should not become shared dependency bins.
- Put database connection code only in `db/client.ts`. Reason: SQLite connection
  mode is a deployment decision and must not leak through the codebase.
- Put direct SQL reads in `server/queries/` and writes in `server/actions/` or
  `server/services/`. Reason: reads and mutations have different caching,
  validation, and transaction needs.
- Put third-party integration code in `lib/<integration>/`. Reason: webhook,
  client, and mapping logic should be easy to audit.
- Put shared validators in `lib/validators/`, named after the boundary they
  protect. Reason: schemas should explain where untrusted data enters.

## Naming Conventions

- React components: `PascalCase`, one component per file when exported. Reason:
  readable imports and stable refactors.
- Route files: App Router names only, such as `page.tsx`, `layout.tsx`,
  `loading.tsx`, `error.tsx`, and `route.ts`. Reason: Next.js uses filenames as
  behavior.
- Server Actions: verb-first names such as `createWorkspaceAction` or
  `updateSubscriptionAction`. Reason: mutations should read as commands.
- Query functions: noun-first names such as `workspaceBySlug` or
  `activeMembersForWorkspace`. Reason: reads should describe returned data.
- SQL tables: plural snake_case, for example `users`, `workspaces`,
  `workspace_members`. Reason: SQL stays consistent with SQLite conventions and
  avoids quoted identifiers.
- SQL columns: snake_case with explicit time suffixes, for example
  `created_at`, `trial_ends_at`, `deleted_at`. Reason: timestamps need semantic
  precision.
- IDs: use `<entity>_id` in SQL and `entityId` in TypeScript. Reason: storage and
  application layers each keep their native style without ambiguity.
- Test files: `<subject>.test.ts` or `<subject>.test.tsx`. Reason: test discovery
  stays simple.

## SQL And Migration Conventions

- Migrations are append-only files in `db/migrations/` named
  `YYYYMMDDHHMMSS_short_description.sql`. Reason: chronological ordering must be
  obvious in reviews and CI.
- Never edit a migration after it has been merged. Reason: deployed SQLite files
  cannot be assumed to match rewritten history.
- Every migration must run inside a transaction unless SQLite forbids a specific
  statement. Reason: failed deploys must not leave partial schema changes.
- Prefer explicit SQL over ORM-generated schema. Reason: SQLite behavior,
  indexes, constraints, and pragmas should be reviewable.
- Enable `PRAGMA foreign_keys = ON` for every connection. Reason: SQLite does not
  protect relationships unless this is enabled.
- Use `INTEGER PRIMARY KEY` or stable text IDs intentionally; do not mix ID
  strategies in the same domain. Reason: mixed primary key styles make joins and
  fixtures harder to reason about.
- Add indexes with the query they support in mind. Reason: indexes are product
  decisions, not decoration.
- Use `created_at`, `updated_at`, and soft-delete `deleted_at` only when the
  product needs restore, audit, or billing history. Reason: unused lifecycle
  columns become misleading.
- Never run destructive migrations automatically in production. Reason: `DROP`,
  `TRUNCATE`, and broad `DELETE` require an explicit operator decision and a
  backup.
- For Turso/libSQL, treat network calls as async and keep database access out of
  Client Components. Reason: remote SQLite has latency and credentials that do
  not belong in the browser.
- For `better-sqlite3`, keep the singleton connection server-only and avoid Edge
  runtime routes. Reason: native modules and Edge runtimes are incompatible.

## Data Access Patterns

- Validate all inputs before calling a query or mutation. Reason: SQL parameter
  binding prevents injection, but it does not enforce product rules.
- Use parameterized SQL only. Reason: string-built SQL is fragile and unsafe.
- Return plain objects from query functions. Reason: Server Components serialize
  predictable data better than class instances or driver-specific rows.
- Wrap multi-step writes in transactions. Reason: SaaS state often spans users,
  workspaces, memberships, and billing records.
- Keep authorization checks next to the data access they protect. Reason: route
  guards alone are easy to bypass when actions and route handlers grow.
- Distinguish "not found" from "not allowed" intentionally. Reason: product
  privacy decisions should be explicit, not accidental.

## Component Patterns

- Default to Server Components. Reason: most SaaS screens are data display, and
  Server Components reduce client JavaScript.
- Add `"use client"` only for local state, browser APIs, focus management,
  optimistic UI, or animation. Reason: client boundaries increase bundle size and
  serialization constraints.
- Keep data fetching in route components or server query modules, not Client
  Components. Reason: database credentials and cache behavior must stay server
  side.
- Use forms plus Server Actions for normal mutations. Reason: forms preserve
  accessibility and progressive enhancement.
- Use route handlers for webhooks and external API callbacks. Reason: those are
  protocol endpoints, not UI actions.
- Include route-level `loading.tsx` and `error.tsx` for dashboard and billing
  surfaces. Reason: SaaS users need clear states around slow data and failures.
- Keep UI copy specific and action-oriented. Reason: product screens should help
  users decide, not explain the implementation.

## Environment And Secrets

- Define environment variables in `lib/env.ts` and validate them with Zod at
  startup. Reason: missing secrets should fail early, not midway through a user
  flow.
- Prefix only browser-safe values with `NEXT_PUBLIC_`. Reason: that prefix exposes
  values to the client bundle.
- Never read `process.env` throughout application code. Reason: centralized env
  parsing makes required config auditable.
- Use separate database URLs for development, test, preview, and production.
  Reason: SQLite files and Turso databases are easy to point at accidentally.

## Testing Policy

- Unit test validators, pure formatting, permission helpers, and SQL statement
  builders. Reason: fast tests catch business-rule regressions.
- Integration test database queries and Server Actions against a temporary SQLite
  database. Reason: mocks do not catch schema, constraint, or transaction errors.
- Test one success path and at least one authorization failure for every
  workspace-scoped mutation. Reason: SaaS bugs are often tenant-boundary bugs.
- Test migrations from an empty database and from the previous schema. Reason:
  greenfield installs and production upgrades are different paths.
- Do not snapshot whole pages by default. Reason: snapshots hide meaningful
  behavior changes in noisy diffs.

## Patterns To Follow

- Server-first data flow: route component -> query/service -> `db/client.ts`.
  Reason: this keeps database access auditable and cache-aware.
- Boundary validation: parse route params, form data, webhook payloads, and env
  values before use. Reason: untrusted data should be obvious in code review.
- Small route groups: split marketing, authenticated app, and admin surfaces.
  Reason: layouts, auth requirements, and metadata differ.
- Explicit cache decisions: use dynamic rendering when data is user-specific;
  use static rendering only for public marketing content. Reason: SaaS data must
  not bleed across users.
- One integration adapter per provider. Reason: replacing Stripe, auth, email, or
  analytics should not touch product UI.

## Anti-Patterns To Avoid

- Do not put database calls in Client Components. Reason: it leaks architecture
  and cannot safely access SQLite credentials.
- Do not create generic `utils.ts` dumping grounds. Reason: vague modules become
  unowned dependencies.
- Do not add an ORM unless the team explicitly chooses one. Reason: this template
  depends on reviewable SQL and SQLite-specific behavior.
- Do not use `any` to bypass input or database row typing. Reason: it hides
  boundary bugs exactly where SaaS data integrity matters.
- Do not catch errors only to return `null`. Reason: "missing", "invalid", and
  "failed" require different product responses.
- Do not make every component a Client Component. Reason: it increases JavaScript
  shipped to users and breaks server-only access patterns.
- Do not run broad updates or deletes without tenant and authorization filters.
  Reason: multi-tenant data loss is the highest-severity SaaS failure.
- Do not store billing state only in Stripe metadata. Reason: the product needs a
  local, queryable view of subscription state.
- Do not rely on middleware as the only authorization layer. Reason: Server
  Actions and route handlers must enforce their own sensitive checks.

## Claude Code Workflow

When starting a task:

1. Identify the route, data model, and tenant boundary involved.
2. Read the relevant files before editing.
3. State the smallest implementation plan and verification commands.
4. Make surgical changes only.
5. Run focused tests first, then broader checks if routing, database, auth, or
   environment behavior changed.

When uncertain, ask one targeted question. Do not invent product requirements,
schema fields, billing behavior, or authorization rules.
