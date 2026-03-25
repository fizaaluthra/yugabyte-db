#!/usr/bin/env python3
"""Apply all YB additions to PG19 guc.c"""
import sys

with open('src/backend/utils/misc/guc.c', 'r') as f:
    c = f.read()

ok_count = 0

def rep(old, new, desc):
    global c, ok_count
    pos = c.find(old)
    if pos < 0:
        print(f"WARN: {desc}")
        return
    c = c[:pos] + new + c[pos+len(old):]
    ok_count += 1
    print(f"OK: {desc}")

def ins_after(marker, text, desc):
    global c, ok_count
    pos = c.find(marker)
    if pos < 0:
        print(f"WARN ins_after: {desc}")
        return
    pos += len(marker)
    c = c[:pos] + text + c[pos:]
    ok_count += 1
    print(f"OK: {desc}")

def ins_before(marker, text, desc):
    global c, ok_count
    pos = c.find(marker)
    if pos < 0:
        print(f"WARN ins_before: {desc}")
        return
    c = c[:pos] + text + c[pos:]
    ok_count += 1
    print(f"OK: {desc}")

# 1. YB includes
ins_after('#include "utils/timestamp.h"\n',
    '\n/* YB includes */\n'
    '#include "access/heaptoast.h"\n#include "access/yb_scan.h"\n'
    '#include "catalog/index.h"\n#include "commands/copy.h"\n'
    '#include "common/pg_yb_param_status_flags.h"\n'
    '#include "executor/ybModifyTable.h"\n#include "optimizer/yb_saop_merge.h"\n'
    '#include "pg_yb_utils.h"\n#include "tcop/pquery.h"\n'
    '#include "utils/syscache.h"\n#include "yb/util/debug/leak_annotations.h"\n'
    '#include "yb_ash.h"\n#include "yb_query_diagnostics.h"\n'
    '#include "yb_tcmalloc_utils.h"\n', "YB includes")

# 2. YB static variables
ins_after('#define GUC_SAFE_SEARCH_PATH "pg_catalog, pg_temp"\n',
    '\nstatic double yb_transaction_priority_lower_bound = 0.0;\n'
    'static double yb_transaction_priority_upper_bound = 1.0;\n'
    'static double yb_transaction_priority = 0.0;\n'
    'static int\tyb_tcmalloc_sample_period = 1024 * 1024;\t/* 1MB */\n', "YB static vars")

# 3. YB function declarations
ins_after('static bool call_enum_check_hook(const struct config_generic *conf, int *newval,\n'
    '\t\t\t\t\t\t\t\t void **extra, GucSource source, int elevel);\n',
    '\n/* YB functions */\n'
    'extern YbcTxnPriorityRequirement YBCGetTransactionPriorityType();\n'
    'extern double YBCGetTransactionPriority();\n'
    'extern void YBCAssignTransactionPriorityLowerBound(double newval, void *extra);\n'
    'extern void YBCAssignTransactionPriorityUpperBound(double newval, void *extra);\n'
    'static bool call_oid_check_hook(struct yb_config_oid *conf, Oid *newval,\n'
    '\t\t\t\t\t\t\t\tvoid **extra, GucSource source, int elevel);\n'
    'static bool check_backoff_multiplier(double *multiplier, void **extra, GucSource source);\n'
    'static bool check_default_replica_identity(char **newval, void **extra,\n'
    '\t\t\t\t\t\t\t\t\t\t   GucSource source);\n'
    'static bool yb_check_neg_catcache_ids(char **newval, void **extra,\n'
    '\t\t\t\t\t\t\t\t\t\t  GucSource source);\n'
    'static void yb_set_neg_catcache_ids(const char *newval, void *extra);\n'
    'static bool check_max_backoff(int *max_backoff_msecs, void **extra, GucSource source);\n'
    'static bool check_min_backoff(int *min_backoff_msecs, void **extra, GucSource source);\n'
    'static bool check_transaction_priority_lower_bound(double *newval, void **extra, GucSource source);\n'
    'static bool check_transaction_priority_upper_bound(double *newval, void **extra, GucSource source);\n'
    'static bool check_yb_explicit_row_locking_batch_size(int *newval, void **extra, GucSource source);\n'
    'static bool yb_check_no_txn(int *newval, void **extra, GucSource source);\n'
    'static bool yb_check_toast_catcache_threshold(int *newval, void **extra, GucSource source);\n'
    'static bool yb_disable_auto_analyze_check_hook(bool *newval, void **extra, GucSource source);\n'
    'static const char *show_tcmalloc_sample_period(void);\n'
    'static const char *yb_show_maxconnections(void);\n'
    'static void assign_tcmalloc_sample_period(int newval, void *extra);\n'
    'static void assign_yb_pg_batch_detection_mechanism(int new_value, void *extra);\n'
    'static void assign_ysql_upgrade_mode(bool newval, void *extra);\n'
    'static void check_reserved_prefixes(const char *varName);\n'
    'static void assign_yb_enable_cbo(int new_value, void *extra);\n'
    'static void assign_yb_enable_optimizer_statistics(bool new_value, void *extra);\n'
    'static void assign_yb_enable_base_scans_cost_model(bool new_value, void *extra);\n\n\n'
    'static bool check_yb_enable_advisory_locks(bool *newval, void **extra, GucSource source);\n\n'
    'static void assign_yb_silence_advisory_locks_not_supported_error(bool newval, void *extra);\n\n'
    'static void assign_yb_enable_pg_stat_statements_rpc_stats(bool newval, void *extra);\n',
    "YB declarations")

