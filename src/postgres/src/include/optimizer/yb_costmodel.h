/*-------------------------------------------------------------------------
 *
 * yb_costmodel.h
 *	  YB-specific cost model enum for GUC options.
 *
 * This header is separate from cost.h so that guc.c can use the enum
 * without pulling in the heavy planner headers (pathnodes.h, plannodes.h).
 *
 *-------------------------------------------------------------------------
 */
#ifndef YB_COSTMODEL_H
#define YB_COSTMODEL_H

#include "c.h"

/* possible values for yb_enable_cbo */
typedef enum
{
	YB_COST_MODEL_LEGACY_IGNORE_STATS_BNL = -5,
	YB_COST_MODEL_LEGACY_BNL = -4,
	YB_COST_MODEL_LEGACY_STATS_BNL = -3,
	YB_COST_MODEL_LEGACY = -2,
	YB_COST_MODEL_LEGACY_STATS = -1,
	YB_COST_MODEL_OFF = 0,
	YB_COST_MODEL_ON,
} YbCostModel;

extern PGDLLIMPORT YbCostModel yb_enable_cbo;

#endif							/* YB_COSTMODEL_H */
