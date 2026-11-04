/* The cypher guest: a sqlite workspace with GraphQLite registered once on its connection, so the cypher function and the graph schema are there from create. A get or update whose text is SQL is sqlite's; one whose text is Cypher goes through the cypher function with the bound names as its parameters, and its rows come back one per line. The extension's own schema is the engine's, not the data's: dump leaves its definitions out, and load puts them back before the text replays. The command line is sqlite's. */

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sqlite_guest.h"

struct sqlite3_api_routines;
extern int sqlite3_graphqlite_init (sqlite3 *db, char **err, const struct sqlite3_api_routines *api);

/* The schema the extension makes on an empty database, read once from a scratch connection: its statements, and the names of its tables. */
static char *cypher_schema;
static char **cypher_tables;
static int cypher_ntables;

static int
cypher_bootstrap (void)
{
  sqlite3 *db = NULL;
  sqlite3_stmt *st = NULL;
  int rc;
  if (cypher_schema != NULL)
    return SQLITE_OK;
  if ((rc = sqlite3_open (":memory:", &db)) != SQLITE_OK || (rc = sqlite3_graphqlite_init (db, NULL, NULL)) != SQLITE_OK
      || (rc = sqlite3_prepare_v2 (db, "SELECT name, sql, type FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid", -1, &st, NULL)) != SQLITE_OK)
    {
      sqlite3_close (db);
      return rc;
    }
  cypher_schema = strdup ("");
  while (sqlite3_step (st) == SQLITE_ROW)
    {
      char *next = sqlite3_mprintf ("%s%s;\n", cypher_schema, sqlite3_column_text (st, 1));
      free (cypher_schema);
      cypher_schema = strdup (next);
      sqlite3_free (next);
      if (strcmp ((const char *) sqlite3_column_text (st, 2), "table") == 0)
        {
          cypher_tables = realloc (cypher_tables, (size_t) (cypher_ntables + 1) * sizeof *cypher_tables);
          cypher_tables[cypher_ntables++] = strdup ((const char *) sqlite3_column_text (st, 0));
        }
    }
  sqlite3_finalize (st);
  sqlite3_close (db);
  return SQLITE_OK;
}

static int
cypher_own (const char *name)
{
  int i;
  for (i = 0; i < cypher_ntables; ++i)
    if (strcmp (cypher_tables[i], name) == 0)
      return 1;
  return 0;
}

static void *
cypher_register (sqlite3 *db)
{
  if (db != NULL && (cypher_bootstrap () != SQLITE_OK || sqlite3_graphqlite_init (db, NULL, NULL) != SQLITE_OK))
    {
      fprintf (stderr, "cypher: %s\n", sqlite3_errmsg (db));
      sqlite3_close (db);
      return NULL;
    }
  return db;
}

__attribute__ ((visibility ("default"))) void *
cypher_create (void)
{
  return cypher_register (sqlite_create ());
}

__attribute__ ((visibility ("default"))) void *
cypher_open (void *state, const char *path, int shared)
{
  return cypher_register (sqlite_open (state, path, shared));
}

/* The load member: every table dropped, the graph schema made again, then the text replayed, in one transaction; a graph the extension cached for its algorithms is let go. */
__attribute__ ((visibility ("default"))) int
cypher_load (void *state, const char *text)
{
  sqlite3 *db = state;
  int rc;
  if (sqlite3_exec (db, "BEGIN", NULL, NULL, NULL) != SQLITE_OK || sq_drop_all (db) != SQLITE_OK
      || sqlite3_exec (db, cypher_schema, NULL, NULL, NULL) != SQLITE_OK)
    {
      fprintf (stderr, "cypher.load: %s\n", sqlite3_errmsg (db));
      sqlite3_exec (db, "ROLLBACK", NULL, NULL, NULL);
      return SQLITE_STATUS_RUN;
    }
  rc = sq_exec (db, NULL, "load", text != NULL ? text : "");
  sqlite3_exec (db, rc == 0 ? "COMMIT" : "ROLLBACK", NULL, NULL, NULL);
  sqlite3_exec (db, "SELECT gql_unload_graph()", NULL, NULL, NULL);
  return rc;
}

/* The dump member: the rows of every table and the definitions of the ones that are not the extension's. */
__attribute__ ((visibility ("default"))) int
cypher_dump (void *state, struct amk_sink *out)
{
  return sq_dump (state, out, cypher_own);
}

/* The program past its bound names and deadline, as the statement loop would see it. */
static const char *
cy_tail (const char *prog)
{
  char word[4096];
  const char *p = prog, *tail = prog;
  for (;;)
    {
      tail = p;
      if (!amk_word (&p, word, sizeof word))
        break;
      if (strcmp (word, "--deadline") == 0)
        {
          if (!amk_word (&p, word, sizeof word))
            break;
          continue;
        }
      if (strcmp (word, "--arg") != 0 && strcmp (word, "--argjson") != 0)
        break;
      if (!amk_word (&p, word, sizeof word) || !amk_word (&p, word, sizeof word))
        break;
    }
  while (*tail == ' ' || *tail == '\t' || *tail == '\n')
    ++tail;
  return tail;
}

