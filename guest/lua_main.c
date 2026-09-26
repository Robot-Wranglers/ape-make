/* The lua guest's entry point: amk links the library, not the lua cli, so it supplies this. */

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>

#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"

/* make's side of the spawn api, resolved at link; the guest keeps no header of make's. */
extern pid_t amk_spawn_goals (int n, char **words, int foreground, const char *stdout_path);
extern int amk_wait_child (pid_t want, int block, pid_t *got, int *code, int *sig, int *stopped);
extern int amk_kill_child (pid_t pid, int sig);
extern int amk_foreground (pid_t pid);
extern int amk_mail_take (pid_t pid, char **buf, size_t *len);
extern int amk_mail_send (const char *s, size_t n);

/* make's sink, where the persistent entry's result goes: one write function, and make decides where the bytes land. */
struct amk_sink
{
  void (*write) (struct amk_sink *, const char *, size_t);
};
extern struct amk_sink amk_sink_stderr;

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

/* The one state the persistent entry and the hook share, kept for the life of the process. */
static lua_State *persistent;

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

/* The amk table on the stack, created on first use with an empty amk.on and the spawn api beside it. */
static void
lua_push_amk (lua_State *L)
{
  if (lua_getglobal (L, "amk") != LUA_TTABLE)
    {
      lua_pop (L, 1);
      lua_newtable (L);
      lua_newtable (L);
      lua_setfield (L, -2, "on");
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
      lua_pushvalue (L, -1);
      lua_setglobal (L, "amk");
    }
}

/* The persistent entry: one state for the life of the process, so globals set by one chunk are there for the next. Output goes to the sink, and argv[2], if any, is amk.input. */
__attribute__ ((visibility ("default"))) int
lua_persist_main (struct amk_sink *out, int argc, char **argv)
{
  lua_State *L = persistent;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "lua.persistent: no chunk\n");
      return 2;
    }
  if (L == NULL)
    {
      L = persistent = lua_open_state ();
      if (L == NULL)
        {
          fprintf (stderr, "lua.persistent: cannot create state\n");
          return 1;
        }
      lua_bind_sink (L);
    }

  lua_sink = out;
  lua_push_amk (L);
  if (argc > 2 && argv[2] != NULL)
    lua_pushstring (L, argv[2]);
  else
    lua_pushliteral (L, "");
  lua_setfield (L, -2, "input");
  lua_pop (L, 1);

  rc = lua_run_chunk (L, argv[1]);
  lua_sink = &amk_sink_stderr;
  return rc;
}

/* The hook entry: amk.on[event], when the persistent state holds a function there, is called with the event as a table. Its print goes to stderr, and an error reports there and is otherwise ignored. */
__attribute__ ((visibility ("default"))) void
lua_hook_main (const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  lua_State *L = persistent;

  if (L == NULL)
    return;
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
