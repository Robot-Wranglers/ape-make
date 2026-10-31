/* The sqlite guest's kept-state primitives: a state is one in-memory database make holds, a request is one statement whose rows come back as JSON objects, one per line, and the whole value is a dump of schema and rows that load replays. The command line is sqlite's own shell. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "sqlite3.h"
#include "amk_guest.h"

#define SQLITE_STATUS_USAGE 2
#define SQLITE_STATUS_RUN 5

/* Raised by amk_sqlite_park inside a statement, read after the statement ends. */
static int sq_parked;

/* The calls amk_route queued, each a handler's name, the routed tuple as JSON, and how many routes led to it; an update runs them once it commits. */
#define SQ_ROUTE_DEPTH 100
static struct sq_route { char *name; char *tuple; int depth; } *sq_routes;
static int sq_nroutes, sq_route_depth, sq_draining;

static void
sq_emit (struct amk_sink *out, const char *s, size_t n)
{
  out->write (out, s, n);
}

static void
sq_puts (struct amk_sink *out, const char *s)
{
  sq_emit (out, s, strlen (s));
}

/* A text as a JSON string literal, escaped as JSON requires. */
static void
sq_emit_string (struct amk_sink *out, const unsigned char *s)
{
  char buf[8];
  sq_emit (out, "\"", 1);
  for (; *s; ++s)
    {
      switch (*s)
        {
        case '"': sq_puts (out, "\\\""); break;
        case '\\': sq_puts (out, "\\\\"); break;
        case '\n': sq_puts (out, "\\n"); break;
        case '\r': sq_puts (out, "\\r"); break;
        case '\t': sq_puts (out, "\\t"); break;
        default:
          if (*s < 0x20)
            {
              snprintf (buf, sizeof buf, "\\u%04x", *s);
              sq_puts (out, buf);
            }
          else
            sq_emit (out, (const char *) s, 1);
        }
    }
  sq_emit (out, "\"", 1);
}

/* One row as a JSON object keyed by column name; a blob is its hex text. */
static void
sq_emit_row (struct amk_sink *out, sqlite3_stmt *st)
{
  int i, n = sqlite3_column_count (st);
  char num[64];
  sq_emit (out, "{", 1);
  for (i = 0; i < n; ++i)
    {
      if (i > 0)
        sq_emit (out, ",", 1);
      sq_emit_string (out, (const unsigned char *) sqlite3_column_name (st, i));
      sq_emit (out, ":", 1);
      switch (sqlite3_column_type (st, i))
        {
        case SQLITE_NULL:
          sq_puts (out, "null");
          break;
        case SQLITE_INTEGER:
          snprintf (num, sizeof num, "%lld", (long long) sqlite3_column_int64 (st, i));
          sq_puts (out, num);
          break;
        case SQLITE_FLOAT:
          snprintf (num, sizeof num, "%.17g", sqlite3_column_double (st, i));
          sq_puts (out, num);
          break;
        case SQLITE_BLOB:
          {
            const unsigned char *b = sqlite3_column_blob (st, i);
            int j, len = sqlite3_column_bytes (st, i);
            sq_emit (out, "\"", 1);
            for (j = 0; j < len; ++j)
              {
                snprintf (num, sizeof num, "%02x", b[j]);
                sq_emit (out, num, 2);
              }
            sq_emit (out, "\"", 1);
          }
          break;
        default:
          if (sqlite3_value_subtype (sqlite3_column_value (st, i)) == 'J')
            sq_puts (out, (const char *) sqlite3_column_text (st, i));
          else
            sq_emit_string (out, sqlite3_column_text (st, i));
        }
    }
  sq_emit (out, "}\n", 2);
}

#define SQ_MAXARGS 32

