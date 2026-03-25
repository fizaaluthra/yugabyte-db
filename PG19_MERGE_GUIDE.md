# PG19 Merge Guide: Patterns, Changelog, and Strategy

## Part 1: Failure Patterns Discovered

These patterns were discovered during a proof-of-concept merge of YB's PG15 fork
onto PG19 master (as of Feb 2026). Each pattern represents a category of issues
that will need systematic fixing across the codebase.

---

### Pattern 1: Removed Preprocessor Guards

**What changed:** PG19 removed several long-standing `#ifdef` guards for features
that are now unconditionally supported.

**Example:** `HAVE_UNIX_SOCKETS` was removed. YB's tserver-key authentication code
in `auth.c` was guarded by `#ifdef HAVE_UNIX_SOCKETS`, making the entire
`CheckYbTserverKeyAuth` function dead code. Connections failed with
`FATAL: tserver key authentication failed`.

**Fix pattern:** Remove the `#ifdef`/`#endif` guards. The code should be
unconditionally compiled.

**Files likely affected:** Grep for `#ifdef HAVE_UNIX_SOCKETS`,
`#ifdef HAVE_SPINLOCKS`, and any other `HAVE_*` macros that PG19 removed.

**PG commits to review:**
- Removal of `HAVE_UNIX_SOCKETS` (unix sockets now always supported)
- Removal of other platform-conditional compilation guards

---

### Pattern 2: Struct Field Additions (Uninitialized Memory)

**What changed:** PG19 added new fields to existing structs. YB code that
allocates these structs using `palloc()` (not `palloc0()`) leaves new fields
as garbage, causing crashes when PG code accesses them.

**Example:** `TokenizedAuthLine` gained a `file_name` field in PG19. YB's
`yb_tokenize_line()` in `hba.c` used `palloc()` to allocate the struct.
When PG19's `parse_hba_line()` called `pstrdup(tok_line->file_name)`, it
dereferenced garbage → SIGSEGV.

**Fix pattern:**
1. Change `palloc()` to `palloc0()` for any struct allocation where PG added fields
2. Explicitly initialize new fields where appropriate
3. Audit all YB code that allocates PG structs manually

**How to find:** Search for `palloc(sizeof(` in YB-specific code and cross-reference
with structs that changed between PG15 and PG19.

---

### Pattern 3: Function Signature Changes

**What changed:** PG19 changed the signatures of several internal functions,
adding new parameters (often for new features like incremental backup,
AIO, or improved error handling).

**Example:** `FuncnameGetCandidates()` added an `int *fgc_flags` parameter.
YB's `YbGetSQLIncrementCatalogVersionFunctionOidHelper()` in
`yb_catalog_version.c` passed `NULL`, which PG19 unconditionally dereferences.

**Fix pattern:** Declare a local variable with a sensible default and pass
its address:
```c
// Before (PG15):
FuncCandidateList clist = FuncnameGetCandidates(names, -1, NIL, false, false, false, true);
// After (PG19):
int fgc_flags = 0;
FuncCandidateList clist = FuncnameGetCandidates(names, -1, NIL, false, false, false, true, &fgc_flags);
```

**How to find:** Compilation errors will catch most of these. But some functions
may accept `NULL` in some code paths and crash in others — search for any YB
code that passes `NULL` to PG functions that gained new pointer parameters.

---

### Pattern 4: Custom Node Types Not Handled in New Code Paths

**What changed:** PG19 added new expression handling code paths, restructured
the executor, and added new node-processing functions. YB's custom node types
(e.g., `T_YbExprColrefDesc`, `T_YbBitmapIndexScan`, etc.) are not handled
in these new paths, hitting `default: elog(ERROR, "unrecognized node type")`
cases.

**Example:** `T_YbExprColrefDesc` (node type 415) was not handled in PG19's
`expression_tree_walker_impl`, `expression_tree_mutator_impl`, `exprType`,
`exprTypmod`, `exprCollation`, or `ExecInitExprRec`. This caused
`ERROR: unrecognized node type: 415` during any DDL operation that triggered
catalog version increment (which internally executes SQL functions via SPI).

