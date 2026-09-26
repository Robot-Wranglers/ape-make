/* The lua guest's entry point: amk links the library, not the lua cli, so it supplies this. */

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>

#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"

#include "amk_guest.h"

static void lua_push_amk (lua_State *L);

/* A state with the standard libraries and the payload's lib/ on the module path, so require finds what the build zipped in. */
static lua_State *
lua_open_state (void)
{
  lua_State *L = luaL_newstate ();
  if (L == NULL)
    return NULL;
  luaL_openlibs (L);
  lua_getglobal (L, "package");
  lua_getfield (L, -1, "path");
  lua_pushfstring (L, "/zip/lib/?.lua;%s", lua_tostring (L, -1));
  lua_setfield (L, -3, "path");
  lua_pop (L, 2);
  return L;
}

/* Run one chunk on the state and report its error, if any, on stderr. */
static int
lua_run_chunk (lua_State *L, const char *chunk)
{
  int rc = luaL_loadstring (L, chunk);
  if (rc == LUA_OK)
    rc = lua_pcall (L, 0, 0, 0);
  if (rc != LUA_OK)
    {
      const char *msg = lua_tostring (L, -1);
      fprintf (stderr, "lua: %s\n", msg ? msg : "unknown error");
      lua_pop (L, 1);
    }
  return rc == LUA_OK ? 0 : 1;
}

/* argv[1] is Lua source text rather than a command line; whatever it prints is the result. */
__attribute__ ((visibility ("default"))) int
lua_run_main (int argc, char **argv)
{
  lua_State *L;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "lua: no chunk\n");
      return 2;
    }

  L = lua_open_state ();
  if (L == NULL)
    {
      fprintf (stderr, "lua: cannot create state\n");
      return 1;
    }
  lua_push_amk (L);
  lua_pop (L, 1);

  rc = lua_run_chunk (L, argv[1]);
  lua_close (L);
  fflush (stdout);
  return rc;
}

/* Where the persistent state's output goes: make's sink during a call, stderr between calls. */
static struct amk_sink *lua_sink = &amk_sink_stderr;

static void
lua_emit (const char *s, size_t n)
{
  lua_sink->write (lua_sink, s, n);
}

/* The persistent form of print, into the sink. */
static int
lua_persist_print (lua_State *L)
{
  int n = lua_gettop (L);
  int i;
  for (i = 1; i <= n; i++)
    {
      size_t len;
      const char *s = luaL_tolstring (L, i, &len);
      if (i > 1)
        lua_emit ("\t", 1);
      lua_emit (s, len);
      lua_pop (L, 1);
    }
  lua_emit ("\n", 1);
  return 0;
}

/* io.write and the output object's write: strings and numbers from the given argument on, into the sink; the output object comes back for chaining. */
static int
lua_persist_write_from (lua_State *L, int first)
{
  int n = lua_gettop (L);
  int i;
  for (i = first; i <= n; i++)
    {
      size_t len;
      const char *s = luaL_checklstring (L, i, &len);
      lua_emit (s, len);
    }
  lua_pushvalue (L, lua_upvalueindex (1));
  return 1;
}

static int
lua_persist_iowrite (lua_State *L)
{
  return lua_persist_write_from (L, 1);
}

static int
lua_persist_fwrite (lua_State *L)
{
  return lua_persist_write_from (L, 2);
}

static int
lua_persist_flush (lua_State *L)
{
  lua_pushvalue (L, 1);
  return 1;
}

/* The output object answers a close with a refusal and stays open, since the sink is the caller's. */
static int
lua_persist_noclose (lua_State *L)
{
  lua_pushnil (L);
  lua_pushliteral (L, "the collecting stream stays open");
  return 2;
}

/* io.output and io.close for the default output mean the output object; for anything else they are the library's own, its second upvalue. */
static int
lua_persist_delegate (lua_State *L)
{
  lua_pushvalue (L, lua_upvalueindex (2));
  lua_insert (L, 1);
  lua_call (L, lua_gettop (L) - 1, LUA_MULTRET);
  return lua_gettop (L);
}