# 4. map_old_guc_names
rep('\t"ssl_ecdh_curve", "ssl_groups",\n\tNULL\n};',
    '\t"ssl_ecdh_curve", "ssl_groups",\n\t"yb_enable_parallel_append", "enable_parallel_append",\n\tNULL\n};',
    "map_old_guc_names")

# 5. yb_should_report_guc function
ins_before('/*\n * Reset all options to their saved default values (implements RESET ALL)\n */',
    'static bool\nyb_should_report_guc(struct config_generic *record)\n{\n'
    '\tbool\t\tshouldReportGUC = record->flags & GUC_REPORT;\n\n'
    '\tif (YbIsClientYsqlConnMgr())\n\t{\n'
    '\t\tshouldReportGUC = shouldReportGUC ||\n'
    '\t\t\t(record->status & GUC_VALUE_RESET) ||\n'
    '\t\t\t(record->context >= PGC_SU_BACKEND &&\n'
    '\t\t\t (record->source == PGC_S_CLIENT ||\n'
    '\t\t\t  record->source == PGC_S_SESSION));\n'
    '\t}\n\treturn shouldReportGUC;\n}\n\n\n', "yb_should_report_guc")

# 6. ResetAllOptions YB
rep('\t\tset_guc_source(gconf, gconf->reset_source);\n\t\tgconf->scontext = gconf->reset_scontext;\n\t\tgconf->srole = gconf->reset_srole;\n\n\t\tif ((gconf->flags & GUC_REPORT) && !(gconf->status & GUC_NEEDS_REPORT))',
    '\t\tset_guc_source(gconf, gconf->reset_source);\n\t\tgconf->scontext = gconf->reset_scontext;\n\t\tgconf->srole = gconf->reset_srole;\n\t\t/* YB: Add GUC_VALUE_RESET for relaying back to Connection Manager */\n\t\tif (YbIsClientYsqlConnMgr())\n\t\t\tgconf->status |= GUC_VALUE_RESET;\n\n\t\tif (yb_should_report_guc(gconf) && !(gconf->status & GUC_NEEDS_REPORT))',
    "ResetAllOptions YB")

# 7. yb_needs_report decl
rep('\t\t\tbool\t\trestorePrior = false;\n\t\t\tbool\t\trestoreMasked = false;\n\t\t\tbool\t\tchanged;',
    '\t\t\tbool\t\trestorePrior = false;\n\t\t\tbool\t\trestoreMasked = false;\n\t\t\tbool\t\tchanged;\n\t\t\tbool\t\tyb_needs_report;',
    "yb_needs_report decl")

# 8. yb_needs_report init
rep('\t\t\tchanged = false;\n\n\t\t\tif (restorePrior || restoreMasked)',
    '\t\t\tchanged = false;\n\t\t\tyb_needs_report = false;\n\n\t\t\tif (restorePrior || restoreMasked)',
    "yb_needs_report init")