/* The leading options: each --arg binds a name to a text and each --argjson to the value its JSON names, for the statements after them, and --deadline bounds the call in milliseconds; the rest of the line is the statements. */
static const char *
sq_args (const char *op, const char *rest, char **names, char **values, int *json, int *nargs, long *deadline)
{
  char word[4096], key[256];
  const char *p = rest, *prog = rest;
  *nargs = 0;
  *deadline = -1;
  for (;;)
    {
      prog = p;
      if (!amk_word (&p, word, sizeof word))
        break;
      if (strcmp (word, "--deadline") == 0)
        {
          char *end;
          if (!amk_word (&p, word, sizeof word) || (*deadline = strtol (word, &end, 10)) < 0 || *end != '\0')
            {
              fprintf (stderr, "sqlite.%s: --deadline takes milliseconds\n", op);
              return NULL;
            }
          continue;
        }
      if (strcmp (word, "--arg") != 0 && strcmp (word, "--argjson") != 0)
        break;
      json[*nargs] = strcmp (word, "--argjson") == 0;
      if (*nargs == SQ_MAXARGS || !amk_word (&p, key, sizeof key) || !amk_word (&p, word, sizeof word))
        {
          fprintf (stderr, "sqlite.%s: %s takes a name and a value\n", op, word);
          return NULL;
        }
      names[*nargs] = strdup (key);
      values[*nargs] = strdup (word);
      ++*nargs;
    }
  while (*prog == ' ' || *prog == '\t')
    ++prog;
  return prog;
}

/* A JSON text bound as the value it names: a number as a number, a string as its text, null as null, true and false as 1 and 0, an array or object as its JSON text. */
static int
sq_bind_json (sqlite3 *db, sqlite3_stmt *st, int idx, const char *text)
{
  sqlite3_stmt *conv = NULL;
  int rc = sqlite3_prepare_v2 (db, "SELECT json_extract(?1, '$')", -1, &conv, NULL);
  if (rc == SQLITE_OK)
    {
      sqlite3_bind_text (conv, 1, text, -1, SQLITE_STATIC);
      rc = sqlite3_step (conv) == SQLITE_ROW ? sqlite3_bind_value (st, idx, sqlite3_column_value (conv, 0)) : SQLITE_ERROR;
    }
  sqlite3_finalize (conv);
  return rc;
}

static double
sq_now_ms (void)
{
  struct timespec t;
  clock_gettime (CLOCK_MONOTONIC, &t);
  return (double) t.tv_sec * 1e3 + (double) t.tv_nsec / 1e6;
}

/* Every thousand virtual machine steps, a nonzero answer once the deadline has passed, which ends the statement as interrupted. */
static int
sq_deadline_check (void *at)
{
  return sq_now_ms () >= *(double *) at;
}

/* Every statement in the text in order, each one's rows to the sink, the bound names filled where a statement names them; the first error ends the run with its message on stderr. */
static int
sq_exec (sqlite3 *db, struct amk_sink *out, const char *op, const char *text)
{
  char *names[SQ_MAXARGS], *values[SQ_MAXARGS];
  int json[SQ_MAXARGS];
  int nargs, i, rc = 0;
  long deadline;
  double at;
  const char *tail = sq_args (op, text, names, values, json, &nargs, &deadline);
  if (tail == NULL)
    rc = SQLITE_STATUS_USAGE;
  else if (deadline >= 0)
    {
      at = sq_now_ms () + (double) deadline;
      sqlite3_progress_handler (db, 1000, sq_deadline_check, &at);
    }
  while (rc == 0 && tail != NULL && *tail != '\0')
    {
      sqlite3_stmt *st = NULL;
      rc = sqlite3_prepare_v2 (db, tail, -1, &st, &tail);
      if (rc != SQLITE_OK)
        {
          fprintf (stderr, "sqlite.%s: %s\n", op, sqlite3_errmsg (db));
          rc = SQLITE_STATUS_RUN;
          break;
        }
      if (st == NULL)
        continue;
      if (strcmp (op, "get") == 0 && !sqlite3_stmt_readonly (st))
        {
          fprintf (stderr, "sqlite.get: a statement that writes belongs in update: %s\n", sqlite3_sql (st));
          sqlite3_finalize (st);
          rc = SQLITE_STATUS_USAGE;
          break;
        }
      for (i = 0; i < nargs; ++i)
        {
          char param[260];
          int idx;
          snprintf (param, sizeof param, ":%s", names[i]);
          idx = sqlite3_bind_parameter_index (st, param);
          if (idx > 0 && json[i])
            rc = sq_bind_json (db, st, idx, values[i]);
          else if (idx > 0)
            sqlite3_bind_text (st, idx, values[i], -1, SQLITE_STATIC);
          if (rc != SQLITE_OK)
            break;
        }
      if (rc != SQLITE_OK)
        {
          fprintf (stderr, "sqlite.%s: --argjson %s: %s\n", op, names[i], sqlite3_errmsg (db));
          sqlite3_finalize (st);
          rc = SQLITE_STATUS_RUN;
          break;
        }
      sq_parked = 0;
      while ((rc = sqlite3_step (st)) == SQLITE_ROW)
        if (out != NULL)
          sq_emit_row (out, st);
      sqlite3_finalize (st);
      if (sq_parked)
        {
          rc = AMK_PARK;
          break;
        }
      if (rc == SQLITE_INTERRUPT && deadline >= 0)
        {
          fprintf (stderr, "sqlite.%s: deadline: %ld ms\n", op, deadline);
          rc = SQLITE_STATUS_RUN;
          amk_ns_answered ();
          break;
        }
      if (rc != SQLITE_DONE)
        {
          fprintf (stderr, "sqlite.%s: %s\n", op, sqlite3_errmsg (db));
          rc = SQLITE_STATUS_RUN;
          break;
        }
      rc = 0;
    }
  if (tail != NULL && deadline >= 0)
    sqlite3_progress_handler (db, 0, NULL, NULL);
  for (i = 0; i < nargs; ++i)
    {
      free (names[i]);
      free (values[i]);
    }
  return rc;
}