static int
lua_persist_output (lua_State *L)
{
  if (lua_isnoneornil (L, 1))
    {
      lua_pushvalue (L, lua_upvalueindex (1));
      return 1;
    }
  return lua_persist_delegate (L);
}

static int
lua_persist_close (lua_State *L)
{
  if (lua_isnoneornil (L, 1) || lua_rawequal (L, 1, lua_upvalueindex (1)))
    return lua_persist_noclose (L);
  return lua_persist_delegate (L);
}

/* Once per persistent state: print, io.write, io.stdout, and io.output and io.close for the default, all write through the sink pointer. */
static void
lua_bind_sink (lua_State *L)
{
  lua_pushcfunction (L, lua_persist_print);
  lua_setglobal (L, "print");
  lua_getglobal (L, "io");
  lua_newtable (L);
  lua_pushvalue (L, -1);
  lua_pushcclosure (L, lua_persist_fwrite, 1);
  lua_setfield (L, -2, "write");
  lua_pushcfunction (L, lua_persist_flush);
  lua_setfield (L, -2, "flush");
  lua_pushcfunction (L, lua_persist_noclose);
  lua_setfield (L, -2, "close");
  lua_pushvalue (L, -1);
  lua_setfield (L, -3, "stdout");
  lua_pushvalue (L, -1);
  lua_pushcclosure (L, lua_persist_iowrite, 1);
  lua_setfield (L, -3, "write");
  lua_pushvalue (L, -1);
  lua_getfield (L, -3, "output");
  lua_pushcclosure (L, lua_persist_output, 2);
  lua_setfield (L, -3, "output");
  lua_pushvalue (L, -1);
  lua_getfield (L, -3, "close");
  lua_pushcclosure (L, lua_persist_close, 2);
  lua_setfield (L, -3, "close");
  lua_pop (L, 2);
}

/* Whether the state is one make keeps, as against a one-shot call's that ends with the call. */
static int
lua_is_kept (lua_State *L)
{
  int kept;
  lua_getfield (L, LUA_REGISTRYINDEX, "amk.kept");
  kept = lua_toboolean (L, -1);
  lua_pop (L, 1);
  return kept;
}

/* amk.spawn(goals[, opts]): a fork of this parsed image runs the listed goals as its own process group and its pid comes back; opts.foreground hands it the terminal, opts.stdout names a file for its output. */
static int
lua_amk_spawn (lua_State *L)
{
  char *words[64];
  lua_Integer n, i;
  int foreground = 0;
  const char *stdout_path = NULL;
  pid_t pid;

  luaL_checktype (L, 1, LUA_TTABLE);
  if (lua_istable (L, 2))
    {
      lua_getfield (L, 2, "foreground");
      foreground = lua_toboolean (L, -1);
      lua_pop (L, 1);
      lua_getfield (L, 2, "stdout");
      stdout_path = lua_tostring (L, -1);
      lua_pop (L, 1);
    }
  n = luaL_len (L, 1);
  if (n < 1 || n > 63)
    return luaL_error (L, "amk.spawn: between 1 and 63 goals");
  for (i = 1; i <= n; i++)
    {
      lua_geti (L, 1, i);
      words[i - 1] = (char *) luaL_checkstring (L, -1);
      lua_pop (L, 1);
    }
  words[n] = NULL;
  pid = amk_spawn_goals ((int) n, words, foreground, stdout_path);
  if (pid < 0)
    return luaL_error (L, "amk.spawn: fork failed");
  lua_pushinteger (L, pid);
  return 1;
}