# 9. GUC_YB_CUSTOM_STICKY in AtEOXact_GUC string case
rep('\t\t\t\t\t\t\t\tset_extra_field(gconf, &gconf->extra,\n\t\t\t\t\t\t\t\t\t\t\t\tnewextra);\n\t\t\t\t\t\t\t\tchanged = true;\n\t\t\t\t\t\t\t}\n\n\t\t\t\t\t\t\t/*\n\t\t\t\t\t\t\t * Release stacked values',
    '\t\t\t\t\t\t\t\tset_extra_field(gconf, &gconf->extra,\n\t\t\t\t\t\t\t\t\t\t\t\tnewextra);\n\t\t\t\t\t\t\t\tchanged = true;\n\t\t\t\t\t\t\t\tif (gconf->flags & GUC_YB_CUSTOM_STICKY)\n\t\t\t\t\t\t\t\t{\n\t\t\t\t\t\t\t\t\telog(LOG, "Making connection sticky for %s",\n\t\t\t\t\t\t\t\t\t\t gconf->name);\n\t\t\t\t\t\t\t\t\tyb_ysql_conn_mgr_sticky_guc = true;\n\t\t\t\t\t\t\t\t}\n\t\t\t\t\t\t\t}\n\n\t\t\t\t\t\t\t/*\n\t\t\t\t\t\t\t * Release stacked values',
    "GUC_YB_CUSTOM_STICKY AtEOXact")

# 10. YB conn mgr rollback
rep('\t\t\t\tset_extra_field(gconf, &(stack->prior.extra), NULL);\n\t\t\t\tset_extra_field(gconf, &(stack->masked.extra), NULL);\n\n\t\t\t\t/* And restore source information */',
    '\t\t\t\tset_extra_field(gconf, &(stack->prior.extra), NULL);\n\t\t\t\tset_extra_field(gconf, &(stack->masked.extra), NULL);\n\n\t\t\t\t/*\n\t\t\t\t * YB: Connection manager needs to be informed if any variable\n\t\t\t\t * set by the user is rolled back\n\t\t\t\t */\n\t\t\t\tif (YbIsClientYsqlConnMgr() && changed &&\n\t\t\t\t\t(gconf->context == PGC_SUSET ||\n\t\t\t\t\t gconf->context == PGC_USERSET) &&\n\t\t\t\t\tgconf->source == PGC_S_SESSION)\n\t\t\t\t{\n\t\t\t\t\tyb_needs_report = true;\n\t\t\t\t}\n\n\t\t\t\t/* And restore source information */',
    "YB conn mgr rollback")

# 11. AtEOXact_GUC report condition
rep('\t\t\t/* Report new value if we changed it */\n\t\t\tif (changed && (gconf->flags & GUC_REPORT) &&\n\t\t\t\t!(gconf->status & GUC_NEEDS_REPORT))',
    '\t\t\t/* Report new value if we changed it */\n\t\t\tif (changed && (yb_needs_report || yb_should_report_guc(gconf)) &&\n\t\t\t\t!(gconf->status & GUC_NEEDS_REPORT))',
    "AtEOXact_GUC report")

# 12. BeginReportingGUCOptions
rep('\t\tif (conf->flags & GUC_REPORT)\n\t\t\tReportGUCOption(conf);',
    '\t\tif (yb_should_report_guc(conf))\n\t\t\tReportGUCOption(conf);',
    "BeginReportingGUCOptions")

# 13. ReportChangedGUCOptions Assert
rep('\t\tAssert((conf->flags & GUC_REPORT) && (conf->status & GUC_NEEDS_REPORT));',
    '\t\tAssert(((conf->flags & GUC_REPORT) || YbIsClientYsqlConnMgr()) &&\n\t\t\t   (conf->status & GUC_NEEDS_REPORT));',
    "ReportChangedGUCOptions Assert")

# 14. ReportGUCOption rewrite
old_rgo = ('/*\n * ReportGUCOption: if appropriate, transmit option value to frontend\n *\n * We need not transmit the value if it\'s the same as what we last\n * transmitted.\n */\nstatic void\nReportGUCOption(struct config_generic *record)\n{\n\tchar\t   *val = ShowGUCOption(record, false);\n\n\tif (record->last_reported == NULL ||\n\t\tstrcmp(val, record->last_reported) != 0)\n\t{\n\t\tStringInfoData msgbuf;\n\n\t\tpq_beginmessage(&msgbuf, PqMsg_ParameterStatus);\n\t\tpq_sendstring(&msgbuf, record->name);\n\t\tpq_sendstring(&msgbuf, val);\n\t\tpq_endmessage(&msgbuf);\n\n\t\t/*\n\t\t * We need a long-lifespan copy.  If guc_strdup() fails due to OOM,\n\t\t * we\'ll set last_reported to NULL and thereby possibly make a\n\t\t * duplicate report later.\n\t\t */\n\t\tguc_free(record->last_reported);\n\t\trecord->last_reported = guc_strdup(LOG, val);\n\t}\n\n\tpfree(val);\n}')

