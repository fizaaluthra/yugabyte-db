DIRS = \
	documentdb \
	# YB_TODO_PG19_MERGE: hypopg needs PG19 API updates
	# hypopg \
	# YB_TODO_PG19_MERGE: orafce needs PG19 API updates
	# orafce \
	# YB_TODO_PG19_MERGE: pg_cron needs PG19 API updates
	# pg_cron \
	# YB_TODO_PG19_MERGE: pg_hint_plan needs PG19 API updates
	# pg_hint_plan \
	$(if $(filter 1,$(YB_SKIP_PG_PARQUET_BUILD)),,pg_parquet) \
	pg_partman \
	# YB_TODO_PG19_MERGE: pg_stat_monitor needs PG19 API updates
	# pg_stat_monitor \
	pgaudit \
	pgtap \
	pgvector \
	postgresql-hll \
	postgresql_anonymizer \
	wal2json \

BUILDDIRS = $(DIRS:%=build-%)
INSTALLDIRS = $(DIRS:%=install-%)
CLEANDIRS = $(DIRS:%=clean-%)

all: $(BUILDDIRS)
$(DIRS): $(BUILDDIRS)
$(BUILDDIRS):
	$(MAKE) -C $(@:build-%=%)

clean: $(CLEANDIRS)
$(CLEANDIRS):
	$(MAKE) -C $(@:clean-%=%) clean

install: $(INSTALLDIRS)
$(INSTALLDIRS):
	$(MAKE) -C $(@:install-%=%) install

.PHONY: subdirs $(DIRS)
.PHONY: subdirs $(BUILDDIRS)
.PHONY: subdirs $(INSTALLDIRS)
.PHONY: subdirs $(CLEANDIRS)
.PHONY: all install clean