/* amk.wait([pid[, block]]): the finished or stopped child as a table, or nil when none has and block is false. */
static int
lua_amk_wait (lua_State *L)
{
  pid_t want = (pid_t) luaL_optinteger (L, 1, 0);
  int block = lua_isnoneornil (L, 2) ? 1 : lua_toboolean (L, 2);
  pid_t got = 0;
  int code = 0, sig = 0, stopped = 0;

  if (amk_wait_child (want, block, &got, &code, &sig, &stopped) <= 0)
    {
      lua_pushnil (L);
      return 1;
    }
  lua_newtable (L);
  lua_pushinteger (L, got);
  lua_setfield (L, -2, "pid");
  lua_pushinteger (L, code);
  lua_setfield (L, -2, "code");
  lua_pushinteger (L, sig);
  lua_setfield (L, -2, "signal");
  lua_pushstring (L, stopped ? "stopped" : sig ? "signal" : code == 0 ? "success" : code == 1 ? "question" : "failed");
  lua_setfield (L, -2, "status");
  if (!stopped)
    {
      char *mail = NULL;
      size_t len = 0;
      if (amk_mail_take (got, &mail, &len))
        {
          lua_pushlstring (L, mail, len);
          free (mail);
        }
      else
        lua_pushliteral (L, "");
      lua_setfield (L, -2, "mail");
    }
  return 1;
}

/* amk.send(text): a line to the job's parent, from inside a spawned job. */
static int
lua_amk_send (lua_State *L)
{
  size_t len;
  const char *s = luaL_checklstring (L, 1, &len);
  lua_pushboolean (L, amk_mail_send (s, len) == 0);
  return 1;
}

/* amk.kill(pid[, signal]): the signal, by default terminate, to a spawned job and every shell under it. */
static int
lua_amk_kill (lua_State *L)
{
  pid_t pid = (pid_t) luaL_checkinteger (L, 1);
  int sig = (int) luaL_optinteger (L, 2, SIGTERM);
  lua_pushboolean (L, amk_kill_child (pid, sig) == 0);
  return 1;
}

/* amk.foreground(pid): the terminal to a spawned job, and the job continued if it was stopped. */
static int
lua_amk_foreground (lua_State *L)
{
  pid_t pid = (pid_t) luaL_checkinteger (L, 1);
  lua_pushboolean (L, amk_foreground (pid) == 0);
  return 1;
}

/* Under the engine flag make has parsed nothing, so the handle refuses rather than reads. */
static void
lua_need_make (lua_State *L, const char *what)
{
  if (!amk_has_db ())
    luaL_error (L, "%s: no make database, running outside a makefile", what);
}

/* amk.expand(text): the text expanded by make. */
static int
lua_amk_expand (lua_State *L)
{
  const char *text = luaL_checkstring (L, 1);
  char *s;
  lua_need_make (L, "amk.expand");
  s = gmk_expand (text);
  lua_pushstring (L, s ? s : "");
  gmk_free (s);
  return 1;
}

/* amk.call(name, ...): the make function or macro of that name, each further argument one whole value, never expanded. */
static int
lua_amk_call (lua_State *L)
{
  const char *name = luaL_checkstring (L, 1), *err = NULL, **args;
  int n = lua_gettop (L) - 1, i;
  char *s;
  lua_need_make (L, "amk.call");
  for (i = 0; i < n; i++)
    luaL_checkstring (L, i + 2);
  args = malloc ((n + 1) * sizeof *args);
  for (i = 0; i < n; i++)
    args[i] = lua_tostring (L, i + 2);
  s = amk_call (name, (unsigned int) n, args, &err);
  free (args);
  if (s == NULL)
    return luaL_error (L, "amk.call: %s", err);
  lua_pushstring (L, s);
  gmk_free (s);
  return 1;
}

/* A handle's result(): the call collected by the pid kept as the upvalue, its text or the error raised. */
static int
lua_amk_call_result (lua_State *L)
{
  pid_t pid = (pid_t) lua_tointeger (L, lua_upvalueindex (1));
  const char *err = NULL;
  char *s;
  if (amk_call_end (pid, &s, &err) < 0)
    return luaL_error (L, "amk.acall: %s", err);
  lua_pushstring (L, s);
  free (s);
  return 1;
}