new_rgo = ('/*\n * ReportGUCOption: if appropriate, transmit option value to frontend\n *\n * We need not transmit the value if it\'s the same as what we last\n * transmitted.\n *\n * YB: Always send back a ParameterStatus packet back, atleast to\n * Connection Manager for full correctness. If the value is the same\n * as what was previously transmitted, do not send the packet to the\n * client from Connection Manager.\n */\nstatic void\nReportGUCOption(struct config_generic *record)\n{\n\tchar\t   *val = ShowGUCOption(record, false);\n\n\t/*\n\t * YB: record->last_reported doesn\'t make sense for connection manager\n\t * since the backend can be attached to another client which would need\n\t * ParameterStatus of a variable it sets\n\t */\n\tif (YbIsClientYsqlConnMgr() ||\n\t\trecord->last_reported == NULL ||\n\t\tstrcmp(val, record->last_reported) != 0)\n\t{\n\t\tStringInfoData msgbuf;\n\n\t\tif (YbIsClientYsqlConnMgr())\n\t\t{\n\t\t\tuint8\t\tflags = 0;\n\n\t\t\tif (record->flags & GUC_REPORT)\n\t\t\t\tflags |= YB_PARAM_STATUS_REPORT_ENABLED;\n\n\t\t\tswitch (record->context)\n\t\t\t{\n\t\t\t\tcase PGC_INTERNAL:\n\t\t\t\tcase PGC_POSTMASTER:\n\t\t\t\tcase PGC_SIGHUP:\n\t\t\t\t\tbreak;\n\t\t\t\tcase PGC_SU_BACKEND:\n\t\t\t\tcase PGC_BACKEND:\n\t\t\t\t\tif (record->source == PGC_S_CLIENT)\n\t\t\t\t\t\tflags |= YB_PARAM_STATUS_CONTEXT_BACKEND;\n\t\t\t\t\tbreak;\n\t\t\t\tcase PGC_SUSET:\n\t\t\t\tcase PGC_USERSET:\n\t\t\t\t\tif (record->source == PGC_S_CLIENT)\n\t\t\t\t\t\tflags |=\n\t\t\t\t\t\t\tYB_PARAM_STATUS_USERSET_OR_SUSET_SOURCE_STARTUP;\n\t\t\t\t\telse if (record->source == PGC_S_SESSION)\n\t\t\t\t\t\tflags |=\n\t\t\t\t\t\t\tYB_PARAM_STATUS_USERSET_OR_SUSET_SOURCE_SESSION;\n\t\t\t\t\tbreak;\n\t\t\t}\n\n\t\t\tpq_beginmessage(&msgbuf, \'r\');\n\t\t\tpq_sendstring(&msgbuf, record->name);\n\t\t\tpq_sendstring(&msgbuf, val);\n\t\t\tpq_sendbyte(&msgbuf, flags);\n\t\t\tpq_endmessage(&msgbuf);\n\t\t}\n\t\telse\n\t\t{\n\t\t\tpq_beginmessage(&msgbuf, PqMsg_ParameterStatus);\n\t\t\tpq_sendstring(&msgbuf, record->name);\n\t\t\tpq_sendstring(&msgbuf, val);\n\t\t\tpq_endmessage(&msgbuf);\n\t\t}\n\n\t\t/*\n\t\t * We need a long-lifespan copy.  If guc_strdup() fails due to OOM,\n\t\t * we\'ll set last_reported to NULL and thereby possibly make a\n\t\t * duplicate report later.\n\t\t */\n\t\tguc_free(record->last_reported);\n\t\trecord->last_reported = guc_strdup(LOG, val);\n\t}\n\n\tpfree(val);\n\t/* YB: Reset flag that was set for Connection Manager */\n\tif (YbIsClientYsqlConnMgr())\n\t\trecord->status &= ~GUC_VALUE_RESET;\n}')
rep(old_rgo, new_rgo, "ReportGUCOption rewrite")

