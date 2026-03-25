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

    # Conflict: dumpDatabase query
    if "ybQueryDatabaseData" in theirs and "Fetch the database-level" in ours:
        r = ours
        print(f"  {sl}: dumpDatabase -> keep PG19 inline")

    # Conflict: pg_largeobject comment
    elif "pg_largeobject_metadata also comes" in ours and "don't support pg_largeobject" in theirs:
        r = ("\t * pg_largeobject_metadata also comes from the old system intact for\n"
            "\t * upgrades from v16 and newer, so set its relfrozenxids, relminmxids, and\n"
            "\t * relfilenode, too.  pg_upgrade can't copy/link the files from older\n"
            "\t * versions because aclitem (needed by pg_largeobject_metadata.lomacl)\n"
            "\t * changed its storage format in v16.\n"
            "\t *\n"
            "\t * YB: We don't support pg_largeobject and thus don't need to upgrade this\n"
            "\t * table.\n")
        print(f"  {sl}: pg_largeobject -> keep both comments")

    # Conflict: relfilenumber
    elif "RelFileNumberIsValid" in ours and "IsYugabyteEnabled" in theirs and "OidIsValid(relfilenode)" in theirs:
        r = ("\t\tif (RelFileNumberIsValid(entry->relfilenumber) &&\n"
            "\t\t\t(IsYugabyteEnabled || entry->relkind != RELKIND_PARTITIONED_TABLE))\n")
        print(f"  {sl}: relfilenumber -> PG19 + YB IsYugabyteEnabled")

    if r is not None:
        content = content[:m.start()] + r + content[m.end():]

with open(FILEPATH, "w") as f:
    f.write(content)

remaining = len(re.findall("<<<<<<< ours", content))
print(f"Conflicts remaining: {remaining}")