/* The dump: every schema statement from sqlite_master, then one insert per row of every table with the values quoted by sqlite itself, each statement on a line of its own. */
static int
sq_dump (sqlite3 *db, struct amk_sink *out)
{
  sqlite3_stmt *tables = NULL, *rows = NULL;
  int rc;
  rc = sqlite3_prepare_v2 (db, "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid", -1, &tables, NULL);
  if (rc != SQLITE_OK)
    return SQLITE_STATUS_RUN;
  while (sqlite3_step (tables) == SQLITE_ROW)
    {
      sq_puts (out, (const char *) sqlite3_column_text (tables, 1));
      sq_puts (out, ";\n");
    }
  sqlite3_finalize (tables);
  rc = sqlite3_prepare_v2 (db, "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY rowid", -1, &tables, NULL);
  if (rc != SQLITE_OK)
    return SQLITE_STATUS_RUN;
  while (sqlite3_step (tables) == SQLITE_ROW)
    {
      const char *name = (const char *) sqlite3_column_text (tables, 0);
      char *cols = NULL, *q;
      sqlite3_stmt *st = NULL;
      q = sqlite3_mprintf ("PRAGMA table_info(%Q)", name);
      if (q == NULL || sqlite3_prepare_v2 (db, q, -1, &st, NULL) != SQLITE_OK)
        {
          sqlite3_free (q);
          continue;
        }
      sqlite3_free (q);
      while (sqlite3_step (st) == SQLITE_ROW)
        {
          char *next = sqlite3_mprintf ("%s%squote(\"%w\")", cols != NULL ? cols : "", cols != NULL ? " || ',' || " : "", sqlite3_column_text (st, 1));
          sqlite3_free (cols);
          cols = next;
        }
      sqlite3_finalize (st);
      if (cols == NULL)
        continue;
      q = sqlite3_mprintf ("SELECT 'INSERT INTO \"%w\" VALUES(' || %s || ');' FROM \"%w\"", name, cols, name);
      sqlite3_free (cols);
      if (q == NULL || sqlite3_prepare_v2 (db, q, -1, &rows, NULL) != SQLITE_OK)
        {
          sqlite3_free (q);
          continue;
        }
      sqlite3_free (q);
      while (sqlite3_step (rows) == SQLITE_ROW)
        {
          sq_puts (out, (const char *) sqlite3_column_text (rows, 0));
          sq_puts (out, "\n");
        }
      sqlite3_finalize (rows);
    }
  sqlite3_finalize (tables);
  return 0;
}