/* amk.acall(name, values...): the call begun in a fork, as a handle with the pid, the fd that reads as done when the result is in, and result() that collects it. */
static int
lua_amk_acall (lua_State *L)
{
  const char *name = luaL_checkstring (L, 1), **args;
  int n = lua_gettop (L) - 1, i, fd = -1;
  pid_t pid;
  lua_need_make (L, "amk.acall");
  for (i = 0; i < n; i++)
    luaL_checkstring (L, i + 2);
  args = malloc ((n + 1) * sizeof *args);
  for (i = 0; i < n; i++)
    args[i] = lua_tostring (L, i + 2);
  pid = amk_call_begin (name, (unsigned int) n, args, &fd);
  free (args);
  if (pid < 0)
    return luaL_error (L, "amk.acall: fork failed");
  lua_newtable (L);
  lua_pushinteger (L, pid);
  lua_setfield (L, -2, "pid");
  lua_pushinteger (L, fd);
  lua_setfield (L, -2, "fd");
  lua_pushinteger (L, pid);
  lua_pushcclosure (L, lua_amk_call_result, 1);
  lua_setfield (L, -2, "result");
  return 1;
}

/* amk.eval(text): the text read by make as makefile syntax. */
static int
lua_amk_eval (lua_State *L)
{
  lua_need_make (L, "amk.eval");
  amk_eval (luaL_checkstring (L, 1));
  return 0;
}

/* amk.var[name] reads a variable, expanded, or nil when make has never seen the name. */
static int
lua_amk_var_index (lua_State *L)
{
  char *s;
  lua_need_make (L, "amk.var");
  s = amk_var_get (luaL_checkstring (L, 2));
  if (s == NULL)
    lua_pushnil (L);
  else
    {
      lua_pushstring (L, s);
      gmk_free (s);
    }
  return 1;
}

/* amk.var[name] = value defines a simple variable with the literal text of the value; nil is the empty string. */
static int
lua_amk_var_newindex (lua_State *L)
{
  const char *name = luaL_checkstring (L, 2);
  lua_need_make (L, "amk.var");
  if (lua_isnoneornil (L, 3))
    amk_var_set (name, "");
  else
    {
      amk_var_set (name, luaL_tolstring (L, 3, NULL));
      lua_pop (L, 1);
    }
  return 0;
}

/* The registry table of make functions the persistent state has defined, by name, on the stack. */
static void
lua_push_func_table (lua_State *L)
{
  if (lua_getfield (L, LUA_REGISTRYINDEX, "amk.func") != LUA_TTABLE)
    {
      lua_pop (L, 1);
      lua_newtable (L);
      lua_pushvalue (L, -1);
      lua_setfield (L, LUA_REGISTRYINDEX, "amk.func");
    }
}

/* make's call into a defined function, in the state that defined it: the arguments as strings, the result as text, and an error reported on stderr and answered empty. */
static char *
lua_func_call (void *state, const char *nm, unsigned int argc, char **argv)
{
  lua_State *L = state;
  const char *s = "";
  size_t len = 0;
  unsigned int i;
  char *out;

  if (L == NULL)
    return NULL;
  lua_push_func_table (L);
  if (lua_getfield (L, -1, nm) != LUA_TFUNCTION)
    {
      lua_pop (L, 2);
      return NULL;
    }
  for (i = 0; i < argc; i++)
    lua_pushstring (L, argv[i]);
  if (lua_pcall (L, (int) argc, 1, 0) != LUA_OK)
    {
      const char *msg = lua_tostring (L, -1);
      fprintf (stderr, "lua $(%s ...): %s\n", nm, msg ? msg : "unknown error");
      lua_pop (L, 2);
      return NULL;
    }
  if (!lua_isnoneornil (L, -1))
    s = luaL_tolstring (L, -1, &len);
  else
    lua_pushliteral (L, "");
  out = gmk_alloc ((unsigned int) len + 1);
  memcpy (out, s, len);
  out[len] = '\0';
  lua_pop (L, 3);
  return out;
}

