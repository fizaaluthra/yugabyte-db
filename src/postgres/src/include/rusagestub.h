/*-------------------------------------------------------------------------
 *
 * rusagestub.h
 *	  Stubs for getrusage(3).
 *
 *
 * Portions Copyright (c) 1996-2022, PostgreSQL Global Development Group
 * Portions Copyright (c) 1994, Regents of the University of California
 *
 * src/include/rusagestub.h
 *
 *-------------------------------------------------------------------------
 */
#ifndef RUSAGESTUB_H
#define RUSAGESTUB_H

#include <sys/time.h>			/* for struct timeval */
#ifndef WIN32
#include <sys/times.h>			/* for struct tms */
#endif
#include <limits.h>				/* for CLK_TCK */

#ifndef RUSAGE_SELF
#define RUSAGE_SELF		0
#endif
#ifndef RUSAGE_CHILDREN
#define RUSAGE_CHILDREN (-1)
#endif

#if !defined(__rusage_defined) && !defined(_STRUCT_RUSAGE) && !defined(__APPLE__)
#define __rusage_defined
struct rusage
{
	struct timeval ru_utime;	/* user time used */
	struct timeval ru_stime;	/* system time used */
};
#endif

extern int	getrusage(int who, struct rusage *rusage);

#endif							/* RUSAGESTUB_H */