/* amk_sqlite_error(message): the statement fails with that message, as a trigger's raise would, so any program can refuse from a plain statement. */
static void
sq_error (sqlite3_context *ctx, int argc, sqlite3_value **argv)
{
  const unsigned char *msg = argc > 0 ? sqlite3_value_text (argv[0]) : NULL;
  sqlite3_result_error (ctx, msg != NULL ? (const char *) msg : "amk_sqlite_error", -1);
}

/* amk_sqlite_park(): the statement fails and the whole operation answers the park status, so the owner holds the request and runs it again after the next change to the namespace. */
static void
sq_park (sqlite3_context *ctx, int argc, sqlite3_value **argv)
{
  (void) argc;
  (void) argv;
  sq_parked = 1;
  sqlite3_result_error (ctx, "amk_sqlite_park", -1);
}

/* amk_route(name, tuple): the call to the make function name with the tuple's fields, queued for after the update commits; nothing runs here. */
static void
sq_route (sqlite3_context *ctx, int argc, sqlite3_value **argv)
{
  const unsigned char *name = sqlite3_value_text (argv[0]), *tuple = sqlite3_value_text (argv[1]);
  struct sq_route *grown;
  (void) argc;
  if (name == NULL || tuple == NULL)
    {
      sqlite3_result_error (ctx, "amk_route takes a name and a tuple", -1);
      return;
    }
  grown = realloc (sq_routes, (size_t) (sq_nroutes + 1) * sizeof *sq_routes);
  if (grown == NULL)
    {
      sqlite3_result_error_nomem (ctx);
      return;
    }
  sq_routes = grown;
  sq_routes[sq_nroutes].name = strdup ((const char *) name);
  sq_routes[sq_nroutes].tuple = strdup ((const char *) tuple);
  sq_routes[sq_nroutes].depth = sq_route_depth + 1;
  ++sq_nroutes;
  sqlite3_result_null (ctx);
}

/* The queue cut back to its first keep calls, as a failed update leaves it. */
static void
sq_routes_drop (int keep)
{
  while (sq_nroutes > keep)
    {
      --sq_nroutes;
      free (sq_routes[sq_nroutes].name);
      free (sq_routes[sq_nroutes].tuple);
    }
}

/* One queued call: the tuple's fields as text, a nested value as its JSON, then the make function; its answer is dropped and its error reported. */
static void
sq_route_call (sqlite3 *db, struct sq_route *r)
{
  sqlite3_stmt *st = NULL;
  const char **args = NULL;
  const char *err = NULL;
  unsigned int n = 0, i;
  char *s;
  if (sqlite3_prepare_v2 (db, "SELECT value FROM json_each(?1) ORDER BY key", -1, &st, NULL) == SQLITE_OK)
    {
      sqlite3_bind_text (st, 1, r->tuple, -1, SQLITE_STATIC);
      while (sqlite3_step (st) == SQLITE_ROW)
        {
          const unsigned char *v = sqlite3_column_text (st, 0);
          args = realloc (args, (n + 1) * sizeof *args);
          args[n++] = strdup (v != NULL ? (const char *) v : "");
        }
    }
  sqlite3_finalize (st);
  s = amk_call (r->name, n, args, &err);
  if (s == NULL)
    fprintf (stderr, "sqlite: handler %s: %s\n", r->name, err != NULL ? err : "failed");
  free (s);
  for (i = 0; i < n; ++i)
    free ((char *) args[i]);
  free (args);
}

/* The queue run in order once its update commits; a call that routes again queues behind it, up to SQ_ROUTE_DEPTH routes deep. */
static int
sq_routes_drain (sqlite3 *db)
{
  int i, rc = 0;
  sq_draining = 1;
  for (i = 0; i < sq_nroutes; ++i)
    {
      if (sq_routes[i].depth > SQ_ROUTE_DEPTH)
        {
          fprintf (stderr, "sqlite.update: handler %s: routed more than %d deep\n", sq_routes[i].name, SQ_ROUTE_DEPTH);
          rc = SQLITE_STATUS_RUN;
          break;
        }
      sq_route_depth = sq_routes[i].depth;
      sq_route_call (db, &sq_routes[i]);
    }
  sq_routes_drop (0);
  sq_route_depth = 0;
  sq_draining = 0;
  return rc;
}