/* The function at idx becomes make's function of that name, or replaces the one this state defined before; a name make has from elsewhere is an error. */
static void
lua_define_func (lua_State *L, const char *name, int idx)
{
  idx = lua_absindex (L, idx);
  if (amk_func_add (name, L, lua_func_call) < 0)
    luaL_error (L, "amk.func: %s is a make function already", name);
  lua_push_func_table (L);
  lua_pushvalue (L, idx);
  lua_setfield (L, -2, name);
  lua_pop (L, 1);
}

/* amk.func(name, fn): make gains a function of that name whose arguments, expanded, reach fn as strings and whose result is what fn returns; only a kept state outlives the call to answer. */
static int
lua_amk_func (lua_State *L)
{
  const char *name = luaL_checkstring (L, 1);
  luaL_checktype (L, 2, LUA_TFUNCTION);
  if (!lua_is_kept (L))
    return luaL_error (L, "amk.func: only from lua.exec, since a one-shot call's state ends with the call");
  lua_need_make (L, "amk.func");
  lua_define_func (L, name, 2);
  return 0;
}

/* Whether the table at idx is a sequence: a first element and nothing under a string key. */
static int
lua_is_sequence (lua_State *L, int idx)
{
  int seq;
  idx = lua_absindex (L, idx);
  if (lua_rawgeti (L, idx, 1) == LUA_TNIL)
    {
      lua_pop (L, 1);
      return 0;
    }
  lua_pop (L, 1);
  seq = 1;
  lua_pushnil (L);
  while (lua_next (L, idx))
    {
      if (lua_type (L, -2) != LUA_TNUMBER)
        seq = 0;
      lua_pop (L, 1);
    }
  return seq;
}

/* The exported names, space separated, grown in C so the Lua stack stays free for the walk. */
struct lua_names
{
  char *s;
  size_t n, cap;
};

static void
lua_names_add (struct lua_names *names, const char *name)
{
  size_t len = strlen (name);
  if (names->n + len + 2 > names->cap)
    names->s = realloc (names->s, names->cap = (names->n + len + 2) * 2);
  if (names->n > 0)
    names->s[names->n++] = ' ';
  memcpy (names->s + names->n, name, len);
  names->n += len;
  names->s[names->n] = '\0';
}

static void lua_export_value (lua_State *L, const char *name, int idx, struct lua_names *names);

static int
lua_name_cmp (const void *a, const void *b)
{
  return strcmp (*(const char *const *) a, *(const char *const *) b);
}

/* The string keys of the table at idx, sorted, in a malloc'd array the caller frees; the strings stay the table's. */
static const char **
lua_sorted_keys (lua_State *L, int idx, size_t *count)
{
  const char **keys = NULL;
  size_t n = 0, cap = 0;
  idx = lua_absindex (L, idx);
  lua_pushnil (L);
  while (lua_next (L, idx))
    {
      if (lua_type (L, -2) == LUA_TSTRING)
        {
          if (n == cap)
            keys = realloc (keys, (cap += 32) * sizeof *keys);
          keys[n++] = lua_tostring (L, -2);
        }
      lua_pop (L, 1);
    }
  qsort (keys, n, sizeof *keys, lua_name_cmp);
  *count = n;
  return keys;
}

/* A table with string keys: one variable per key as name.key, in key order, recursing. */
static void
lua_export_fields (lua_State *L, const char *name, int idx, struct lua_names *names)
{
  size_t n, i;
  const char **keys;
  idx = lua_absindex (L, idx);
  keys = lua_sorted_keys (L, idx, &n);
  for (i = 0; i < n; i++)
    {
      if (!amk_name_ok (keys[i]))
        {
          free (keys);
          luaL_error (L, "amk import: %s has a key make cannot spell: %s", name, keys[i]);
        }
      lua_pushfstring (L, "%s.%s", name, keys[i]);
      lua_getfield (L, idx, keys[i]);
      lua_export_value (L, lua_tostring (L, -2), -1, names);
      lua_pop (L, 2);
    }
  free (keys);
}

