/*-------------------------------------------------------------------------
 *
 * spin.h
 *	   API for spinlocks.
 *
 *
 *	The interface to spinlocks is defined by the typedef "slock_t" and
 *	these macros:
 *
 *	void SpinLockInit(volatile slock_t *lock)
 *		Initialize a spinlock (to the unlocked state).
 *
 *	void SpinLockAcquire(volatile slock_t *lock)
 *		Acquire a spinlock, waiting if necessary.
 *		Time out and abort() if unable to acquire the lock in a
 *		"reasonable" amount of time --- typically ~ 1 minute.
 *		YB note: instead of 1 minute, it's roughly 15 seconds.
 *
 *	void SpinLockRelease(volatile slock_t *lock)
 *		Unlock a previously acquired lock.
 *
 *	bool SpinLockFree(slock_t *lock)
 *		Tests if the lock is free. Returns true if free, false if locked.
 *		This does *not* change the state of the lock.
 *
 *	Callers must beware that the macro argument may be evaluated multiple
 *	times!
 *
 *	Load and store operations in calling code are guaranteed not to be
 *	reordered with respect to these operations, because they include a
 *	compiler barrier.  (Before PostgreSQL 9.5, callers needed to use a
 *	volatile qualifier to access data protected by spinlocks.)
 *
 *	Keep in mind the coding rule that spinlocks must not be held for more
 *	than a few instructions.  In particular, we assume it is not possible
 *	for a CHECK_FOR_INTERRUPTS() to occur while holding a spinlock, and so
 *	it is not necessary to do HOLD/RESUME_INTERRUPTS() in these macros.
 *
 *	These macros are implemented in terms of hardware-dependent macros
 *	supplied by s_lock.h.  There is not currently any extra functionality
 *	added by this header, but there has been in the past and may someday
 *	be again.
 *
 *
 * Portions Copyright (c) 1996-2026, PostgreSQL Global Development Group
 * Portions Copyright (c) 1994, Regents of the University of California
 *
 * src/include/storage/spin.h
 *
 *-------------------------------------------------------------------------
 */
#ifndef SPIN_H
#define SPIN_H

#include "storage/s_lock.h"

/*
 * YB: We track spinlock acquisitions per-process so the postmaster can detect
 * when a child dies while holding a spinlock and force a restart.  We use an
 * external pointer (set in proc.c when MyProc is initialized) instead of
 * referencing MyProc directly, because including proc.h here creates a
 * circular include chain in PG19:  lock.h -> shmem.h -> spin.h -> proc.h ->
 * lock.h.  When the pointer is NULL (postmaster, before InitProcess), the
 * tracking is simply skipped.
 */
extern PGDLLIMPORT int *yb_spin_locks_acquired_ptr;

#define SpinLockInit(lock)	S_INIT_LOCK(lock)

/* YB modified */
#define SpinLockAcquire(lock) \
	do \
	{ \
		if (yb_spin_locks_acquired_ptr) \
			(*yb_spin_locks_acquired_ptr)++; \
		S_LOCK(lock); \
	} while (0)

/* YB modified */
#define SpinLockRelease(lock) \
	do \
	{ \
		S_UNLOCK(lock); \
		if (yb_spin_locks_acquired_ptr && *yb_spin_locks_acquired_ptr >= 1) \
			(*yb_spin_locks_acquired_ptr)--; \
	} while (0)

#define SpinLockFree(lock)	S_LOCK_FREE(lock)

#endif							/* SPIN_H */
