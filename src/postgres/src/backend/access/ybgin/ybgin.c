/*--------------------------------------------------------------------------
 *
 * ybgin.c
 *	  Implementation of Yugabyte Generalized Inverted Index access method.
 *
 * Copyright (c) YugabyteDB, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License.  You may obtain a copy
 * of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
 * License for the specific language governing permissions and limitations
 * under the License.
 *
 * IDENTIFICATION
 *			src/backend/access/ybgin/ybgin.c
 *--------------------------------------------------------------------------
 */

#include "postgres.h"

#include "access/amapi.h"
#include "access/gin.h"
#include "access/ybgin.h"
#include "fmgr.h"
#include "nodes/nodes.h"
#include "postgres_ext.h"

/*
 * PG19 requires aminsert != NULL (Assert in GetIndexAmRoutine). YB indexes use
 * yb_aminsert instead; this stub satisfies the assert and should never run.
 */
static bool
ybgin_aminsert_stub(Relation indexRelation,
					Datum *values,
					bool *isnull,
					ItemPointer heap_tid,
					Relation heapRelation,
					IndexUniqueCheck checkUnique,
					bool indexUnchanged,
					IndexInfo *indexInfo)
{
	elog(ERROR, "aminsert called on YBGIN index; use yb_aminsert path");
	return false;
}

/*
 * YBGIN handler function: return IndexAmRoutine with access method parameters
 * and callbacks.
 */
Datum
ybginhandler(PG_FUNCTION_ARGS)
{
	IndexAmRoutine *amroutine = makeNode(IndexAmRoutine);

	amroutine->amstrategies = 0;
	amroutine->amsupport = GINNProcs;
	amroutine->amcanorder = false;
	amroutine->amcanorderbyop = false;
	amroutine->amcanbackward = false;
	amroutine->amcanunique = false;
	amroutine->amcanmulticol = false;	/* TODO(jason): support multicolumn */
	amroutine->amoptionalkey = true;
	amroutine->amsearcharray = false;
	amroutine->amsearchnulls = false;
	amroutine->amstorage = true;
	amroutine->amclusterable = false;
	amroutine->ampredlocks = true;	/* TODO(jason): check what this is */
	amroutine->amcanparallel = false;
	amroutine->amcaninclude = false;
	amroutine->ybamcanupdatetupleinplace = false;
	amroutine->amkeytype = InvalidOid;

	amroutine->ambuild = ybginbuild;
	amroutine->ambuildempty = ybginbuildempty;
	amroutine->aminsert = ybgin_aminsert_stub;
	amroutine->ambulkdelete = ybginbulkdelete;
	amroutine->amvacuumcleanup = ybginvacuumcleanup;
	amroutine->amcanreturn = NULL;
	amroutine->amcostestimate = ybgincostestimate;
	amroutine->amoptions = ybginoptions;
	amroutine->amproperty = NULL;
	amroutine->amvalidate = ybginvalidate;
	amroutine->ambeginscan = ybginbeginscan;
	amroutine->amrescan = ybginrescan;
	amroutine->amgettuple = ybgingettuple;
	amroutine->amgetbitmap = NULL;	/* TODO(jason): support bitmap scan */
	amroutine->amendscan = ybginendscan;
	amroutine->ammarkpos = NULL;
	amroutine->amrestrpos = NULL;
	amroutine->amestimateparallelscan = NULL;
	amroutine->aminitparallelscan = NULL;
	amroutine->amparallelrescan = NULL;
	amroutine->yb_amisforybrelation = true;
	amroutine->yb_aminsert = ybgininsert;
	amroutine->yb_amdelete = ybgindelete;
	amroutine->yb_amupdate = NULL;
	amroutine->yb_ambackfill = ybginbackfill;
	amroutine->yb_ammightrecheck = ybginmightrecheck;
	amroutine->yb_ambindschema = ybginbindschema;

	PG_RETURN_POINTER(amroutine);
}