/* One global into make: a function as a make function, a sequence as words, a table as fields, a boolean as true or nothing, and a string or number as its text; nil and anything else are skipped. */
static void
lua_export_value (lua_State *L, const char *name, int idx, struct lua_names *names)
{
  luaL_Buffer words;
  idx = lua_absindex (L, idx);
  switch (lua_type (L, idx))
    {
    case LUA_TFUNCTION:
      lua_define_func (L, name, idx);
      break;
    case LUA_TSTRING:
    case LUA_TNUMBER:
      amk_var_set (name, lua_tostring (L, idx));
      break;
    case LUA_TBOOLEAN:
      amk_var_set (name, lua_toboolean (L, idx) ? "true" : "");
      break;
    case LUA_TTABLE:
      if (!lua_is_sequence (L, idx))
        {
          lua_export_fields (L, name, idx, names);
          return;
        }
      luaL_buffinit (L, &words);
      {
        lua_Integer i, n = luaL_len (L, idx);
        for (i = 1; i <= n; i++)
          {
            lua_rawgeti (L, idx, i);
            if (i > 1)
              luaL_addchar (&words, ' ');
            luaL_addvalue (&words);
          }
      }
      luaL_pushresult (&words);
      amk_var_set (name, lua_tostring (L, -1));
      lua_pop (L, 1);
      break;
    default:
      return;
    }
  lua_names_add (names, name);
}

/* The globals as they were before an export chunk, kept in the registry so what the chunk added or rebound can be told apart. */
static void
lua_snapshot_globals (lua_State *L)
{
  lua_newtable (L);
  lua_pushglobaltable (L);
  lua_pushnil (L);
  while (lua_next (L, -2))
    {
      lua_pushvalue (L, -2);
      lua_pushvalue (L, -2);
      lua_rawset (L, -6);
      lua_pop (L, 1);
    }
  lua_pop (L, 1);
  lua_setfield (L, LUA_REGISTRYINDEX, "amk.before");
}

/* Every global that is new or rebound since the snapshot, exported in name order, and the names to the sink given as the argument. */
static int
lua_export_globals (lua_State *L)
{
  struct amk_sink *out = lua_touserdata (L, 1);
  const char **names;
  size_t n, i;
  struct lua_names exported = { NULL, 0, 0 };

  lua_getfield (L, LUA_REGISTRYINDEX, "amk.before");
  lua_pushglobaltable (L);
  names = lua_sorted_keys (L, -1, &n);
  for (i = 0; i < n; i++)
    {
      if (!amk_name_ok (names[i]))
        continue;
      lua_getfield (L, -1, names[i]);
      lua_getfield (L, -3, names[i]);
      if (!lua_rawequal (L, -1, -2))
        lua_export_value (L, names[i], -2, &exported);
      lua_pop (L, 2);
    }
  free (names);
  if (exported.n > 0)
    out->write (out, exported.s, exported.n);
  out->write (out, "\n", 1);
  free (exported.s);
  return 0;
}

/* The status this process leaves with, whatever make's own turns out to be. */
static int
lua_amk_exit_code (lua_State *L)
{
  amk_exit_with ((int) luaL_checkinteger (L, 1));
  return 0;
}

/* The amk table on the stack, created on first use with an empty amk.on, the variable proxy, and the spawn api beside it. */
static void
lua_push_amk (lua_State *L)
{
  if (lua_getglobal (L, "amk") != LUA_TTABLE)
    {
      lua_pop (L, 1);
      lua_newtable (L);
      lua_newtable (L);
      lua_setfield (L, -2, "on");
      lua_newtable (L);
      lua_newtable (L);
      lua_pushcfunction (L, lua_amk_var_index);
      lua_setfield (L, -2, "__index");
      lua_pushcfunction (L, lua_amk_var_newindex);
      lua_setfield (L, -2, "__newindex");
      lua_setmetatable (L, -2);
      lua_setfield (L, -2, "var");
      lua_pushcfunction (L, lua_amk_expand);
      lua_setfield (L, -2, "expand");
      lua_pushcfunction (L, lua_amk_eval);
      lua_setfield (L, -2, "eval");
      lua_pushcfunction (L, lua_amk_call);
      lua_setfield (L, -2, "call");
      lua_pushcfunction (L, lua_amk_acall);
      lua_setfield (L, -2, "acall");
      lua_pushcfunction (L, lua_amk_func);
      lua_setfield (L, -2, "func");
      lua_pushcfunction (L, lua_amk_spawn);
      lua_setfield (L, -2, "spawn");
      lua_pushcfunction (L, lua_amk_wait);
      lua_setfield (L, -2, "wait");
      lua_pushcfunction (L, lua_amk_kill);
      lua_setfield (L, -2, "kill");
      lua_pushcfunction (L, lua_amk_foreground);
      lua_setfield (L, -2, "foreground");
      lua_pushcfunction (L, lua_amk_send);
      lua_setfield (L, -2, "send");
      lua_pushcfunction (L, lua_amk_exit_code);
      lua_setfield (L, -2, "exit_code");
      lua_pushvalue (L, -1);
      lua_setglobal (L, "amk");
    }
}

