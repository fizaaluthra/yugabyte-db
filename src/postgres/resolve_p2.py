#!/usr/bin/env python3
import re

FILEPATH = "src/bin/pg_dump/pg_dump.c"
with open(FILEPATH, "r") as f:
    content = f.read()

pat = "<<<<<<< ours\n(.*?)=======\n(.*?)>>>>>>> theirs\n"
conflicts = list(re.finditer(pat, content, re.DOTALL))
print(f"Found {len(conflicts)} conflicts")

for i in range(len(conflicts) - 1, -1, -1):
    m = conflicts[i]
    ours = m.group(1)
    theirs = m.group(2)
    sl = content[:m.start()].count("\n") + 1
    r = None

    # Conflict: indoption in index query
    if "indoption" in theirs and "inh.inhparent AS parentidx" in ours:
        r = ('\t\tappendPQExpBufferStr(query,\n'
            '\t\t\t\t\t\t\t "i.indoption, "\t/* YB */\n'
            '\t\t\t\t\t\t\t "inh.inhparent AS parentidx, "\n'
            '\t\t\t\t\t\t\t "i.indnkeyatts AS indnkeyatts, "\n'
            '\t\t\t\t\t\t\t "i.indnatts AS indnatts, "\n'
            '\t\t\t\t\t\t\t "(SELECT pg_catalog.array_agg(attnum ORDER BY attnum) "\n'
            '\t\t\t\t\t\t\t "  FROM pg_catalog.pg_attribute "\n'
            '\t\t\t\t\t\t\t "  WHERE attrelid = i.indexrelid AND "\n'
            '\t\t\t\t\t\t\t "    attstattarget >= 0) AS indstatcols, "\n'
            '\t\t\t\t\t\t\t "(SELECT pg_catalog.array_agg(attstattarget ORDER BY attnum) "\n'
            '\t\t\t\t\t\t\t "  FROM pg_catalog.pg_attribute "\n'
            '\t\t\t\t\t\t\t "  WHERE attrelid = i.indexrelid AND "\n'
            '\t\t\t\t\t\t\t "    attstattarget >= 0) AS indstatvals, ");\n'
            '\telse\n'
            '\t\tappendPQExpBufferStr(query,\n'
            '\t\t\t\t\t\t\t "i.indoption, "\t/* YB */\n'
            '\t\t\t\t\t\t\t "0 AS parentidx, "\n'
            '\t\t\t\t\t\t\t "i.indnatts AS indnkeyatts, "\n'
            '\t\t\t\t\t\t\t "i.indnatts AS indnatts, "\n'
            '\t\t\t\t\t\t\t "\'\' AS indstatcols, "\n'
            '\t\t\t\t\t\t\t "\'\' AS indstatvals, ");\n')
        print(f"  {sl}: indoption -> PG19 + YB indoption")

    # Conflict: dumpACL pg_stat_statements
    elif "data-only skips ACLs" in ours and "pg_stat_statements" in theirs:
        r = ('\t/*\n'
            '\t * YB: pg_stat_statements is a built-in extension in YB (created during\n'
            '\t * initdb). PG doesn\'t dump built-in extensions, so pg_stat_statements is\n'
            '\t * not dumped. Therefore, pg_stat_statements_reset() is not explicitly\n'
            '\t * created. Moreover, the function no longer exists with that signature\n'
            '\t * in PG15 (it gained parameters). So keep this work-around for now,\n'
            '\t * otherwise the restore will fail with:\n'
            '\t * ERROR:  function pg_catalog.pg_stat_statements_reset() does not exist\n'
            '\t * In the future, we may want to follow the typical extension binary upgrade\n'
            '\t * path for pg_stat_statements (create an empty extension and manually\n'
            '\t * create extension objects), and then this work-around can be removed\n'
            '\t * (tracked in GH issue #26566).\n'
            '\t */\n'
            '\tif (IsYugabyteEnabled && dopt->binary_upgrade &&\n'
            '\t\tstrcmp(name, "\\"pg_stat_statements_reset\\"()") == 0)\n'
            '\t\treturn InvalidDumpId;\n'
            '\n'
            '\t/* --data-only skips ACLs *except* large object ACLs */\n')
        print(f"  {sl}: dumpACL -> PG19 + YB pg_stat_statements")

    # Conflict: free partkeydef
    elif "free(partkeydef)" in ours and "freeYbcTablePropertiesIfRequired" in theirs:
        r = ('\t\tfree(partkeydef);\n'
            '\t\tfree(ftoptions);\n'
            '\t\tfree(srvname);\n'
            '\n'
            '\t\tfreeYbcTablePropertiesIfRequired(yb_properties);\n')
        print(f"  {sl}: free partkeydef -> PG19 + YB freeYbcTableProperties")

    # Conflict: print_notnull
    elif "notnull_constrs" in ours and "notnull_islocal" in ours and "inhNotNull" in theirs:
        r = ('\t\t\t\t\t * Not Null constraint --- print it if it is locally\n'
            '\t\t\t\t\t * defined, or if binary upgrade.\n'
            '\t\t\t\t\t * YB: For backups, follow binary-upgrade mode\n'
            '\t\t\t\t\t * for inherited child tables to preserve col order.\n'
            '\t\t\t\t\t * (In the latter case, we\n'
            '\t\t\t\t\t * reset conislocal below.)\n'
            '\t\t\t\t\t */\n'
            '\t\t\t\t\tprint_notnull = (tbinfo->notnull_constrs[j] != NULL &&\n'
            '\t\t\t\t\t\t\t\t\t (tbinfo->notnull_islocal[j] ||\n'
            '\t\t\t\t\t\t\t\t\t  dopt->binary_upgrade ||\n'
            '\t\t\t\t\t\t\t\t\t  tbinfo->ispartition ||\n'
            '\t\t\t\t\t\t\t\t\t  dopt->include_yb_metadata));\n')
        print(f"  {sl}: print_notnull -> PG19 + YB include_yb_metadata")

    if r is not None:
        content = content[:m.start()] + r + content[m.end():]

with open(FILEPATH, "w") as f:
    f.write(content)

remaining = len(re.findall("<<<<<<< ours", content))
print(f"Conflicts remaining: {remaining}")