**Fix pattern:** Add `case T_YbExprColrefDesc:` (and other YB node types) to:
- `exprType()` — return the node's `typid`
- `exprTypmod()` — return the node's `typmod`
- `exprCollation()` — return the node's `collid`
- `expression_tree_walker_impl()` — treat as primitive (no subnodes)
- `expression_tree_mutator_impl()` — `return copyObject(node)`
- `ExecInitExprRec()` — generate appropriate execution steps

**Files affected:**
- `src/backend/nodes/nodeFuncs.c`
- `src/backend/executor/execExpr.c`
- `src/backend/nodes/queryjumblefuncs.c` (auto-generated, may need manual additions)
- Any new node-processing files added in PG19

**Full list of YB custom node types to audit:**
```
T_YbExprColrefDesc
T_YbBitmapIndexScan
T_YbBitmapTableScan
T_YbBatchedNestLoop
T_YbSeqScan
T_YbSample
(and others — grep for T_Yb in nodes/nodetags.h)
```

---

### Pattern 5: Merge Conflict Artifacts — PG Code Leaking into YB Paths

**What happened:** During merge conflict resolution, PG-specific code was
incorrectly placed inside YB-specific code paths (guarded by
`IsYugaByteEnabled()`). The conflict markers mixed PG's concurrent index
phases with YB's custom backfill flow.

**Example:** `validate_index()` is a PG-specific function for concurrent
index creation that scans the heap and inserts missing index entries. In YB,
index backfill is handled entirely by `YBCPgBackfillIndex()` via DocDB.
During the merge, `validate_index()` was incorrectly inserted into the YB
code path in `DefineIndex()` (indexcmds.c). This caused crashes because:
1. `validate_index` was called outside a transaction context (SIGBUS)
2. Even with a transaction, it tries PG heap scans on DocDB tables

**Fix:** Remove `validate_index()` from the YB path entirely. The correct
YB flow (matching PG15) is:
```c
// After committing indisready=true:
CommitTransactionCommand();
StartTransactionCommand();
YBIncrementDdlNestingLevel(YB_DDL_MODE_VERSION_INCREMENT);
YbWaitForBackendsCatalogVersion();
HandleYBStatus(YBCPgBackfillIndex(databaseId, indexRelationId));
// ... then mark index valid
```

**How to find:** This is a general pattern for merge conflicts. Anywhere PG
and YB have divergent code paths (typically an `if (IsYugaByteEnabled())`
/ `else` block), verify that the conflict resolution kept each path intact
and didn't mix code from one into the other. Pay special attention to:
- `DefineIndex()` — complex multi-phase DDL with separate PG/YB paths
- `ATExecAddIndex()` — ALTER TABLE ADD INDEX
- Any DDL command with `YBDecrementDdlNestingLevel` / `YBIncrementDdlNestingLevel`

---

### Pattern 6: Symbol Visibility — Background Worker Functions Not Exported

**What changed:** PG19 changed the default symbol visibility for extension
shared libraries to hidden. Functions loaded dynamically via `dlsym()` (such
as background worker entry points) must be explicitly exported with
`PGDLLEXPORT`.

**Example:** `yb_pg_metrics.dylib` registers a background worker with
`bgw_function_name = "webserver_worker_main"`. The function exists in the
dylib but as a **local** symbol (lowercase `t` in `nm` output). PG's
`load_external_function()` calls `dlsym()` which can only find globally
visible symbols → `ERROR: could not find function "webserver_worker_main"`.

**Fix pattern:** Add `PGDLLEXPORT` declaration before the function definition:
```c
// Add a forward declaration with PGDLLEXPORT:
PGDLLEXPORT void webserver_worker_main(Datum unused);

void
webserver_worker_main(Datum unused)
{
    ...
}
```

**How to find:** Search for all `bgw_function_name` assignments in YB
extensions and verify the referenced functions have `PGDLLEXPORT`. Also check
any YB extension function loaded via `load_external_function()`.