/* The open primitive: a kept state, which make holds for the life of the process, with print and io bound to the sink and the handle in place. */
__attribute__ ((visibility ("default"))) void *
lua_open (void)
{
  lua_State *L = lua_open_state ();
  if (L == NULL)
    {
      fprintf (stderr, "lua: cannot create state\n");
      return NULL;
    }
  lua_bind_sink (L);
  lua_pushboolean (L, 1);
  lua_setfield (L, LUA_REGISTRYINDEX, "amk.kept");
  lua_push_amk (L);
  lua_pop (L, 1);
  return L;
}

/* The run primitive: exec runs the chunk in the state with its output to the sink; import runs it with print on stderr, then hands make the globals it defined or rebound and the sink their names. */
__attribute__ ((visibility ("default"))) int
lua_run (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  lua_State *L = state;
  int export = strcmp (op, "import") == 0;
  int rc;

  if (!export && strcmp (op, "exec") != 0)
    {
      fprintf (stderr, "lua: unknown operation %s\n", op);
      return 2;
    }
  if (prog == NULL)
    {
      fprintf (stderr, "lua.%s: no chunk\n", op);
      return 2;
    }

  lua_sink = export ? &amk_sink_stderr : out;
  if (export)
    lua_snapshot_globals (L);
  rc = lua_run_chunk (L, prog);
  if (export && rc == 0)
    {
      lua_pushcfunction (L, lua_export_globals);
      lua_pushlightuserdata (L, out);
      if (lua_pcall (L, 1, 0, 0) != LUA_OK)
        {
          const char *msg = lua_tostring (L, -1);
          fprintf (stderr, "lua.import: %s\n", msg ? msg : "unknown error");
          lua_pop (L, 1);
          rc = 1;
        }
    }
  lua_sink = &amk_sink_stderr;
  return rc;
}

/* The hook primitive: amk.on[event], when the state holds a function there, is called with the event as a table. Its print goes to stderr, and an error reports there and is otherwise ignored. */
__attribute__ ((visibility ("default"))) void
lua_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  lua_State *L = state;

  lua_push_amk (L);
  if (lua_getfield (L, -1, "on") != LUA_TTABLE
      || lua_getfield (L, -1, event) != LUA_TFUNCTION)
    {
      lua_settop (L, 0);
      return;
    }

  lua_newtable (L);
  lua_pushstring (L, event);
  lua_setfield (L, -2, "event");
  lua_pushstring (L, target);
  lua_setfield (L, -2, "target");
  lua_pushstring (L, status);
  lua_setfield (L, -2, "status");
  lua_pushinteger (L, exit_code);
  lua_setfield (L, -2, "code");
  lua_pushinteger (L, exit_sig);
  lua_setfield (L, -2, "signal");
  lua_pushinteger (L, pid);
  lua_setfield (L, -2, "pid");

  if (lua_pcall (L, 1, 0, 0) != LUA_OK)
    {
      const char *msg = lua_tostring (L, -1);
      fprintf (stderr, "lua hook %s: %s\n", event, msg ? msg : "unknown error");
    }
  lua_settop (L, 0);
}