/* The functions amk adds to every connection, under the engine's name. */
static int
sq_functions (sqlite3 *db)
{
  int rc = sqlite3_create_function (db, "amk_sqlite_error", 1, SQLITE_UTF8, NULL, sq_error, NULL, NULL);
  if (rc == SQLITE_OK)
    rc = sqlite3_create_function (db, "amk_sqlite_park", 0, SQLITE_UTF8, NULL, sq_park, NULL, NULL);
  if (rc == SQLITE_OK)
    rc = sqlite3_create_function (db, "amk_route", 2, SQLITE_UTF8, NULL, sq_route, NULL, NULL);
  return rc;
}

/* The create member: a fresh in-memory database. */
__attribute__ ((visibility ("default"))) void *
sqlite_create (void)
{
  sqlite3 *db = NULL;
  if (sqlite3_open (":memory:", &db) != SQLITE_OK || sq_functions (db) != SQLITE_OK)
    {
      sqlite3_close (db);
      return NULL;
    }
  return db;
}

/* The open member: the database file at path as the store, waiting on another owner's lock; owned holds the file alone, shared lets owners on one host take turns through the write-ahead log. */
__attribute__ ((visibility ("default"))) void *
sqlite_open (void *state, const char *path, int shared)
{
  sqlite3 *db = NULL;
  if (sqlite3_open_v2 (path, &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE, NULL) != SQLITE_OK
      || sq_functions (db) != SQLITE_OK
      || sqlite3_busy_timeout (db, 10000) != SQLITE_OK
      || sqlite3_exec (db, shared ? "PRAGMA journal_mode=WAL" : "PRAGMA locking_mode=EXCLUSIVE", NULL, NULL, NULL) != SQLITE_OK)
    {
      fprintf (stderr, "sqlite: %s: %s\n", path, db != NULL ? sqlite3_errmsg (db) : "cannot open");
      sqlite3_close (db);
      return NULL;
    }
  sqlite3_close (state);
  return db;
}

static int sq_statements (sqlite3 *db, struct amk_sink *out, const char *op, const char *prog);

/* The statements in one transaction when the store is a file, so another owner never sees half a program; begin names the lock, and an in-memory store or an open transaction runs them as they are. */
static int
sq_transaction (sqlite3 *db, struct amk_sink *out, const char *op, const char *prog, const char *begin)
{
  const char *file = sqlite3_db_filename (db, "main");
  int rc;
  if (file == NULL || *file == '\0' || !sqlite3_get_autocommit (db))
    return sq_statements (db, out, op, prog);
  if (sqlite3_exec (db, begin, NULL, NULL, NULL) != SQLITE_OK)
    {
      fprintf (stderr, "sqlite.%s: %s\n", op, sqlite3_errmsg (db));
      return SQLITE_STATUS_RUN;
    }
  rc = sq_statements (db, out, op, prog);
  sqlite3_exec (db, rc == 0 ? "COMMIT" : "ROLLBACK", NULL, NULL, NULL);
  return rc;
}

/* Every view, trigger and table dropped, indexes with their tables, inside the caller's transaction. */
static int
sq_drop_all (sqlite3 *db)
{
  static const char *const kinds[] = { "view", "trigger", "table" };
  int k, rc = SQLITE_OK;
  for (k = 0; k < 3 && rc == SQLITE_OK; ++k)
    {
      sqlite3_stmt *st = NULL;
      char **names = NULL;
      int n = 0, i;
      rc = sqlite3_prepare_v2 (db, "SELECT name FROM sqlite_master WHERE type = ?1 AND name NOT LIKE 'sqlite_%'", -1, &st, NULL);
      if (rc != SQLITE_OK)
        break;
      sqlite3_bind_text (st, 1, kinds[k], -1, SQLITE_STATIC);
      while (sqlite3_step (st) == SQLITE_ROW)
        {
          names = realloc (names, (size_t) (n + 1) * sizeof *names);
          names[n++] = strdup ((const char *) sqlite3_column_text (st, 0));
        }
      sqlite3_finalize (st);
      for (i = 0; i < n; ++i)
        {
          char *q = sqlite3_mprintf ("DROP %s IF EXISTS \"%w\"", kinds[k], names[i]);
          if (rc == SQLITE_OK)
            rc = sqlite3_exec (db, q, NULL, NULL, NULL);
          sqlite3_free (q);
          free (names[i]);
        }
      free (names);
    }
  return rc;
}