# 15. gucReset in set_config_with_handle
rep('\tvoid\t   *newextra = NULL;\n\tbool\t\tprohibitValueChange = false;\n\tbool\t\tmakeDefault;',
    '\tvoid\t   *newextra = NULL;\n\tbool\t\tprohibitValueChange = false;\n\tbool\t\tmakeDefault;\n\tbool\t\tgucReset = value == NULL && source == PGC_S_SESSION;',
    "gucReset variable")

# 16. GUC_VALUE_RESET marks (replace ALL occurrences)
old_m = '\t\t\t\t\tset_guc_source(record, source);\n\t\t\t\t\trecord->scontext = context;\n\t\t\t\t\trecord->srole = srole;\n\t\t\t\t}\n\t\t\t\tif (makeDefault)'
new_m = '\t\t\t\t\tset_guc_source(record, source);\n\t\t\t\t\trecord->scontext = context;\n\t\t\t\t\trecord->srole = srole;\n\t\t\t\t\t/* YB: Mark value as been reset for connection manager */\n\t\t\t\t\tif (gucReset)\n\t\t\t\t\t\trecord->status |= GUC_VALUE_RESET;\n\t\t\t\t}\n\t\t\t\tif (makeDefault)'
cnt = c.count(old_m)
if cnt > 0:
    c = c.replace(old_m, new_m)
    ok_count += 1
    print(f"OK: GUC_VALUE_RESET ({cnt}x)")

# 17. GUC_YB_CUSTOM_STICKY in set_config_with_handle (after session_authorization hack)
rep('\t\t\t\t\t\t\t\t\t\t\t\t\t  true,\n\t\t\t\t\t\t\t\t\t\t\t\t\t  elevel,\n\t\t\t\t\t\t\t\t\t\t\t\t\t  false);\n\t\t\t\t}\n\n\t\t\t\tif (makeDefault)',
    '\t\t\t\t\t\t\t\t\t\t\t\t\t  true,\n\t\t\t\t\t\t\t\t\t\t\t\t\t  elevel,\n\t\t\t\t\t\t\t\t\t\t\t\t\t  false);\n\n\t\t\t\t\tif (record->flags & GUC_YB_CUSTOM_STICKY)\n\t\t\t\t\t{\n\t\t\t\t\t\telog(LOG, "Making connection sticky for setting %s", name);\n\t\t\t\t\t\tyb_ysql_conn_mgr_sticky_guc = true;\n\t\t\t\t\t}\n\t\t\t\t}\n\n\t\t\t\tif (makeDefault)',
    "GUC_YB_CUSTOM_STICKY set_config_with_handle")

# 18. set_config_with_handle report condition
rep('\tif (changeVal && (record->flags & GUC_REPORT) &&\n\t\t!(record->status & GUC_NEEDS_REPORT))',
    '\tif (changeVal && yb_should_report_guc(record) &&\n\t\t!(record->status & GUC_NEEDS_REPORT) &&\n\t\t!(YbIsClientYsqlConnMgr() && (action & GUC_ACTION_LOCAL)))',
    "set_config_with_handle report")

# 19. DefineCustomStringVariable sticky
rep('\tvar->_string.assign_hook = assign_hook;\n\tvar->_string.show_hook = show_hook;\n\tdefine_custom_variable(var);',
    '\tvar->_string.assign_hook = assign_hook;\n\tvar->_string.show_hook = show_hook;\n\tdefine_custom_variable(var);\n\n\t/* YB: make custom string variables sticky for connection manager */\n\tvar->flags |= GUC_YB_CUSTOM_STICKY;',
    "DefineCustomStringVariable sticky")