/* The next word of the text in upper case, and where it ends. */
static const char *
cy_word (const char *p, char *word, size_t size)
{
  size_t n = 0;
  while (*p == ' ' || *p == '\t' || *p == '\n')
    ++p;
  while (n + 1 < size && ((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || *p == '_'))
    word[n++] = (char) toupper ((unsigned char) *p++);
  word[n] = '\0';
  return p;
}

/* Whether a text is Cypher rather than SQL: it opens with a clause SQL has not, or with a create of a pattern rather than of a table. */
static int
cy_is_cypher (const char *text)
{
  static const char *const clauses[] = { "MATCH", "MERGE", "RETURN", "UNWIND", "OPTIONAL", "CALL", "FOREACH", NULL };
  char word[32];
  const char *p = cy_word (text, word, sizeof word);
  int i;
  for (i = 0; clauses[i] != NULL; ++i)
    if (strcmp (word, clauses[i]) == 0)
      return 1;
  if (strcmp (word, "CREATE") == 0)
    {
      while (*p == ' ' || *p == '\t' || *p == '\n')
        ++p;
      return *p == '(';
    }
  return 0;
}

/* Whether a Cypher text writes: a writing clause as a word outside its string literals. */
static int
cy_writes (const char *text)
{
  static const char *const writers[] = { "CREATE", "MERGE", "SET", "DELETE", "DETACH", "REMOVE", NULL };
  char word[32];
  const char *p = text;
  int i;
  while (*p != '\0')
    {
      if (*p == '\'' || *p == '"' || *p == '`')
        {
          char q = *p++;
          while (*p != '\0' && *p != q)
            p += (*p == '\\' && p[1] != '\0') ? 2 : 1;
          if (*p != '\0')
            ++p;
          continue;
        }
      if ((*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') || *p == '_')
        {
          p = cy_word (p, word, sizeof word);
          for (i = 0; writers[i] != NULL; ++i)
            if (strcmp (word, writers[i]) == 0)
              return 1;
          while ((*p >= '0' && *p <= '9'))
            ++p;
          continue;
        }
      ++p;
    }
  return 0;
}

/* One Cypher text through the cypher function, the bound names as its parameter object; an array answer prints one element per line, any other answer as one line. */
static int
cy_run (sqlite3 *db, struct amk_sink *out, const char *op, const char *prog)
{
  char *names[SQ_MAXARGS], *values[SQ_MAXARGS];
  int json[SQ_MAXARGS];
  int nargs, i, rc;
  long deadline;
  double at;
  char *sql, *params = NULL;
  sqlite3_stmt *st = NULL;
  const char *text = sq_args (op, prog, names, values, json, &nargs, &deadline);
  if (text == NULL)
    return SQLITE_STATUS_USAGE;
  if (strcmp (op, "get") == 0 && cy_writes (text))
    {
      fprintf (stderr, "cypher.get: a query that writes belongs in update: %s\n", text);
      return SQLITE_STATUS_USAGE;
    }
  for (i = 0; i < nargs; ++i)
    {
      char *next = sqlite3_mprintf ("%s%s?%d, %s(?%d)", params != NULL ? params : "", params != NULL ? ", " : "",
                                    2 * i + 2, json[i] ? "json" : "", 2 * i + 3);
      sqlite3_free (params);
      params = next;
    }
  sql = sqlite3_mprintf ("WITH c(j) AS (SELECT cypher(?1%s%s%s)) "
                         "SELECT e.value FROM c, json_each(c.j) AS e WHERE json_type(c.j) = 'array' "
                         "UNION ALL SELECT j FROM c WHERE json_type(c.j) <> 'array'",
                         nargs > 0 ? ", json_object(" : "", params != NULL ? params : "", nargs > 0 ? ")" : "");
  sqlite3_free (params);
  rc = sqlite3_prepare_v2 (db, sql, -1, &st, NULL);
  sqlite3_free (sql);
  if (rc != SQLITE_OK)
    {
      fprintf (stderr, "cypher.%s: %s\n", op, sqlite3_errmsg (db));
      return SQLITE_STATUS_RUN;
    }
  sqlite3_bind_text (st, 1, text, -1, SQLITE_STATIC);
  for (i = 0; i < nargs; ++i)
    {
      sqlite3_bind_text (st, 2 * i + 2, names[i], -1, SQLITE_STATIC);
      sqlite3_bind_text (st, 2 * i + 3, values[i], -1, SQLITE_STATIC);
    }
  if (deadline >= 0)
    {
      at = sq_now_ms () + (double) deadline;
      sqlite3_progress_handler (db, 1000, sq_deadline_check, &at);
    }
  while ((rc = sqlite3_step (st)) == SQLITE_ROW)
    if (out != NULL)
      {
        sq_puts (out, (const char *) sqlite3_column_text (st, 0));
        sq_puts (out, "\n");
      }
  if (rc != SQLITE_DONE)
    fprintf (stderr, "cypher.%s: %s\n", op, rc == SQLITE_INTERRUPT && deadline >= 0 ? "deadline" : sqlite3_errmsg (db));
  sqlite3_finalize (st);
  if (deadline >= 0)
    sqlite3_progress_handler (db, 0, NULL, NULL);
  for (i = 0; i < nargs; ++i)
    {
      free (names[i]);
      free (values[i]);
    }
  return rc == SQLITE_DONE ? 0 : SQLITE_STATUS_RUN;
}

/* The get and update members: Cypher through the function, SQL as sqlite's. */
__attribute__ ((visibility ("default"))) int
cypher_get (void *state, struct amk_sink *out, const char *prog)
{
  if (!cy_is_cypher (cy_tail (prog)))
    return sqlite_get (state, out, prog);
  return sq_transaction (state, out, "get", prog, "BEGIN", cy_run);
}

__attribute__ ((visibility ("default"))) int
cypher_update (void *state, struct amk_sink *out, const char *prog)
{
  if (!cy_is_cypher (cy_tail (prog)))
    return sqlite_update (state, out, prog);
  return sq_update (state, out, prog, cy_run);
}