static int
sq_statements (sqlite3 *db, struct amk_sink *out, const char *op, const char *prog)
{
  if (prog == NULL || *prog == '\0')
    {
      fprintf (stderr, "sqlite.%s: no statement\n", op);
      return SQLITE_STATUS_USAGE;
    }
  return sq_exec (db, out, op, prog);
}

/* The get member: the statements' rows to the sink; a statement that would write is refused. */
__attribute__ ((visibility ("default"))) int
sqlite_get (void *state, struct amk_sink *out, const char *prog)
{
  return sq_transaction (state, out, "get", prog, "BEGIN");
}

/* The update member: the statements, writes included, their rows to the sink; a row changed is reported, so a wait on the namespace wakes, and the calls the update routed run after it commits. */
__attribute__ ((visibility ("default"))) int
sqlite_update (void *state, struct amk_sink *out, const char *prog)
{
  sqlite3_int64 before = sqlite3_total_changes64 (state);
  int queued = sq_nroutes;
  int rc = sq_transaction (state, out, "update", prog, "BEGIN IMMEDIATE");
  if (sqlite3_total_changes64 (state) != before)
    amk_ns_changed ();
  if (rc != 0)
    sq_routes_drop (queued);
  else if (!sq_draining && sq_nroutes > 0 && sqlite3_get_autocommit (state))
    rc = sq_routes_drain (state);
  return rc;
}

/* The load member: the database replaced by the text's statements in one transaction, or left as it was. */
__attribute__ ((visibility ("default"))) int
sqlite_load (void *state, const char *text)
{
  sqlite3 *db = state;
  int rc;
  if (sqlite3_exec (db, "BEGIN", NULL, NULL, NULL) != SQLITE_OK || sq_drop_all (db) != SQLITE_OK)
    {
      fprintf (stderr, "sqlite.load: %s\n", sqlite3_errmsg (db));
      sqlite3_exec (db, "ROLLBACK", NULL, NULL, NULL);
      return SQLITE_STATUS_RUN;
    }
  rc = sq_exec (db, NULL, "load", text != NULL ? text : "");
  sqlite3_exec (db, rc == 0 ? "COMMIT" : "ROLLBACK", NULL, NULL, NULL);
  return rc;
}

/* The dump member: schema and rows, as the statements load replays. */
__attribute__ ((visibility ("default"))) int
sqlite_dump (void *state, struct amk_sink *out)
{
  return sq_dump (state, out);
}

/* The state as one blob and back, for a layer that carries engine state whole. */
__attribute__ ((visibility ("default"))) unsigned char *
sqlite_serialize (void *state, long long *len)
{
  sqlite3_int64 n = 0;
  unsigned char *p = sqlite3_serialize (state, "main", &n, 0);
  *len = n;
  return p;
}

__attribute__ ((visibility ("default"))) int
sqlite_deserialize (void *state, unsigned char *blob, long long len)
{
  return sqlite3_deserialize (state, "main", blob, len, len, SQLITE_DESERIALIZE_FREEONCLOSE | SQLITE_DESERIALIZE_RESIZEABLE) == SQLITE_OK ? 0 : SQLITE_STATUS_RUN;
}