# 20. ShowGUCOption PGC_OID
rep('\t\tcase PGC_INT:\n\t\t\t{\n\t\t\t\tconst struct config_int *conf = &record->_int;\n\n\t\t\t\tif (conf->show_hook)\n\t\t\t\t\tval = conf->show_hook();\n\t\t\t\telse\n\t\t\t\t{\n\t\t\t\t\t/*\n\t\t\t\t\t * Use int64 arithmetic to avoid overflows in units\n\t\t\t\t\t * conversion.\n\t\t\t\t\t */\n\t\t\t\t\tint64\t\tresult = *conf->variable;',
    '\t\tcase PGC_OID:\n\t\t\t{\n\t\t\t\tstruct yb_config_oid *conf = (struct yb_config_oid *) record;\n\n\t\t\t\tif (conf->show_hook)\n\t\t\t\t\tval = conf->show_hook();\n\t\t\t\telse\n\t\t\t\t{\n\t\t\t\t\tsnprintf(buffer, sizeof(buffer), "%u", *conf->variable);\n\t\t\t\t\tval = buffer;\n\t\t\t\t}\n\t\t\t}\n\t\t\tbreak;\n\n\t\tcase PGC_INT:\n\t\t\t{\n\t\t\t\tconst struct config_int *conf = &record->_int;\n\n\t\t\t\tif (conf->show_hook)\n\t\t\t\t\tval = conf->show_hook();\n\t\t\t\telse\n\t\t\t\t{\n\t\t\t\t\t/*\n\t\t\t\t\t * Use int64 arithmetic to avoid overflows in units\n\t\t\t\t\t * conversion.\n\t\t\t\t\t */\n\t\t\t\t\tint64\t\tresult = *conf->variable;',
    "ShowGUCOption PGC_OID")

# 21. GetConfigOptionResetString PGC_OID
rep('\t\tcase PGC_INT:\n\t\t\tsnprintf(buffer, sizeof(buffer), "%d",\n\t\t\t\t\t record->_int.reset_val);\n\t\t\treturn buffer;',
    '\t\tcase PGC_OID:\n\t\t\tsnprintf(buffer, sizeof(buffer), "%u",\n\t\t\t\t\t ((struct yb_config_oid *) record)->reset_val);\n\t\t\treturn buffer;\n\n\t\tcase PGC_INT:\n\t\t\tsnprintf(buffer, sizeof(buffer), "%d",\n\t\t\t\t\t record->_int.reset_val);\n\t\t\treturn buffer;',
    "GetConfigOptionResetString PGC_OID")

# 22. call_oid_check_hook function
ins_before('static bool\ncall_real_check_hook(const struct config_generic *conf, double *newval, void **extra,\n',
    'static bool\ncall_oid_check_hook(struct yb_config_oid *conf, Oid *newval, void **extra,\n\t\t\t\t\tGucSource source, int elevel)\n{\n\tif (!conf->check_hook)\n\t\treturn true;\n\n\tGUC_check_errcode_value = ERRCODE_INVALID_PARAMETER_VALUE;\n\tGUC_check_errmsg_string = NULL;\n\tGUC_check_errdetail_string = NULL;\n\tGUC_check_errhint_string = NULL;\n\n\tif (!conf->check_hook(newval, extra, source))\n\t{\n\t\tereport(elevel,\n\t\t\t\t(errcode(GUC_check_errcode_value),\n\t\t\t\t GUC_check_errmsg_string ?\n\t\t\t\t errmsg_internal("%s", GUC_check_errmsg_string) :\n\t\t\t\t errmsg("invalid value for parameter \\"%s\\": %u",\n\t\t\t\t\t\tconf->gen.name, *newval),\n\t\t\t\t GUC_check_errdetail_string ?\n\t\t\t\t errdetail_internal("%s", GUC_check_errdetail_string) : 0,\n\t\t\t\t GUC_check_errhint_string ?\n\t\t\t\t errhint("%s", GUC_check_errhint_string) : 0));\n\t\tFlushErrorState();\n\t\treturn false;\n\t}\n\n\treturn true;\n}\n\n',
    "call_oid_check_hook")

# 23. YB functions at end of file - extract from theirs lines 16207 onwards
with open('/tmp/yb_theirs_guc.c', 'r') as f:
    theirs_lines = f.readlines()
yb_funcs = ''.join(theirs_lines[16206:])  # 0-indexed, line 16207 = index 16206
c = c.rstrip('\n') + '\n\n' + yb_funcs
ok_count += 1
print(f"OK: YB end-of-file functions ({len(theirs_lines) - 16206} lines)")

with open('src/backend/utils/misc/guc.c', 'w') as f:
    f.write(c)

print(f"\nTotal changes: {ok_count}")
print(f"File: {len(c.splitlines())} lines")