**Files affected:**
- `src/postgres/yb-extensions/yb_pg_metrics/yb_pg_metrics.c`
- Any other YB extensions registering background workers

---

### Pattern 7: Expression Pushdown Interference with Plan Caching

**What changed:** PG19's plan caching and SPI execution paths are stricter
about what node types appear in expression trees. YB's expression pushdown
optimization creates `YbExprColrefDesc` nodes in targetlists, which are
intended only for DocDB but leak into the general PG expression evaluator
when SQL functions are executed via SPI.

**Example:** The catalog version increment function
`yb_increment_db_catalog_version_with_inval_messages` is a SQL function
that internally does `UPDATE pg_yb_catalog_version ... RETURNING`. When
`yb_enable_expression_pushdown` is true, YB's single-row optimization creates
`YbExprColrefDesc` nodes in the RETURNING clause. These pass through SPI into
`ExecInitExprRec`, which doesn't know how to handle them.

**Workaround applied:** Temporarily disable `yb_enable_expression_pushdown`
around internal catalog update operations:
```c
bool save_pushdown = yb_enable_expression_pushdown;
yb_enable_expression_pushdown = false;
// ... execute catalog SQL functions ...
yb_enable_expression_pushdown = save_pushdown;
```

**Proper fix needed:** Ensure `YbExprColrefDesc` nodes are never generated in
contexts where they'll be processed by the generic PG expression evaluator,
OR ensure all PG expression evaluation paths can handle them gracefully.

---

### Pattern 8: Sequence / SERIAL Handling

**What changed:** PG19 likely changed sequence storage format or metadata.
YB's sequence implementation may not match.

**Example:** `CREATE TABLE employees (id serial PRIMARY KEY, ...)` fails with
`ERROR: bad magic number in sequence "employees_id_seq": 00000000`.

**Fix pattern:** TBD — requires investigation of PG19 sequence format changes
and YB's sequence implementation in DocDB.

**Impact:** Blocks any use of `serial`, `bigserial`, `smallserial` columns
and explicit `CREATE SEQUENCE`.

---

## Part 2: Relevant PG Changelog (PG16 → PG19)

These are the changes most likely to affect YB's PostgreSQL fork, organized
by risk level.

### High Impact (Will Break YB Code)

#### Catalog Schema Changes
- **New system columns added to catalog tables** — Any new columns in
  `pg_class`, `pg_attribute`, `pg_proc`, `pg_type`, `pg_index`, etc.
  require matching changes in YB's DocDB catalog schema and initdb.
- **PG17: `pg_class.relallfrozen` added** — New column tracking all-frozen
  page count.
- **PG16-19: Various `pg_attribute` changes** — Attribute cache offset
  (`attcacheoff`) handling changes.

#### Node System Overhaul
- **PG16: Auto-generated node support** — `gen_node_support.pl` now
  auto-generates `equal`, `copy`, `read`, `write` functions for nodes.
  YB custom nodes need to be integrated into this system OR have manual
  overrides.
- **PG16+: NodeTag renumbering** — Node tag numeric values change between
  versions. YB code that uses hardcoded node tag numbers will break.
  Always use `T_YbFoo` symbolic names.

#### Executor Changes
- **PG17: Incremental sort improvements**
- **PG17: New `ReturningExpr` node type** — Replaces direct targetlist
  handling for RETURNING clauses. YB's `ybReturningColumns` /
  `ybPushdownTlist` may conflict.
- **PG18: Async I/O (AIO) infrastructure** — New I/O subsystem may affect
  YB's storage layer integration.
- **PG19: I/O worker management** — `maybe_adjust_io_workers()` and related
  infrastructure.

#### Authentication / Connection
- **PG19: `HAVE_UNIX_SOCKETS` removed** — Unix socket support is now
  unconditional. All `#ifdef HAVE_UNIX_SOCKETS` guards are gone.
- **PG17: HBA file parsing changes** — `TokenizedAuthLine` struct changes,
  new fields for file tracking.

### Medium Impact (May Break, Needs Audit)

