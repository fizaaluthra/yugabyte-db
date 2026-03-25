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

    # Conflict 0: dumpTablegroup + dumpTableSchema
    if "PQExpBuffer extra = createPQExpBuffer();" in ours and "namecopy" in theirs and "dumpTableSchema" in theirs:
        # Keep YB dumpTablegroup body + freeYbcTablePropertiesIfRequired + dumpTableSchema with PG19 extra
        # But update dumpACL call to PG19 10-param signature (add NULL tag param)
        r = theirs.replace(
            'dumpACL(fout, tginfo->dobj.dumpId, InvalidDumpId, "TABLEGROUP",\n\t\t\t\ttginfo->dobj.name, NULL, NULL, tginfo->rolname, &tginfo->dacl)',
            'dumpACL(fout, tginfo->dobj.dumpId, InvalidDumpId, "TABLEGROUP",\n\t\t\t\ttginfo->dobj.name, NULL, NULL, NULL, tginfo->rolname, &tginfo->dacl)'
        )
        # Add PG19's extra PQExpBuffer to the dumpTableSchema declarations
        r = r.replace(
            "\tPQExpBuffer delq = createPQExpBuffer();\n",
            "\tPQExpBuffer delq = createPQExpBuffer();\n\tPQExpBuffer extra = createPQExpBuffer();\n"
        )
        print(f"  {sl}: dumpTablegroup + dumpTableSchema -> keep both + PG19 extra")

    # Conflict 1: UNLOGGED + primaryKeyIndex + yb_properties
    elif "PostgreSQL 18 has disabled UNLOGGED" in ours and "primaryKeyIndex" in theirs:
        # Take theirs (YB code) but update binary_upgrade_set_pg_class_oids calls to PG19 3-param signature
        # Then append PG19 UNLOGGED comment at end
        r = theirs.replace(
            "binary_upgrade_set_pg_class_oids(fout, q,\n\t\t\t\t\t\t\t\t\t\t\t\t index->dobj.catId.oid, true);",
            "binary_upgrade_set_pg_class_oids(fout, q,\n\t\t\t\t\t\t\t\t\t\t\t\t\t index->dobj.catId.oid);"
        )
        # Append PG19 UNLOGGED comment at the end
        r = r + ("\t\t/*\n"
            "\t\t * PostgreSQL 18 has disabled UNLOGGED for partitioned tables, so\n"
            "\t\t * ignore it when dumping if it was set in this case.\n"
            "\t\t */\n")
        print(f"  {sl}: UNLOGGED + YB primaryKeyIndex + yb_properties -> merged")

    # Conflict 2: dropped columns + inherited columns
    elif "recreate dropped columns" in ours and "YB backups" in theirs:
        # Wrap PG19's batched dropped columns code in YB include_yb_metadata check
        # Keep PG19's inherited columns + notnull fix
        # But also merge with YB's inherited column handling
        yb_guard_start = ("\t\t\t\t\t/*\n"
            "\t\t\t\t\t * For YB backups, we don't need to recreate dropped cols because\n"
            "\t\t\t\t\t * docdb snapshot import can handle such gaps in the col order.\n"
            "\t\t\t\t\t */\n"
            "\t\t\t\t\tif (!dopt->include_yb_metadata)\n"
            "\t\t\t\t\t{\n")
        # Indent the PG19 dropped cols code by one extra tab and wrap in the guard
        # Original PG19 code starts with "if (firstitem)" at same indent level
        pg19_dropped = ours
        # Add the guard and close it, then continue with the rest of PG19 code
        # Split ours at the closing of the dropped columns loop
        # Ours contains: dropped cols loop body + inherited cols + notnull fix
        # We want to wrap only the dropped cols part in the YB guard
        
        # Find where the dropped cols handling ends - it's at "else if (!tbinfo->attislocal"
        # in theirs. In ours, it's after the DROP COLUMN append.
        # The whole ours block goes from dropped cols through notnull fix.
        # Let me just wrap the entire dropped cols in include_yb_metadata check,
        # keep inherited cols + notnull fix from PG19
        
        # Actually the cleanest approach: take PG19's code but wrap dropped cols in YB guard
        lines = ours.split("\n")
        # Find the boundary between dropped cols and inherited cols sections
        new_lines = []
        in_dropped = True
        for line in lines:
            if "Fix up inherited columns" in line:
                # Close the YB guard before starting inherited columns section
                in_dropped = False
            if in_dropped:
                new_lines.append(line)
            else:
                new_lines.append(line)
        
        # Simpler: just take ours as-is but prepend YB guard around dropped cols part
        # Find where dropped cols processing starts (the if(firstitem) block)
        # and where it ends (before "Fix up inherited columns")
        
        idx_inherited = ours.find("\t\t\t/*\n\t\t\t * Fix up inherited columns")
        if idx_inherited < 0:
            # Try alternate
            idx_inherited = ours.find("Fix up inherited columns")
        
        if idx_inherited > 0:
            dropped_part = ours[:idx_inherited]
            rest_part = ours[idx_inherited:]
            r = yb_guard_start + dropped_part + "\t\t\t\t\t}\n" + rest_part
        else:
            # Fallback: just take ours
            r = ours
            print(f"  WARNING: couldn't split dropped cols from rest")
        
        print(f"  {sl}: dropped columns -> PG19 batched + YB include_yb_metadata guard")

    # Conflict 3: PRIMARY KEY / UNIQUE + USING INDEX
    elif "PRIMARY KEY" in ours and "indnullsnotdistinct" in ours and "dump_index_for_constraint" in theirs:
        r = ('\t\t\tappendPQExpBufferStr(q,\n'
            '\t\t\t\t\t\t\t\t coninfo->contype == \'p\' ? "PRIMARY KEY" : "UNIQUE");\n'
            '\n'
            '\t\t\t/*\n'
            '\t\t\t * YB: See note on #13603 #24260 above.\n'
            '\t\t\t */\n'
            '\t\t\tif (dump_index_for_constraint)\n')
        print(f"  {sl}: PRIMARY KEY/UNIQUE -> PG19 + YB USING INDEX")

    # Conflict 4: conperiod + YB else branch
    elif "conperiod" in ours and "WITHOUT OVERLAPS" in ours and "non-unique constraint" in theirs:
        r = ('\t\t\tif (coninfo->conperiod)\n'
            '\t\t\t\tappendPQExpBufferStr(q, " WITHOUT OVERLAPS");\n'
            '\n'
            '\t\t\t/*\n'
            '\t\t\t * YB: If a table has a non-unique constraint or does not have an\n'
            '\t\t\t * index definition, the original ALTER TABLE ADD CONSTRAINT\n'
            '\t\t\t * command is used and the rest of the query is constructed.\n'
            '\t\t\t */\n'
            '\t\t\telse\n'
            '\t\t\t{\n'
            '\t\t\t\t/*\n'
            '\t\t\t\t * PRIMARY KEY constraints should not be using NULLS NOT DISTINCT\n'
            '\t\t\t\t * indexes. Being able to create this was fixed, but we need to\n'
            '\t\t\t\t * make the index distinct in order to be able to restore the\n'
            '\t\t\t\t * dump.\n'
            '\t\t\t\t */\n'
            '\t\t\t\tif (indxinfo->indnullsnotdistinct && coninfo->contype != \'p\')\n'
            '\t\t\t\t\tappendPQExpBufferStr(q, " NULLS NOT DISTINCT");\n'
            '\t\t\t\tappendPQExpBufferStr(q, " (");\n'
            '\t\t\t\tfor (k = 0; k < indxinfo->indnkeyattrs; k++)\n'
            '\t\t\t\t{\n'
            '\t\t\t\t\tint\t\t\tindkey = (int) indxinfo->indkeys[k];\n'
            '\t\t\t\t\tconst char *attname;\n')
        print(f"  {sl}: conperiod + YB else -> merged")

    # Conflict 5: read_dump_filters + YB helper functions
    elif "read_dump_filters" in ours and "ybQueryDatabaseData" in theirs:
        # Keep PG19's read_dump_filters + all YB helpers with updated ybQueryDatabaseData
        # Find remaining YB funcs after getDatabaseOid
        idx_yb_table_props = theirs.find("/*\n * Load the YB table properties")
        if idx_yb_table_props < 0:
            idx_yb_table_props = theirs.find("getYbTablePropertiesAndReloptions")
        
        remaining_yb = ""
        if idx_yb_table_props > 0:
            remaining_yb = theirs[idx_yb_table_props:]
        
        yb_query_func = (
            '\nstatic PGresult *\n'
            'ybQueryDatabaseData(Archive *fout, PQExpBuffer dbQry)\n'
            '{\n'
            '\t/*\n'
            '\t * Fetch the database-level properties for this database.\n'
            '\t */\n'
            '\tappendPQExpBufferStr(dbQry, "SELECT tableoid, oid, datname, "\n'
            '\t\t\t\t\t "datdba, "\n'
            '\t\t\t\t\t "pg_encoding_to_char(encoding) AS encoding, "\n'
            '\t\t\t\t\t "datcollate, datctype, datfrozenxid, "\n'
            '\t\t\t\t\t "datacl, acldefault(\'d\', datdba) AS acldefault, "\n'
            '\t\t\t\t\t "datistemplate, datconnlimit, ");\n'
            '\tif (fout->remoteVersion >= 90300)\n'
            '\t\tappendPQExpBufferStr(dbQry, "datminmxid, ");\n'
            '\telse\n'
            '\t\tappendPQExpBufferStr(dbQry, "0 AS datminmxid, ");\n'
            '\tif (fout->remoteVersion >= 170000)\n'
            '\t\tappendPQExpBufferStr(dbQry, "datlocprovider, datlocale, datcollversion, ");\n'
            '\telse if (fout->remoteVersion >= 150000)\n'
            '\t\tappendPQExpBufferStr(dbQry, "datlocprovider, daticulocale AS datlocale, datcollversion, ");\n'
            '\telse\n'
            '\t\tappendPQExpBufferStr(dbQry, "\'c\' AS datlocprovider, NULL AS datlocale, NULL AS datcollversion, ");\n'
            '\tif (fout->remoteVersion >= 160000)\n'
            '\t\tappendPQExpBufferStr(dbQry, "daticurules, ");\n'
            '\telse\n'
            '\t\tappendPQExpBufferStr(dbQry, "NULL AS daticurules, ");\n'
            '\tappendPQExpBufferStr(dbQry,\n'
            '\t\t\t\t\t "(SELECT spcname FROM pg_tablespace t WHERE t.oid = dattablespace) AS tablespace, "\n'
            '\t\t\t\t\t "shobj_description(oid, \'pg_database\') AS description "\n'
            '\t\t\t\t\t "FROM pg_database "\n'
            '\t\t\t\t\t "WHERE datname = current_database()");\n'
            '\n'
            '\treturn ExecuteSqlQueryForSingleRow(fout, dbQry->data);\n'
            '}\n'
            '\n'
            'static Oid\n'
            'getDatabaseOid(Archive *fout)\n'
            '{\n'
            '\tpg_log_info("reading database id");\n'
            '\n'
            '\tPQExpBuffer dbQry = createPQExpBuffer();\n'
            '\tPGresult   *res = ybQueryDatabaseData(fout, dbQry);\n'
            '\tint\t\t\ti_oid = PQfnumber(res, "oid");\n'
            '\tOid\t\t\tdb_oid = atooid(PQgetvalue(res, 0, i_oid));\n'
            '\n'
            '\tPQclear(res);\n'
            '\tdestroyPQExpBuffer(dbQry);\n'
            '\treturn db_oid;\n'
            '}\n\n'
        )
        
        r = ours + yb_query_func + remaining_yb
        print(f"  {sl}: read_dump_filters + YB helpers -> keep both")

    if r is not None:
        content = content[:m.start()] + r + content[m.end():]

with open(FILEPATH, "w") as f:
    f.write(content)

remaining = len(re.findall("<<<<<<< ours", content))
print(f"Conflicts remaining: {remaining}")
