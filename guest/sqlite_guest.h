/* The sqlite guest's primitives, for a guest built on it: the bound names and the statement loop, the transaction and update wrappers, drop and dump. Private to sqlite's link unit. */

#ifndef SQLITE_GUEST_H
#define SQLITE_GUEST_H

#include "sqlite3.h"
#include "amk_guest.h"

#define SQLITE_STATUS_USAGE 2
#define SQLITE_STATUS_RUN 5
#define SQ_MAXARGS 32

typedef int sq_runner (sqlite3 *db, struct amk_sink *out, const char *op, const char *prog);

void sq_puts (struct amk_sink *out, const char *s);
const char *sq_args (const char *op, const char *rest, char **names, char **values, int *json, int *nargs, long *deadline);
double sq_now_ms (void);
int sq_deadline_check (void *at);
int sq_exec (sqlite3 *db, struct amk_sink *out, const char *op, const char *text);
int sq_statements (sqlite3 *db, struct amk_sink *out, const char *op, const char *prog);
int sq_transaction (sqlite3 *db, struct amk_sink *out, const char *op, const char *prog, const char *begin, sq_runner *run);
int sq_update (sqlite3 *db, struct amk_sink *out, const char *prog, sq_runner *run);
int sq_drop_all (sqlite3 *db);
int sq_dump (sqlite3 *db, struct amk_sink *out, int (*own) (const char *));

void *sqlite_create (void);
void *sqlite_open (void *state, const char *path, int shared);
int sqlite_get (void *state, struct amk_sink *out, const char *prog);
int sqlite_update (void *state, struct amk_sink *out, const char *prog);

#endif
