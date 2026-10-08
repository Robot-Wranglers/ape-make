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

/* A state with the standard libraries and the payload's lib/lua/ on the module path, so require finds the vendored modules the build zipped in. */
static lua_State *
lua_open_state (void)
{
  lua_State *L = luaL_newstate ();
  if (L == NULL)
    return NULL;
  luaL_openlibs (L);
  lua_getglobal (L, "package");
  lua_getfield (L, -1, "path");
  lua_pushfstring (L, "/zip/lib/lua/?.lua;%s", lua_tostring (L, -1));
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

/* amk.send(text): a line to the job's parent, from inside a spawned job. */
static int
lua_amk_send (lua_State *L)
{
  size_t len;
  const char *s = luaL_checklstring (L, 1, &len);
  lua_pushboolean (L, amk_mail_send (s, len) == 0);
  return 1;
}

/* Fires every thousand instructions, then on every instruction once the process's deadline has passed, so each frame that catches the error raises it again and the run unwinds to the call that set it. */
static void
lua_deadline_hook (lua_State *L, lua_Debug *ar)
{
  (void) ar;
  if (amk_deadline_expired ())
    {
      lua_sethook (L, lua_deadline_hook, LUA_MASKCOUNT, 1);
      lua_pushfstring (L, "deadline: %d ms", (int) amk_deadline_budget ());
      lua_error (L);
    }
}

/* Runs the function and arguments on the stack under the deadline hook, putting the hook before it back either way; answers lua_pcall's code. */
static int
lua_pcall_bounded (lua_State *L, int nargs, int nresults)
{
  lua_Hook hook = lua_gethook (L);
  int mask = lua_gethookmask (L), count = lua_gethookcount (L);
  int rc;
  lua_sethook (L, lua_deadline_hook, LUA_MASKCOUNT, 1000);
  rc = lua_pcall (L, nargs, nresults, 0);
  lua_sethook (L, hook, mask, count);
  return rc;
}

/* amk.deadline(ms, fn, ...): fn's results, or the error "deadline: ms ms" once ms milliseconds pass, in this guest or in any other it calls; a nested deadline keeps the tighter one. */
static int
lua_amk_deadline (lua_State *L)
{
  lua_Integer ms = luaL_checkinteger (L, 1);
  struct amk_deadline saved;
  long hit;
  int rc;

  luaL_argcheck (L, ms >= 0, 1, "must not be negative");
  luaL_checktype (L, 2, LUA_TFUNCTION);
  amk_deadline_push ((long) ms, &saved);
  rc = lua_pcall_bounded (L, lua_gettop (L) - 2, LUA_MULTRET);
  hit = amk_deadline_pop (&saved);
  if (rc != LUA_OK && hit >= 0)
    {
      lua_pushfstring (L, "deadline: %d ms", (int) hit);
      return lua_error (L);
    }
  if (rc != LUA_OK)
    return lua_error (L);
  return lua_gettop (L) - 1;
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
lua_amk_call_kind (lua_State *L, int kind, const char *who)
{
  const char *name = luaL_checkstring (L, 1), *err = NULL, **args;
  int n = lua_gettop (L) - 1, i;
  char *s;
  lua_need_make (L, who);
  for (i = 0; i < n; i++)
    luaL_checkstring (L, i + 2);
  args = malloc ((n + 1) * sizeof *args);
  for (i = 0; i < n; i++)
    args[i] = lua_tostring (L, i + 2);
  s = amk_call_kind (kind, name, (unsigned int) n, args, &err);
  free (args);
  if (s == NULL)
    return luaL_error (L, "%s: %s", who, err);
  lua_pushstring (L, s);
  gmk_free (s);
  return 1;
}

/* amk.call(name, ...): the cascade, a make function, the name under amk., a macro; amk.fxn and amk.macro take one layer by its full name. */
static int lua_amk_call (lua_State *L) { return lua_amk_call_kind (L, AMK_AS_ANY, "amk.call"); }
static int lua_amk_fxn_call (lua_State *L) { return lua_amk_call_kind (L, AMK_AS_FXN, "amk.fxn"); }
static int lua_amk_macro (lua_State *L) { return lua_amk_call_kind (L, AMK_AS_MACRO, "amk.macro"); }

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
/* amk.agoal(name): amk.acall of the goal function, a goal run in a fork as a handle. */
static int lua_amk_acall (lua_State *L);
static int
lua_amk_agoal (lua_State *L)
{
  luaL_checkstring (L, 1);
  lua_settop (L, 1);
  lua_pushliteral (L, "amk.goal");
  lua_insert (L, 1);
  return lua_amk_acall (L);
}

static int
lua_amk_acall_kind (lua_State *L, int kind, const char *who)
{
  const char *name = luaL_checkstring (L, 1), **args;
  int n = lua_gettop (L) - 1, i, fd = -1;
  pid_t pid;
  lua_need_make (L, who);
  for (i = 0; i < n; i++)
    luaL_checkstring (L, i + 2);
  args = malloc ((n + 1) * sizeof *args);
  for (i = 0; i < n; i++)
    args[i] = lua_tostring (L, i + 2);
  pid = amk_call_begin (kind, name, (unsigned int) n, args, &fd);
  free (args);
  if (pid < 0)
    return luaL_error (L, "%s: fork failed", who);
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

/* amk.acall(name, ...): the cascade begun in a fork, as a handle; amk.afxn and amk.amacro take one layer. */
static int lua_amk_acall (lua_State *L) { return lua_amk_acall_kind (L, AMK_AS_ANY, "amk.acall"); }
static int lua_amk_afxn (lua_State *L) { return lua_amk_acall_kind (L, AMK_AS_FXN, "amk.afxn"); }
static int lua_amk_amacro (lua_State *L) { return lua_amk_acall_kind (L, AMK_AS_MACRO, "amk.amacro"); }

/* An ask handle's result(): the reply waited for by the id kept as the upvalue, its text or the error raised. */
static int
lua_amk_ask_result (lua_State *L)
{
  unsigned long id = (unsigned long) lua_tointeger (L, lua_upvalueindex (1));
  const char *err = NULL;
  char *s;
  if (amk_ask_result (amk_ask_collect (id), &s, &err) < 0)
    return luaL_error (L, "amk.ask: %s", err);
  lua_pushstring (L, s);
  free (s);
  return 1;
}

/* amk.ask(op, namespace, values...): one request sent to the owner, as a handle with the id and result() that waits for the reply; the process goes on until then, and in the owner a request that would park is an error. */
static int
lua_amk_ask (lua_State *L)
{
  const char *op = luaL_checkstring (L, 1), *ns = luaL_checkstring (L, 2), **vals;
  int n = lua_gettop (L) - 2, i;
  char *line;
  long id;
  lua_need_make (L, "amk.ask");
  for (i = 0; i < n; i++)
    luaL_checkstring (L, i + 3);
  vals = malloc ((n + 1) * sizeof *vals);
  for (i = 0; i < n; i++)
    vals[i] = lua_tostring (L, i + 3);
  line = amk_ask_line (op, ns, (unsigned int) n, vals);
  free (vals);
  id = amk_ask_begin (line);
  free (line);
  if (id < 0)
    return luaL_error (L, "amk.ask: %s", AMK_ASK_PARKED);
  lua_newtable (L);
  lua_pushinteger (L, id);
  lua_setfield (L, -2, "id");
  lua_pushinteger (L, id);
  lua_pushcclosure (L, lua_amk_ask_result, 1);
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

/* amk.var[name] reads a variable, expanded, or nil when make has never seen the name; a read of raw is the raw proxy, its upvalue. */
static int
lua_amk_var_index (lua_State *L)
{
  char *s;
  const char *name = luaL_checkstring (L, 2);
  if (strcmp (name, "raw") == 0)
    {
      lua_pushvalue (L, lua_upvalueindex (1));
      return 1;
    }
  lua_need_make (L, "amk.var");
  s = amk_var_get (name);
  if (s == NULL)
    lua_pushnil (L);
  else
    {
      lua_pushstring (L, s);
      gmk_free (s);
    }
  return 1;
}

/* amk.var.raw[name] reads a variable's text as stored, never expanded, or nil when make has never seen the name. */
static int
lua_amk_var_raw_index (lua_State *L)
{
  char *s;
  lua_need_make (L, "amk.var.raw");
  s = amk_var_raw_get (luaL_checkstring (L, 2));
  if (s == NULL)
    lua_pushnil (L);
  else
    {
      lua_pushstring (L, s);
      gmk_free (s);
    }
  return 1;
}

/* amk.var.raw[name] = value defines a recursive variable with the text as written; nil is the empty string. */
static int
lua_amk_var_raw_newindex (lua_State *L)
{
  const char *name = luaL_checkstring (L, 2);
  lua_need_make (L, "amk.var.raw");
  if (lua_isnoneornil (L, 3))
    amk_var_raw_set (name, "");
  else
    {
      amk_var_raw_set (name, luaL_tolstring (L, 3, NULL));
      lua_pop (L, 1);
    }
  return 0;
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

/* make's call into a defined function, in the state that defined it: the arguments as strings, the result as text, and an error raised to whoever made the call. */
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
  if ((amk_deadline_active () ? lua_pcall_bounded (L, (int) argc, 1) : lua_pcall (L, (int) argc, 1, 0)) != LUA_OK)
    {
      const char *msg = lua_tostring (L, -1);
      if (!amk_deadline_expired ())
        amk_func_raise ("lua", nm, msg);
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

/* A missing amk field that names a make function, amk.name: a callable of that function whose own fields reach amk.name.field the same way, kept in the table; nil when make has no such function.  */
static const char *lua_amk_proxy_chunk =
  "local call = ...\n"
  "local function proxy(name)\n"
  "  return setmetatable({}, {\n"
  "    __call = function(_, ...) return call(name, ...) end,\n"
  "    __index = function(_, k) return proxy(name .. '.' .. k) end })\n"
  "end\n"
  "return proxy\n";

/* A missing amk field that the cascade resolves: a proxy calling amk.call by that name, whose own fields chain the dotted name on; nil when nothing answers. */
static int
lua_amk_proxy_for (lua_State *L, const char *name)
{
  char full[512];
  const char *err;
  if (amk_resolve (name, full, sizeof full, &err) < 0)
    {
      lua_pushnil (L);
      return 1;
    }
  if (lua_getfield (L, LUA_REGISTRYINDEX, "amk.proxy") != LUA_TFUNCTION)
    {
      lua_pop (L, 1);
      if (luaL_loadstring (L, lua_amk_proxy_chunk) != LUA_OK)
        return lua_error (L);
      lua_pushcfunction (L, lua_amk_call);
      lua_call (L, 1, 1);
      lua_pushvalue (L, -1);
      lua_setfield (L, LUA_REGISTRYINDEX, "amk.proxy");
    }
  lua_pushstring (L, name);
  lua_call (L, 1, 1);
  lua_pushvalue (L, 2);
  lua_pushvalue (L, -2);
  lua_rawset (L, 1);
  return 1;
}

/* A missing amk field names an amk module, the file lib/name/init.lua, loaded once by path and kept in the table; with no such file, what the cascade resolves the name to, else nil. */
static int
lua_amk_module (lua_State *L)
{
  const char *name = luaL_checkstring (L, 2);
  const char *path = lua_pushfstring (L, "/zip/lib/%s/init.lua", name);
  FILE *f;
  if ((f = fopen (path, "r")) == NULL)
    {
      lua_pop (L, 1);
      return lua_amk_proxy_for (L, name);
    }
  fclose (f);
  if (luaL_loadfile (L, path) != LUA_OK)
    return lua_error (L);
  lua_call (L, 0, 1);
  lua_pushvalue (L, 2);
  lua_pushvalue (L, -2);
  lua_rawset (L, 1);
  return 1;
}

/* The amk table on the stack, created on first use with an empty amk.on, the variable proxy, and the spawn api beside it. */
/* The handle's verbs, each a field of the amk table. */
static const luaL_Reg lua_amk_verbs[] = {
  { "expand", lua_amk_expand }, { "eval", lua_amk_eval },
  { "call", lua_amk_call }, { "fxn", lua_amk_fxn_call }, { "macro", lua_amk_macro },
  { "acall", lua_amk_acall }, { "afxn", lua_amk_afxn }, { "amacro", lua_amk_amacro }, { "agoal", lua_amk_agoal },
  { "ask", lua_amk_ask }, { "func", lua_amk_func },
  { "send", lua_amk_send }, { "exit_code", lua_amk_exit_code },
  { "deadline", lua_amk_deadline },
  { NULL, NULL },
};

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
      lua_newtable (L);
      lua_newtable (L);
      lua_pushcfunction (L, lua_amk_var_raw_index);
      lua_setfield (L, -2, "__index");
      lua_pushcfunction (L, lua_amk_var_raw_newindex);
      lua_setfield (L, -2, "__newindex");
      lua_setmetatable (L, -2);
      lua_pushcclosure (L, lua_amk_var_index, 1);
      lua_setfield (L, -2, "__index");
      lua_pushcfunction (L, lua_amk_var_newindex);
      lua_setfield (L, -2, "__newindex");
      lua_setmetatable (L, -2);
      lua_setfield (L, -2, "var");
      luaL_setfuncs (L, lua_amk_verbs, 0);
      lua_newtable (L);
      lua_pushcfunction (L, lua_amk_module);
      lua_setfield (L, -2, "__index");
      lua_setmetatable (L, -2);
      lua_pushvalue (L, -1);
      lua_setglobal (L, "amk");
    }
}

/* The create member: a kept state, which make holds for the life of the process, with print and io bound to the sink and the handle in place. */
__attribute__ ((visibility ("default"))) void *
lua_create (void)
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

/* exec runs the chunk in the state with its output to the sink; import runs it with print on stderr, then hands make the globals it defined or rebound and the sink their names. */
static int
lua_run_op (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  lua_State *L = state;
  int export = strcmp (op, "import") == 0;
  int rc;

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

__attribute__ ((visibility ("default"))) int
lua_exec (void *state, struct amk_sink *out, const char *prog)
{
  return lua_run_op (state, out, "exec", prog);
}

__attribute__ ((visibility ("default"))) int
lua_import (void *state, struct amk_sink *out, const char *prog)
{
  return lua_run_op (state, out, "import", prog);
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
