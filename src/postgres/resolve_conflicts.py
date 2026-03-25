#!/usr/bin/env python3
"""Resolve all remaining merge conflicts in pg_dump.c"""
import re, sys

FILEPATH = 'src/bin/pg_dump/pg_dump.c'

with open(FILEPATH, 'r') as f:
    content = f.read()

pattern = r'<<<<<<< ours\n(.*?)=======\n(.*?)>>>>>>> theirs\n'
conflicts = list(re.finditer(pattern, content, re.DOTALL))
print(f"Found {len(conflicts)} conflicts to resolve")

# Process in reverse order to preserve positions
for i in range(len(conflicts) - 1, -1, -1):
    m = conflicts[i]
    ours = m.group(1)
    theirs = m.group(2)
    start_line = content[:m.start()].count('\n') + 1
    ctx_before = content[max(0, m.start()-300):m.start()]

    resolution = None
    desc = "UNHANDLED"

    # ---- Conflict 0: dumpDatabase query ----
    if 'ybQueryDatabaseData' in theirs and 'Fetch the database-level properties' in ours:
        # Keep PG19 inline query
        resolution = ours
        desc = "dumpDatabase query -> keep PG19 inline"

    # ---- Conflict 1: pg_largeobject comment ----
    elif 'pg_largeobject_metadata also comes' in ours and "don't support pg_largeobject" in theirs:
        resolution = ("\t * pg_largeobject_metadata also comes from the old system intact for\n"
            "\t * upgrades from v16 and newer, so set its relfrozenxids, relminmxids, and\n"
            "\t * relfilenode, too.  pg_upgrade can't copy/link the files from older\n"
            "\t * versions because aclitem (needed by pg_largeobject_metadata.lomacl)\n"
            "\t * changed its storage format in v16.\n"
            "\t *\n"
            "\t * YB: We don't support pg_largeobject and thus don't need to upgrade this\n"
            "\t * table.\n")
        desc = "pg_largeobject comment -> keep both"

    # ---- Conflict 2: relfilenumber check ----
    elif 'RelFileNumberIsValid' in ours and 'IsYugabyteEnabled' in theirs and 'OidIsValid(relfilenode)' in theirs:
        resolution = ("\t\tif (RelFileNumberIsValid(entry->relfilenumber) &&\n"
            "\t\t\t(IsYugabyteEnabled || entry->relkind != RELKIND_PARTITIONED_TABLE))\n")
        desc = "relfilenumber -> PG19 naming + YB IsYugabyteEnabled"

    # ---- Conflict 3: indoption in index query ----
    elif 'indoption' in theirs and 'inh.inhparent AS parentidx' in ours:
        resolution = ("\t\tappendPQExpBufferStr(query,\n"
            "\t\t\t\t\t\t\t \"i.indoption, \"\t/* YB */\n"
            "\t\t\t\t\t\t\t \"inh.inhparent AS parentidx, \"\n"
            "\t\t\t\t\t\t\t \"i.indnkeyatts AS indnkeyatts, \"\n"
            "\t\t\t\t\t\t\t \"i.indnatts AS indnatts, \"\n"
            "\t\t\t\t\t\t\t \"(SELECT pg_catalog.array_agg(attnum ORDER BY attnum) \"\n"
            "\t\t\t\t\t\t\t \"  FROM pg_catalog.pg_attribute \"\n"
            "\t\t\t\t\t\t\t \"  WHERE attrelid = i.indexrelid AND \"\n"
            "\t\t\t\t\t\t\t \"    attstattarget >= 0) AS indstatcols, \"\n"
            "\t\t\t\t\t\t\t \"(SELECT pg_catalog.array_agg(attstattarget ORDER BY attnum) \"\n"
            "\t\t\t\t\t\t\t \"  FROM pg_catalog.pg_attribute \"\n"
            "\t\t\t\t\t\t\t \"  WHERE attrelid = i.indexrelid AND \"\n"
            "\t\t\t\t\t\t\t \"    attstattarget >= 0) AS indstatvals, \");\n"
            "\telse\n"
            "\t\tappendPQExpBufferStr(query,\n"
            "\t\t\t\t\t\t\t \"i.indoption, \"\t/* YB */\n"
            "\t\t\t\t\t\t\t \"0 AS parentidx, \"\n"
            "\t\t\t\t\t\t\t \"i.indnatts AS indnkeyatts, \"\n"
            "\t\t\t\t\t\t\t \"i.indnatts AS indnatts, \"\n"
            "\t\t\t\t\t\t\t \"'' AS indstatcols, \"\n"
            "\t\t\t\t\t\t\t \"'' AS indstatvals, \");\n")
        desc = "index query -> PG19 + YB indoption"

    # ---- Conflict 4: dumpACL pg_stat_statements ----
    elif 'data-only skips ACLs' in ours and 'pg_stat_statements' in theirs:
        resolution = ("\t/*\n"
            "\t * YB: pg_stat_statements is a built-in extension in YB (created during\n"
            "\t * initdb). PG doesn't dump built-in extensions, so pg_stat_statements is\n"
            "\t * not dumped. Therefore, pg_stat_statements_reset() is not explicitly\n"
            "\t * created. Moreover, the function no longer exists with that signature\n"
            "\t * in PG15 (it gained parameters). So keep this work-around for now,\n"
            "\t * otherwise the restore will fail with:\n"
            "\t * ERROR:  function pg_catalog.pg_stat_statements_reset() does not exist\n"
            "\t * In the future, we may want to follow the typical extension binary upgrade\n"
            "\t * path for pg_stat_statements (create an empty extension and manually\n"
            "\t * create extension objects), and then this work-around can be removed\n"
            "\t * (tracked in GH issue #26566).\n"
            "\t */\n"
            "\tif (IsYugabyteEnabled && dopt->binary_upgrade &&\n"
            "\t\tstrcmp(name, \"\\\"pg_stat_statements_reset\\\"()\") == 0)\n"
            "\t\treturn InvalidDumpId;\n"
            "\n"
            "\t/* --data-only skips ACLs *except* large object ACLs */\n")
        desc = "dumpACL -> PG19 comment + YB pg_stat_statements"

    # ---- Conflict 5: dumpTablegroup + dumpTableSchema ----
    elif 'PQExpBuffer extra = createPQExpBuffer();' in ours and 'namecopy' in theirs and 'dumpTableSchema' in theirs:
        resolution = ("\tchar\t   *namecopy;\n"
            "\n"
            "\tif (!tginfo->dobj.dump || !dopt->dumpSchema)\n"
            "\t\treturn;\n"
            "\n"
            "\t/*\n"
            "\t * Set the next tablegroup oid to be used in yb_binary_restore mode.\n"
            "\t * It's necessary to reuse the old tablegroup oid during the backup\n"
            "\t * restoring to match tablegroup parent table.\n"
            "\t */\n"
            "\tappendPQExpBufferStr(q,\n"
            "\t\t\t\t\t\t \"\\n-- For YB tablegroup backup, must preserve pg_yb_tablegroup oid\\n\");\n"
            "\tappendPQExpBuffer(q,\n"
            "\t\t\t\t\t  \"SELECT pg_catalog.binary_upgrade_set_next_tablegroup_oid('%u'::pg_catalog.oid);\\n\",\n"
            "\t\t\t\t\t  tginfo->dobj.catId.oid);\n"
            "\n"
            "\tnamecopy = pg_strdup(fmtId(tginfo->dobj.name));\n"
            "\n"
            "\tappendPQExpBuffer(q, \"CREATE TABLEGROUP %s\", namecopy);\n"
            "\tif (nonemptyReloptions(tginfo->grpoptions))\n"
            "\t{\n"
            "\t\tappendPQExpBufferStr(q, \"\\nWITH (\");\n"
            "\t\tappendReloptionsArrayAH(q, tginfo->grpoptions, \"\", fout);\n"
            "\t\tappendPQExpBufferStr(q, \")\");\n"
            "\t}\n"
            "\tappendPQExpBufferStr(q, \";\\n\");\n"
            "\n"
            "\tappendPQExpBuffer(delq, \"DROP TABLEGROUP %s;\\n\", namecopy);\n"
            "\n"
            "\tif (tginfo->dobj.dump & DUMP_COMPONENT_DEFINITION)\n"
            "\t\tArchiveEntry(fout,\n"
            "\t\t\t\t\t tginfo->dobj.catId,\t/* catalog ID */\n"
            "\t\t\t\t\t tginfo->dobj.dumpId,\t/* dump ID */\n"
            "\t\t\t\t\t ARCHIVE_OPTS(.tag = tginfo->dobj.name, /* Name */\n"
            "\t\t\t\t\t\t\t\t  .namespace = NULL,\t/* Namespace */\n"
            "\t\t\t\t\t\t\t\t  .tablespace = tginfo->grptablespace,\t/* Tablespace */\n"
            "\t\t\t\t\t\t\t\t  .owner = tginfo->rolname, /* Owner */\n"
            "\t\t\t\t\t\t\t\t  .description = \"TABLEGROUP\",\t/* Desc */\n"
            "\t\t\t\t\t\t\t\t  .section = SECTION_PRE_DATA,\t/* Section */\n"
            "\t\t\t\t\t\t\t\t  .createStmt = q->data,\t/* Create */\n"
            "\t\t\t\t\t\t\t\t  .dropStmt = delq->data,\t/* Del */\n"
            "\t\t\t\t\t\t\t\t  .copyStmt = NULL, /* Copy */\n"
            "\t\t\t\t\t\t\t\t  .deps = NULL, /* Deps */\n"
            "\t\t\t\t\t\t\t\t  .nDeps = 0,\t/* # Deps */\n"
            "\t\t\t\t\t\t\t\t  .dumpFn = NULL,\t/* Dumper */\n"
            "\t\t\t\t\t\t\t\t  .dumpArg = NULL));\t/* Dumper Arg */\n"
            "\n"
            "\tif (tginfo->dobj.dump & DUMP_COMPONENT_ACL)\n"
            "\t\tdumpACL(fout, tginfo->dobj.dumpId, InvalidDumpId, \"TABLEGROUP\",\n"
            "\t\t\t\ttginfo->dobj.name, NULL, NULL, NULL, tginfo->rolname, &tginfo->dacl);\n"
            "\n"
            "\tdestroyPQExpBuffer(q);\n"
            "\tdestroyPQExpBuffer(delq);\n"
            "\tfree(namecopy);\n"
            "}\n"
            "\n"
            "static void\n"
            "freeYbcTablePropertiesIfRequired(YbcTableProperties yb_properties)\n"
            "{\n"
            "\tif (!yb_properties)\n"
            "\t\treturn;\n"
            "\n"
            "\tif (yb_properties->tablegroup_name)\n"
            "\t\tfree(yb_properties->tablegroup_name);\n"
            "\tfree(yb_properties);\n"
            "}\n"
            "\n"
            "/*\n"
            " * dumpTableSchema\n"
            " *\t  write the declaration (not data) of one user-defined table or view\n"
            " */\n"
            "static void\n"
            "dumpTableSchema(Archive *fout, const TableInfo *tbinfo)\n"
            "{\n"
            "\tDumpOptions *dopt = fout->dopt;\n"
            "\tPQExpBuffer q = createPQExpBuffer();\n"
            "\tPQExpBuffer delq = createPQExpBuffer();\n"
            "\tPQExpBuffer extra = createPQExpBuffer();\n")
        desc = "dumpTablegroup + dumpTableSchema -> keep both + PG19 extra"

    # ---- Conflict 6: UNLOGGED + YB primaryKeyIndex + yb_properties ----
    elif 'PostgreSQL 18 has disabled UNLOGGED' in ours and 'primaryKeyIndex' in theirs:
        resolution = ("\t\t\t/*\n"
            "\t\t\t * YB: We may create a primary key index as part of the CREATE TABLE\n"
            "\t\t\t * statement we generate here; accordingly, set things up so we\n"
            "\t\t\t * will set its OID correctly in binary update mode.\n"
            "\t\t\t */\n"
            "\t\t\tif (tbinfo->primaryKeyIndex)\n"
            "\t\t\t{\n"
            "\t\t\t\tIndxInfo   *index = tbinfo->primaryKeyIndex;\n"
            "\n"
            "\t\t\t\tbinary_upgrade_set_pg_class_oids(fout, q,\n"
            "\t\t\t\t\t\t\t\t\t\t\t\t\t index->dobj.catId.oid);\n"
            "\t\t\t}\n"
            "\t\t}\n"
            "\n"
            "\t\t/* Get the table properties from YB, if relevant. */\n"
            "\t\tYbcTableProperties yb_properties = NULL;\n"
            "\n"
            "\t\tif ((dopt->include_yb_metadata || dopt->binary_upgrade) &&\n"
            "\t\t\t(tbinfo->relkind == RELKIND_RELATION || tbinfo->relkind == RELKIND_INDEX\n"
            "\t\t\t || tbinfo->relkind == RELKIND_MATVIEW || tbinfo->relkind == RELKIND_PARTITIONED_TABLE))\n"
            "\t\t{\n"
            "\t\t\tyb_properties = (YbcTableProperties) pg_malloc0(sizeof(YbcTablePropertiesData));\n"
            "\t\t}\n"
            "\t\tPQExpBuffer yb_reloptions = createPQExpBuffer();\n"
            "\n"
            "\t\tgetYbTablePropertiesAndReloptions(fout, yb_properties, yb_reloptions,\n"
            "\t\t\t\t\t\t\t\t\t\t\t  tbinfo->dobj.catId.oid,\n"
            "\t\t\t\t\t\t\t\t\t\t\t  tbinfo->dobj.name, tbinfo->relkind);\n"
            "\n"
            "\t\t/*\n"
            "\t\t * YB: Colocation backup: preserve implicit tablegroup oid.\n"
            "\t\t * Legacy colocated databases skip this step.\n"
            "\t\t */\n"
            "\t\tif (is_colocated_database && !is_legacy_colocated_database\n"
            "\t\t\t&& (tbinfo->relkind == RELKIND_RELATION || tbinfo->relkind == RELKIND_MATVIEW\n"
            "\t\t\t\t|| tbinfo->relkind == RELKIND_PARTITIONED_TABLE) && yb_properties\n"
            "\t\t\t&& yb_properties->is_colocated)\n"
            "\t\t{\n"
            "\t\t\t/*\n"
            "\t\t\t * Set the next implicit tablegroup oid in a colocated database.\n"
            "\t\t\t * It's mandatory to reuse the old tablegroup oid to match tablegroup parent table\n"
            "\t\t\t * in import_snapshot step during restoring a backup.\n"
            "\t\t\t */\n"
            "\t\t\tappendPQExpBufferStr(q,\n"
            "\t\t\t\t\t\t\t\t \"\\n-- For YB colocation backup, must preserve implicit tablegroup pg_yb_tablegroup oid\\n\");\n"
            "\t\t\tappendPQExpBuffer(q,\n"
            "\t\t\t\t\t\t\t  \"SELECT pg_catalog.binary_upgrade_set_next_tablegroup_oid('%u'::pg_catalog.oid);\\n\",\n"
            "\t\t\t\t\t\t\t  yb_properties->tablegroup_oid);\n"
            "\n"
            "\t\t\tif (strcmp(yb_properties->tablegroup_name, \"default\") == 0)\n"
            "\t\t\t{\n"
            "\t\t\t\tappendPQExpBufferStr(q,\n"
            "\t\t\t\t\t\t\t\t\t \"\\n-- For YB colocation backup without tablespace information, must preserve default tablegroup tables\\n\");\n"
            "\t\t\t\tappendPQExpBuffer(q,\n"
            "\t\t\t\t\t\t\t\t  \"SELECT pg_catalog.binary_upgrade_set_next_tablegroup_default(true);\\n\");\n"
            "\t\t\t}\n"
            "\t\t}\n"
            "\n"
            "\t\t/*\n"
            "\t\t * PostgreSQL 18 has disabled UNLOGGED for partitioned tables, so\n"
            "\t\t * ignore it when dumping if it was set in this case.\n"
            "\t\t */\n")
        desc = "UNLOGGED + YB primaryKeyIndex + yb_properties -> merged"

    # ---- Conflict 7: print_notnull ----
    elif 'notnull_constrs' in ours and 'notnull_islocal' in ours and 'inhNotNull' in theirs:
        resolution = ("\t\t\t\t\t * Not Null constraint --- print it if it is locally\n"
            "\t\t\t\t\t * defined, or if binary upgrade.\n"
            "\t\t\t\t\t * YB: For backups, follow binary-upgrade mode\n"
            "\t\t\t\t\t * for inherited child tables to preserve col order.\n"
            "\t\t\t\t\t * (In the latter case, we\n"
            "\t\t\t\t\t * reset conislocal below.)\n"
            "\t\t\t\t\t */\n"
            "\t\t\t\t\tprint_notnull = (tbinfo->notnull_constrs[j] != NULL &&\n"
            "\t\t\t\t\t\t\t\t\t (tbinfo->notnull_islocal[j] ||\n"
            "\t\t\t\t\t\t\t\t\t  dopt->binary_upgrade ||\n"
            "\t\t\t\t\t\t\t\t\t  tbinfo->ispartition ||\n"
            "\t\t\t\t\t\t\t\t\t  dopt->include_yb_metadata));\n")
        desc = "print_notnull -> PG19 + YB include_yb_metadata"

    # ---- Conflict 8: dropped columns recreation ----
    elif 'recreate dropped columns' in ours and 'YB backups' in theirs:
        resolution = ("\t\t\t\t\t/*\n"
            "\t\t\t\t\t * For YB backups, we don't need to recreate dropped cols because\n"
            "\t\t\t\t\t * docdb snapshot import can handle such gaps in the col order.\n"
            "\t\t\t\t\t */\n"
            "\t\t\t\t\tif (!dopt->include_yb_metadata)\n"
            "\t\t\t\t\t{\n"
            "\t\t\t\t\t\tif (firstitem)\n"
            "\t\t\t\t\t\t{\n"
            "\t\t\t\t\t\t\tappendPQExpBufferStr(q, \"\\n-- For binary upgrade, recreate dropped columns.\\n\"\n"
            "\t\t\t\t\t\t\t\t\t\t\t\t \"UPDATE pg_catalog.pg_attribute\\n\"\n"
            "\t\t\t\t\t\t\t\t\t\t\t\t \"SET attlen = v.dlen, \"\n"
            "\t\t\t\t\t\t\t\t\t\t\t\t \"attalign = v.dalign, \"\n"
            "\t\t\t\t\t\t\t\t\t\t\t\t \"attbyval = false\\n\"\n"
            "\t\t\t\t\t\t\t\t\t\t\t\t \"FROM (VALUES \");\n"
            "\t\t\t\t\t\t\tfirstitem = false;\n"
            "\t\t\t\t\t\t}\n"
            "\t\t\t\t\t\telse\n"
            "\t\t\t\t\t\t\tappendPQExpBufferStr(q, \",\\n             \");\n"
            "\t\t\t\t\t\tappendPQExpBufferChar(q, '(');\n"
            "\t\t\t\t\t\tappendStringLiteralAH(q, tbinfo->attnames[j], fout);\n"
            "\t\t\t\t\t\tappendPQExpBuffer(q, \", %d, '%c')\",\n"
            "\t\t\t\t\t\t\t\t\t\t  tbinfo->attlen[j],\n"
            "\t\t\t\t\t\t\t\t\t\t  tbinfo->attalign[j]);\n"
            "\t\t\t\t\t\t/* The ALTER ... DROP COLUMN commands must come after */\n"
            "\t\t\t\t\t\tappendPQExpBuffer(extra, \"ALTER %sTABLE ONLY %s \",\n"
            "\t\t\t\t\t\t\t\t\t\t  foreign, qualrelname);\n"
            "\t\t\t\t\t\tappendPQExpBuffer(extra, \"DROP COLUMN %s;\\n\",\n"
            "\t\t\t\t\t\t\t\t\t\t  fmtId(tbinfo->attnames[j]));\n"
            "\t\t\t\t\t}\n"
            "\t\t\t\t}\n"
            "\t\t\t}\n"
            "\t\t\tif (!firstitem)\n"
            "\t\t\t{\n"
            "\t\t\t\tappendPQExpBufferStr(q, \") v(dname, dlen, dalign)\\n\"\n"
            "\t\t\t\t\t\t\t\t\t \"WHERE attrelid = \");\n"
            "\t\t\t\tappendStringLiteralAH(q, qualrelname, fout);\n"
            "\t\t\t\tappendPQExpBufferStr(q, \"::pg_catalog.regclass\\n\"\n"
            "\t\t\t\t\t\t\t\t\t \"  AND attname = v.dname;\\n\");\n"
            "\t\t\t\t/* Now we can issue the actual DROP COLUMN commands */\n"
            "\t\t\t\tappendBinaryPQExpBuffer(q, extra->data, extra->len);\n"
            "\t\t\t}\n"
            "\n"
            "\t\t\t/*\n"
            "\t\t\t * Fix up inherited columns.  As above, do the pg_attribute\n"
            "\t\t\t * manipulations in a single SQL command.\n"
            "\t\t\t */\n"
            "\t\t\tfirstitem = true;\n"
            "\t\t\tfor (j = 0; j < tbinfo->numatts; j++)\n"
            "\t\t\t{\n"
            "\t\t\t\tif (!tbinfo->attisdropped[j] &&\n"
            "\t\t\t\t\t!tbinfo->attislocal[j])\n"
            "\t\t\t\t{\n"
            "\t\t\t\t\tif (firstitem)\n"
            "\t\t\t\t\t{\n"
            "\t\t\t\t\t\tappendPQExpBufferStr(q, \"\\n-- For binary upgrade, recreate inherited columns.\\n\");\n"
            "\t\t\t\t\t\tappendPQExpBufferStr(q, \"UPDATE pg_catalog.pg_attribute\\n\"\n"
            "\t\t\t\t\t\t\t\t\t\t\t \"SET attislocal = false\\n\"\n"
            "\t\t\t\t\t\t\t\t\t\t\t \"WHERE attrelid = \");\n"
            "\t\t\t\t\t\tappendStringLiteralAH(q, qualrelname, fout);\n"
            "\t\t\t\t\t\tappendPQExpBufferStr(q, \"::pg_catalog.regclass\\n\"\n"
            "\t\t\t\t\t\t\t\t\t\t\t \"  AND attname IN (\");\n"
            "\t\t\t\t\t\tfirstitem = false;\n"
            "\t\t\t\t\t}\n"
            "\t\t\t\t\telse\n"
            "\t\t\t\t\t\tappendPQExpBufferStr(q, \", \");\n"
            "\t\t\t\t\tappendStringLiteralAH(q, tbinfo->attnames[j], fout);\n"
            "\t\t\t\t}\n"
            "\t\t\t}\n"
            "\t\t\tif (!firstitem)\n"
            "\t\t\t\tappendPQExpBufferStr(q, \");\\n\");\n"
            "\n"
            "\t\t\t/*\n"
            "\t\t\t * Fix up not-null constraints that come from inheritance.  As\n"
            "\t\t\t * above, do the pg_constraint manipulations in a single SQL\n"
            "\t\t\t * command.  (Actually, two in special cases, if we're doing an\n"
            "\t\t\t * upgrade from < 18).\n"
            "\t\t\t */\n"
            "\t\t\tfirstitem = true;\n"
            "\t\t\tfirstitem_extra = true;\n"
            "\t\t\tresetPQExpBuffer(extra);\n"
            "\t\t\tfor (j = 0; j < tbinfo->numatts; j++)\n"
            "\t\t\t{\n"
            "\t\t\t\t/*\n"
            "\t\t\t\t * If a not-null constraint comes from inheritance, reset\n"
            "\t\t\t\t * conislocal.  The inhcount is fixed by ALTER TABLE INHERIT,\n"
            "\t\t\t\t * below.  Special hack: in versions < 18, columns with no\n"
            "\t\t\t\t * local definition need their constraint to be matched by\n"
            "\t\t\t\t * column number in conkeys instead of by constraint name,\n"
            "\t\t\t\t * because the latter is not available.  (We distinguish the\n"
            "\t\t\t\t * case because the constraint name is the empty string.)\n"
            "\t\t\t\t */\n"
            "\t\t\t\tif (tbinfo->notnull_constrs[j] != NULL &&\n"
            "\t\t\t\t\t!tbinfo->notnull_islocal[j])\n")
        desc = "dropped columns -> PG19 batched + YB include_yb_metadata"

    # ---- Conflict 9: free partkeydef ----
    elif 'free(partkeydef)' in ours and 'freeYbcTablePropertiesIfRequired' in theirs:
        resolution = ("\t\tfree(partkeydef);\n"
            "\t\tfree(ftoptions);\n"
            "\t\tfree(srvname);\n"
            "\n"
            "\t\tfreeYbcTablePropertiesIfRequired(yb_properties);\n")
        desc = "free partkeydef -> PG19 + YB freeYbcTableProperties"

    # ---- Conflict 10: PRIMARY KEY / UNIQUE + USING INDEX ----
    elif 'PRIMARY KEY' in ours and 'NULLS NOT DISTINCT' in ours and 'dump_index_for_constraint' in theirs:
        resolution = ("\t\t\tappendPQExpBufferStr(q,\n"
            "\t\t\t\t\t\t\t\t coninfo->contype == 'p' ? \"PRIMARY KEY\" : \"UNIQUE\");\n"
            "\n"
            "\t\t\t/*\n"
            "\t\t\t * YB: See note on #13603 #24260 above.\n"
            "\t\t\t */\n"
            "\t\t\tif (dump_index_for_constraint)\n")
        desc = "PRIMARY KEY/UNIQUE -> PG19 + YB USING INDEX"

    # ---- Conflict 11: conperiod + YB else branch ----
    elif 'conperiod' in ours and 'WITHOUT OVERLAPS' in ours and 'non-unique constraint' in theirs:
        resolution = ("\t\t\tif (coninfo->conperiod)\n"
            "\t\t\t\tappendPQExpBufferStr(q, \" WITHOUT OVERLAPS\");\n"
            "\n"
            "\t\t\t/*\n"
            "\t\t\t * YB: If a table has a non-unique constraint or does not have an\n"
            "\t\t\t * index definition, the original ALTER TABLE ADD CONSTRAINT\n"
            "\t\t\t * command is used and the rest of the query is constructed.\n"
            "\t\t\t */\n"
            "\t\t\telse\n"
            "\t\t\t{\n"
            "\t\t\t\t/*\n"
            "\t\t\t\t * PRIMARY KEY constraints should not be using NULLS NOT DISTINCT\n"
            "\t\t\t\t * indexes. Being able to create this was fixed, but we need to\n"
            "\t\t\t\t * make the index distinct in order to be able to restore the\n"
            "\t\t\t\t * dump.\n"
            "\t\t\t\t */\n"
            "\t\t\t\tif (indxinfo->indnullsnotdistinct && coninfo->contype != 'p')\n"
            "\t\t\t\t\tappendPQExpBufferStr(q, \" NULLS NOT DISTINCT\");\n"
            "\t\t\t\tappendPQExpBufferStr(q, \" (\");\n"
            "\t\t\t\tfor (k = 0; k < indxinfo->indnkeyattrs; k++)\n"
            "\t\t\t\t{\n"
            "\t\t\t\t\tint\t\t\tindkey = (int) indxinfo->indkeys[k];\n"
            "\t\t\t\t\tconst char *attname;\n")
        desc = "conperiod + YB else branch -> merged"

    # ---- Conflict 12: read_dump_filters + YB helper functions ----
    elif 'read_dump_filters' in ours and 'ybQueryDatabaseData' in theirs:
        # Keep PG19's read_dump_filters AND add all YB helper functions
        # Update ybQueryDatabaseData with PG19's query
        yb_funcs = (
            "\nstatic PGresult *\n"
            "ybQueryDatabaseData(Archive *fout, PQExpBuffer dbQry)\n"
            "{\n"
            "\t/*\n"
            "\t * Fetch the database-level properties for this database.\n"
            "\t */\n"
            "\tappendPQExpBufferStr(dbQry, \"SELECT tableoid, oid, datname, \"\n"
            "\t\t\t\t\t \"datdba, \"\n"
            "\t\t\t\t\t \"pg_encoding_to_char(encoding) AS encoding, \"\n"
            "\t\t\t\t\t \"datcollate, datctype, datfrozenxid, \"\n"
            "\t\t\t\t\t \"datacl, acldefault('d', datdba) AS acldefault, \"\n"
            "\t\t\t\t\t \"datistemplate, datconnlimit, \");\n"
            "\tif (fout->remoteVersion >= 90300)\n"
            "\t\tappendPQExpBufferStr(dbQry, \"datminmxid, \");\n"
            "\telse\n"
            "\t\tappendPQExpBufferStr(dbQry, \"0 AS datminmxid, \");\n"
            "\tif (fout->remoteVersion >= 170000)\n"
            "\t\tappendPQExpBufferStr(dbQry, \"datlocprovider, datlocale, datcollversion, \");\n"
            "\telse if (fout->remoteVersion >= 150000)\n"
            "\t\tappendPQExpBufferStr(dbQry, \"datlocprovider, daticulocale AS datlocale, datcollversion, \");\n"
            "\telse\n"
            "\t\tappendPQExpBufferStr(dbQry, \"'c' AS datlocprovider, NULL AS datlocale, NULL AS datcollversion, \");\n"
            "\tif (fout->remoteVersion >= 160000)\n"
            "\t\tappendPQExpBufferStr(dbQry, \"daticurules, \");\n"
            "\telse\n"
            "\t\tappendPQExpBufferStr(dbQry, \"NULL AS daticurules, \");\n"
            "\tappendPQExpBufferStr(dbQry,\n"
            "\t\t\t\t\t \"(SELECT spcname FROM pg_tablespace t WHERE t.oid = dattablespace) AS tablespace, \"\n"
            "\t\t\t\t\t \"shobj_description(oid, 'pg_database') AS description \"\n"
            "\t\t\t\t\t \"FROM pg_database \"\n"
            "\t\t\t\t\t \"WHERE datname = current_database()\");\n"
            "\n"
            "\treturn ExecuteSqlQueryForSingleRow(fout, dbQry->data);\n"
            "}\n"
            "\n"
            "static Oid\n"
            "getDatabaseOid(Archive *fout)\n"
            "{\n"
            "\tpg_log_info(\"reading database id\");\n"
            "\n"
            "\tPQExpBuffer dbQry = createPQExpBuffer();\n"
            "\tPGresult   *res = ybQueryDatabaseData(fout, dbQry);\n"
            "\tint\t\t\ti_oid = PQfnumber(res, \"oid\");\n"
            "\tOid\t\t\tdb_oid = atooid(PQgetvalue(res, 0, i_oid));\n"
            "\n"
            "\tPQclear(res);\n"
            "\tdestroyPQExpBuffer(dbQry);\n"
            "\treturn db_oid;\n"
            "}\n"
        )
        # Find the remaining YB functions in theirs (after getDatabaseOid)
        idx = theirs.find("/*\n * Load the YB table properties")
        if idx >= 0:
            remaining_yb = theirs[idx:]
        else:
            remaining_yb = ""
        
        resolution = ours + yb_funcs + remaining_yb
        desc = "read_dump_filters + YB helpers -> keep both, PG19 query in ybQueryDatabaseData"

    else:
        print(f"Conflict at line {start_line}: UNHANDLED - SKIPPING")
        continue

    print(f"  Resolved conflict at line {start_line}: {desc}")
    content = content[:m.start()] + resolution + content[m.end():]

with open(FILEPATH, 'w') as f:
    f.write(content)

remaining = len(re.findall(r'<<<<<<< ours', content))
print(f"\nConflicts remaining: {remaining}")
if remaining > 0:
    for m in re.finditer(r'<<<<<<< ours', content):
        line = content[:m.start()].count('\n') + 1
        print(f"  Unresolved at line {line}")