#### Planner Changes
- **PG16: Improved join planning** — New join path types, changed cost
  models. YB's custom scan paths may need updating.
- **PG17: Incremental backup support** — Touches WAL, pg_control, and
  checkpoint infrastructure.
- **PG18: Virtual generated columns** — New column storage type that
  affects tuple descriptor handling.

#### Background Workers
- **PG16+: Background worker API changes** — Registration and lifecycle
  management changes. Affects `yb_pg_metrics` webserver worker.

#### GUC System
- **PG16: GUC system overhaul** — Internal representation of GUCs changed.
  Custom YB GUCs may need adaptation.
- **PG19: New GUC categories and validation** — Additional GUC infrastructure
  changes.

#### Memory / Shared Memory
- **PG17: DSA (Dynamic Shared Memory Area) changes**
- **PG18+: Shared memory layout changes** — May affect YB's shared memory
  integration (`YBCSetupSharedMemoryAddressSegment`).

### Lower Impact (Behavioral, Caught by Tests)

- **PG16: `COPY FROM` performance improvements** — Changed internals
- **PG17: JSON improvements** — `JSON_TABLE`, `IS JSON`, etc.
- **PG18: UUIDv7 support** — New UUID generation
- **PG19: Various SQL standard compliance improvements**
- **Date/time handling refinements across versions**
- **Error message text changes** (will cause test output mismatches)

---

## Part 3: Systematic Audit Checklist

Before starting the official merge, audit these areas:

### YB Custom Code Inventory
```bash
# All YB-specific files
find src/postgres -name '*yb*' -o -name '*yugabyte*' | wc -l

# All YB ifdef blocks
grep -rn '#ifdef.*YB\|#if.*IsYugaByte\|#if.*YB_' src/postgres/src/ | wc -l

# All YB custom node types
grep 'T_Yb' src/postgres/src/include/nodes/nodetags.h

# All YB GUCs
grep 'DefineCustom.*Variable.*"yb_' src/postgres/src/backend/utils/misc/guc.c
```

### PG API Change Points
```bash
# Functions with changed signatures (compare PG15 vs PG19 headers)
diff <(grep -r 'extern.*(' pg15/src/include/) <(grep -r 'extern.*(' pg19/src/include/)

# Struct changes
diff <(grep -rA5 'typedef struct' pg15/src/include/) <(grep -rA5 'typedef struct' pg19/src/include/)

# Removed macros
diff <(grep '#define' pg15/src/include/pg_config.h) <(grep '#define' pg19/src/include/pg_config.h)
```

### Critical Test Categories (Priority Order)
1. `src/postgres/src/test/regress/` — SQL regression tests
2. `src/yb/yql/pgwrapper/` — YB PG wrapper tests
3. `src/yb/integration-tests/` — Integration tests
4. `java/yb-pgsql/` — Java YSQL tests

---

## Part 4: Files Modified During This Exercise

For reference, these files were modified to fix issues found during the PoC:

| File | Fix |
|------|-----|
| `src/yb/yql/pgwrapper/pg_wrapper.cc` | Conditional shared_preload_libraries |
| `src/postgres/src/backend/libpq/hba.c` | TokenizedAuthLine.file_name init |
| `src/postgres/src/backend/libpq/auth.c` | Remove HAVE_UNIX_SOCKETS guards |
| `src/postgres/src/backend/nodes/nodeFuncs.c` | YbExprColrefDesc in walker/mutator/exprType/etc |
| `src/postgres/src/backend/executor/execExpr.c` | YbExprColrefDesc in ExecInitExprRec |
| `src/postgres/src/backend/catalog/yb_catalog/yb_catalog_version.c` | FuncnameGetCandidates flags + pushdown disable |
| `src/postgres/src/backend/commands/indexcmds.c` | Remove validate_index from YB path (merge artifact) |
| `src/postgres/yb-extensions/yb_pg_metrics/yb_pg_metrics.c` | Add PGDLLEXPORT to webserver_worker_main |
| `src/postgres/src/test/regress/pg_regress_main.c` | Restore ysqlsh (was overwritten to psql by merge) |