/* JSON5 text as canonical JSON through sqlite's json(), on a private connection opened once; null with *err set when the text does not parse. */
__attribute__ ((visibility ("default"))) char *
sqlite_json5 (const char *text, const char **err)
{
  static sqlite3 *db;
  static sqlite3_stmt *st;
  char *r = NULL;

  if (st == NULL && (sqlite3_open (":memory:", &db) != SQLITE_OK
                     || sqlite3_prepare_v2 (db, "SELECT json(?1)", -1, &st, NULL) != SQLITE_OK))
    {
      *err = db != NULL ? sqlite3_errmsg (db) : "out of memory";
      return NULL;
    }
  sqlite3_bind_text (st, 1, text, -1, SQLITE_TRANSIENT);
  if (sqlite3_step (st) == SQLITE_ROW)
    r = strdup ((const char *) sqlite3_column_text (st, 0));
  else
    *err = sqlite3_errmsg (db);
  sqlite3_reset (st);
  return r;
}

extern int sqlite_shell_main (int argc, char **argv);

/* How many words a shell option takes after it, so a value is never read as a database name. */
static int
sq_option_values (const char *z)
{
  static const char *const one[] = { "-separator", "-nullvalue", "-newline", "-cmd", "-init", "-screenwidth", "-heap", "-threadsafe", "-mmap", "-sorterref", "-vfs", "-maxsize", "-nonce", "-escape", NULL };
  int i;
  if (z[1] == '-')
    ++z;
  if (strcmp (z, "-pagecache") == 0 || strcmp (z, "-lookaside") == 0)
    return 2;
  for (i = 0; one[i] != NULL; ++i)
    if (strcmp (z, one[i]) == 0)
      return 1;
  return 0;
}

static int
sq_blank (const char *s)
{
  return s[strspn (s, " \t\r\n")] == '\0';
}

/* One program into the shell's arguments: each dot-command line on its own, and the SQL between them as one argument; a dot line inside an unfinished statement stays SQL. */
static void
sq_split (const char *text, char **av, int *ac)
{
  size_t cap = strlen (text) + 2, len = 0;
  char *sql = malloc (cap);
  const char *line = text;
  sql[0] = '\0';
  while (*line != '\0')
    {
      const char *end = strchr (line, '\n');
      size_t n = end != NULL ? (size_t) (end - line) : strlen (line);
      const char *p = line + strspn (line, " \t");
      if (*p == '.' && (sq_blank (sql) || sqlite3_complete (sql)))
        {
          if (!sq_blank (sql))
            av[(*ac)++] = strdup (sql);
          len = 0;
          sql[0] = '\0';
          av[(*ac)++] = strndup (p, n - (size_t) (p - line));
        }
      else
        {
          memcpy (sql + len, line, n);
          len += n;
          sql[len++] = '\n';
          sql[len] = '\0';
        }
      line += end != NULL ? n + 1 : n;
    }
  if (!sq_blank (sql))
    av[(*ac)++] = sql;
}

/* The sqlite3 shell; after --, the database is in memory unless one was named before it, and each argument is a program of statements and dot-command lines, as a target or a builtin passes it. */
__attribute__ ((visibility ("default"))) int
sqlite_main (int argc, char **argv)
{
  char **av;
  const char *p;
  int i, k, ac = 0, named = 0, dashdash = -1, n = argc + 2;
  for (i = 1; i < argc && dashdash < 0; ++i)
    if (strcmp (argv[i], "--") == 0)
      dashdash = i;
  if (dashdash < 0)
    return sqlite_shell_main (argc, argv);
  for (i = dashdash + 1; i < argc; ++i)
    for (p = argv[i], n += 2; *p != '\0'; ++p)
      n += 2 * (*p == '\n');
  av = malloc ((size_t) (n + 1) * sizeof *av);
  av[ac++] = argv[0];
  for (i = 1; i < dashdash; ++i)
    {
      av[ac++] = argv[i];
      if (argv[i][0] != '-')
        named = 1;
      else
        for (k = sq_option_values (argv[i]); k > 0 && i + 1 < dashdash; --k)
          av[ac++] = argv[++i];
    }
  av[ac++] = (char *) "--";
  if (!named)
    av[ac++] = (char *) ":memory:";
  for (i = dashdash + 1; i < argc; ++i)
    sq_split (argv[i], av, &ac);
  av[ac] = NULL;
  return sqlite_shell_main (ac, av);
}
