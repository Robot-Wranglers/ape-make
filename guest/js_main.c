/* The quickjs guest's entry point: amk links the engine and its std library, not the qjs cli, so it supplies this. */

#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "quickjs.h"
#include "quickjs-libc.h"
#include "amk_guest.h"

/* The std and os modules are bound as globals the way qjs does it, so a plain chunk can use them without import. */
static const char *js_guest_prelude =
  "import * as std from 'std';\n"
  "import * as os from 'os';\n"
  "globalThis.std = std;\n"
  "globalThis.os = os;\n";

/* A kept state, which make holds: its runtime and context, and the make functions it has defined by name; the context's opaque points back at it, so a one-shot call's context, with none, is told apart. */
struct js_state
{
  JSRuntime *rt;
  JSContext *ctx;
  JSValue funcs;
};

static struct js_state *
js_kept (JSContext *ctx)
{
  return JS_GetContextOpaque (ctx);
}

static JSValue
js_amk_has (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  (void) this_val;
  (void) argc;
  (void) argv;
  return JS_NewBool (ctx, amk_has_db ());
}

static JSValue
js_amk_expand (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *text;
  char *s;
  JSValue r;
  (void) this_val;
  if (argc < 1 || (text = JS_ToCString (ctx, argv[0])) == NULL)
    return JS_EXCEPTION;
  s = gmk_expand (text);
  r = JS_NewString (ctx, s ? s : "");
  gmk_free (s);
  JS_FreeCString (ctx, text);
  return r;
}

/* The raw call: the kind, the name, then each value as one whole argument; the prelude has already made every argument a string. */
static JSValue
js_amk_call (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *err = NULL, **vals;
  char *s;
  JSValue r;
  int i, n = argc - 2, kind = 0;
  (void) this_val;
  if (argc < 2 || JS_ToInt32 (ctx, &kind, argv[0]) < 0)
    return JS_ThrowTypeError (ctx, "amk.call: a kind and a name are required");
  vals = calloc ((size_t) argc + 1, sizeof *vals);
  for (i = 1; i < argc; i++)
    if ((vals[i] = JS_ToCString (ctx, argv[i])) == NULL)
      break;
  s = i == argc ? amk_call_kind (kind, vals[1], (unsigned int) n, vals + 2, &err) : NULL;
  r = s != NULL ? JS_NewString (ctx, s) : i == argc ? JS_ThrowTypeError (ctx, "amk.call: %s", err) : JS_EXCEPTION;
  gmk_free (s);
  while (i-- > 1)
    JS_FreeCString (ctx, vals[i]);
  free (vals);
  return r;
}

/* The raw deferred call: the kind, the name and the values as for call, answered with the pid and the fd the prelude waits on. */
static JSValue
js_amk_call_begin (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char **vals;
  JSValue r;
  int i, n = argc - 2, fd = -1, kind = 0;
  pid_t pid = -1;
  (void) this_val;
  if (argc < 2 || JS_ToInt32 (ctx, &kind, argv[0]) < 0)
    return JS_ThrowTypeError (ctx, "amk.acall: a kind and a name are required");
  vals = calloc ((size_t) argc + 1, sizeof *vals);
  for (i = 1; i < argc; i++)
    if ((vals[i] = JS_ToCString (ctx, argv[i])) == NULL)
      break;
  if (i == argc)
    pid = amk_call_begin (kind, vals[1], (unsigned int) n, vals + 2, &fd);
  while (i-- > 1)
    JS_FreeCString (ctx, vals[i]);
  free (vals);
  if (pid < 0)
    return JS_ThrowTypeError (ctx, "amk.acall: fork failed");
  r = JS_NewObject (ctx);
  JS_SetPropertyStr (ctx, r, "pid", JS_NewInt64 (ctx, pid));
  JS_SetPropertyStr (ctx, r, "fd", JS_NewInt32 (ctx, fd));
  return r;
}

/* The raw collect: the text of the call with that pid, or its error thrown. */
static JSValue
js_amk_call_end (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *err = NULL;
  char *s;
  JSValue r;
  int64_t pid;
  (void) this_val;
  if (argc < 1 || JS_ToInt64 (ctx, &pid, argv[0]) < 0)
    return JS_ThrowTypeError (ctx, "amk.acall: a pid is required");
  if (amk_call_end ((pid_t) pid, &s, &err) < 0)
    return JS_ThrowTypeError (ctx, "amk.acall: %s", err);
  r = JS_NewString (ctx, s);
  free (s);
  return r;
}

static JSValue
js_amk_eval (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *text;
  (void) this_val;
  if (argc < 1 || (text = JS_ToCString (ctx, argv[0])) == NULL)
    return JS_EXCEPTION;
  amk_eval (text);
  JS_FreeCString (ctx, text);
  return JS_UNDEFINED;
}

static JSValue
js_amk_get (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *name;
  char *s;
  JSValue r;
  (void) this_val;
  if (argc < 1 || (name = JS_ToCString (ctx, argv[0])) == NULL)
    return JS_EXCEPTION;
  s = amk_var_get (name);
  JS_FreeCString (ctx, name);
  if (s == NULL)
    return JS_UNDEFINED;
  r = JS_NewString (ctx, s);
  gmk_free (s);
  return r;
}

static JSValue
js_amk_set (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *name, *value;
  (void) this_val;
  if (argc < 2 || (name = JS_ToCString (ctx, argv[0])) == NULL)
    return JS_EXCEPTION;
  value = JS_ToCString (ctx, argv[1]);
  if (value == NULL)
    {
      JS_FreeCString (ctx, name);
      return JS_EXCEPTION;
    }
  amk_var_set (name, value);
  JS_FreeCString (ctx, value);
  JS_FreeCString (ctx, name);
  return JS_UNDEFINED;
}

static JSValue
js_amk_raw_get (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *name;
  char *s;
  JSValue r;
  (void) this_val;
  if (argc < 1 || (name = JS_ToCString (ctx, argv[0])) == NULL)
    return JS_EXCEPTION;
  s = amk_var_raw_get (name);
  JS_FreeCString (ctx, name);
  if (s == NULL)
    return JS_UNDEFINED;
  r = JS_NewString (ctx, s);
  gmk_free (s);
  return r;
}

static JSValue
js_amk_raw_set (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *name, *value;
  (void) this_val;
  if (argc < 2 || (name = JS_ToCString (ctx, argv[0])) == NULL)
    return JS_EXCEPTION;
  value = JS_ToCString (ctx, argv[1]);
  if (value == NULL)
    {
      JS_FreeCString (ctx, name);
      return JS_EXCEPTION;
    }
  amk_var_raw_set (name, value);
  JS_FreeCString (ctx, value);
  JS_FreeCString (ctx, name);
  return JS_UNDEFINED;
}

/* The engine polls this on its own instruction count, and a true answer throws an error no catch inside the run can stop. */
static int
js_deadline_interrupt (JSRuntime *rt, void *opaque)
{
  (void) rt;
  (void) opaque;
  return amk_deadline_expired ();
}

/* fn called under the interrupt handler, which stays installed after only while a deadline is still in force. */
static JSValue
js_call_bounded (JSContext *ctx, JSValueConst fn, int argc, JSValueConst *argv)
{
  JSRuntime *rt = JS_GetRuntime (ctx);
  JSValue r;
  JS_SetInterruptHandler (rt, js_deadline_interrupt, NULL);
  r = JS_Call (ctx, fn, JS_UNDEFINED, argc, argv);
  JS_SetInterruptHandler (rt, amk_deadline_active () ? js_deadline_interrupt : NULL, NULL);
  return r;
}

/* make's call into a defined function, in the state that defined it: the arguments as strings, the result as text, and an error raised to whoever made the call. */
static char *
js_func_call (void *state, const char *nm, unsigned int argc, char **argv)
{
  struct js_state *s = state;
  JSContext *ctx = s->ctx;
  JSValue fn, *args, result;
  const char *text;
  char *out = NULL;
  unsigned int i;

  fn = JS_GetPropertyStr (ctx, s->funcs, nm);
  if (!JS_IsFunction (ctx, fn))
    {
      JS_FreeValue (ctx, fn);
      return NULL;
    }
  args = malloc ((argc ? argc : 1) * sizeof *args);
  for (i = 0; i < argc; i++)
    args[i] = JS_NewString (ctx, argv[i]);
  result = amk_deadline_active () ? js_call_bounded (ctx, fn, (int) argc, args) : JS_Call (ctx, fn, JS_UNDEFINED, (int) argc, args);
  for (i = 0; i < argc; i++)
    JS_FreeValue (ctx, args[i]);
  free (args);
  JS_FreeValue (ctx, fn);
  if (JS_IsException (result) && amk_deadline_expired ())
    {
      JS_FreeValue (ctx, JS_GetException (ctx));
      return NULL;
    }
  if (JS_IsException (result))
    {
      JSValue e = JS_GetException (ctx);
      const char *msg = JS_ToCString (ctx, e);
      amk_func_raise ("js", nm, msg);
      if (msg != NULL)
        JS_FreeCString (ctx, msg);
      JS_FreeValue (ctx, e);
      return NULL;
    }
  if (JS_IsUndefined (result) || JS_IsNull (result))
    text = NULL;
  else
    text = JS_ToCString (ctx, result);
  out = gmk_alloc ((unsigned int) (text ? strlen (text) : 0) + 1);
  strcpy (out, text ? text : "");
  if (text != NULL)
    JS_FreeCString (ctx, text);
  JS_FreeValue (ctx, result);
  return out;
}

/* The function becomes make's function of that name, or replaces the one this state defined before; a name make has from elsewhere is an error. */
static JSValue
js_define_func (JSContext *ctx, const char *name, JSValueConst fn)
{
  struct js_state *s = js_kept (ctx);
  if (amk_func_add (name, s, js_func_call) < 0)
    return JS_ThrowTypeError (ctx, "amk.func: %s is a make function already", name);
  JS_SetPropertyStr (ctx, s->funcs, name, JS_DupValue (ctx, fn));
  return JS_UNDEFINED;
}

static JSValue
js_amk_func (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *name;
  JSValue r;
  (void) this_val;
  if (js_kept (ctx) == NULL)
    return JS_ThrowTypeError (ctx, "amk.func: only from js.exec, since a one-shot call's state ends with the call");
  if (argc < 2 || !JS_IsFunction (ctx, argv[1]))
    return JS_ThrowTypeError (ctx, "amk.func: fn must be a function");
  if ((name = JS_ToCString (ctx, argv[0])) == NULL)
    return JS_EXCEPTION;
  r = js_define_func (ctx, name, argv[1]);
  JS_FreeCString (ctx, name);
  return r;
}

/* A bare module name, with no leading slash or dot and not a builtin, is a package under lib/js/: its init.js, else the file of that name; a relative name resolves against the importing module as quickjs's default does. */
static char *
js_module_normalize (JSContext *ctx, const char *base, const char *name, void *opaque)
{
  char path[512];
  char *out;
  const char *r, *slash;
  size_t len;
  (void) opaque;
  if (name[0] == '/' || strcmp (name, "std") == 0 || strcmp (name, "os") == 0)
    return js_strdup (ctx, name);
  if (name[0] != '.')
    {
      snprintf (path, sizeof path, "/zip/lib/js/%s/init.js", name);
      if (access (path, R_OK) != 0)
        snprintf (path, sizeof path, "/zip/lib/js/%s.js", name);
      return js_strdup (ctx, access (path, R_OK) == 0 ? path : name);
    }
  slash = strrchr (base, '/');
  len = slash != NULL ? (size_t) (slash - base) : 0;
  out = js_malloc (ctx, len + strlen (name) + 2);
  if (out == NULL)
    return NULL;
  memcpy (out, base, len);
  out[len] = '\0';
  for (r = name;;)
    {
      if (r[0] == '.' && r[1] == '/')
        r += 2;
      else if (r[0] == '.' && r[1] == '.' && r[2] == '/' && out[0] != '\0')
        {
          char *p = strrchr (out, '/');
          *(p != NULL ? p : out) = '\0';
          r += 3;
        }
      else
        break;
    }
  if (out[0] != '\0')
    strcat (out, "/");
  strcat (out, r);
  return out;
}

/* __amk.resolves(name): whether the cascade answers for the name, so a missing amk field may stand for it. */
static JSValue
js_amk_resolves (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *name = argc > 0 ? JS_ToCString (ctx, argv[0]) : NULL, *err;
  char full[512];
  JSValue r;
  (void) this_val;
  if (name == NULL)
    return JS_EXCEPTION;
  r = JS_NewBool (ctx, amk_resolve (name, full, sizeof full, &err) >= 0);
  JS_FreeCString (ctx, name);
  return r;
}

/* A payload module, the name's lib/ directory and its init.js, loaded and evaluated now and answered as its namespace, or as its default export when it has one; undefined when the payload has none. */
static JSValue
js_amk_module (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *name = JS_ToCString (ctx, argv[0]);
  char path[512];
  FILE *f;
  (void) this_val;
  (void) argc;
  if (name == NULL)
    return JS_EXCEPTION;
  snprintf (path, sizeof path, "/zip/lib/%s/init.js", name);
  JS_FreeCString (ctx, name);
  if ((f = fopen (path, "r")) == NULL)
    return JS_UNDEFINED;
  fclose (f);
  return js_std_await (ctx, JS_LoadModule (ctx, "", path));
}

/* amk.send(text): a line to the job's parent, from inside a spawned job. */
static JSValue
js_amk_send (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  size_t len;
  const char *s;
  int rc;
  (void) this_val;
  if (argc < 1 || (s = JS_ToCStringLen (ctx, &len, argv[0])) == NULL)
    return JS_EXCEPTION;
  rc = amk_mail_send (s, len);
  JS_FreeCString (ctx, s);
  return JS_NewBool (ctx, rc == 0);
}

/* The descriptors make's own wait watches, the child pipe and every pair a child asks on, for the prelude to hand the reactor. */
static JSValue
js_amk_ask_fds (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  int fds[2 * 64 + 8], n, i;
  JSValue r = JS_NewArray (ctx);
  (void) this_val;
  (void) argc;
  (void) argv;
  n = amk_ask_fds (fds, (int) (sizeof fds / sizeof fds[0]));
  for (i = 0; i < n; i++)
    JS_SetPropertyUint32 (ctx, r, (uint32_t) i, JS_NewInt32 (ctx, fds[i]));
  return r;
}

/* Every request already waiting answered and the child pipe drained, with no wait. */
static JSValue
js_amk_ask_serve (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  (void) ctx;
  (void) this_val;
  (void) argc;
  (void) argv;
  amk_ask_wait (0);
  return JS_UNDEFINED;
}

/* The raw ask: one request line to the owner, answered with the id to poll for; one that would park in the owner is thrown. */
static JSValue
js_amk_ask_begin (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *line;
  long id;
  (void) this_val;
  if (argc < 1 || (line = JS_ToCString (ctx, argv[0])) == NULL)
    return JS_ThrowTypeError (ctx, "amk.ask: a request is required");
  id = amk_ask_begin (line);
  JS_FreeCString (ctx, line);
  if (id < 0)
    return JS_ThrowTypeError (ctx, "amk.ask: " AMK_ASK_PARKED);
  return JS_NewInt64 (ctx, id);
}

/* The reply to an ask by its id once it is here, else undefined. */
static JSValue
js_amk_ask_poll (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  int64_t id;
  char *reply;
  JSValue r;
  (void) this_val;
  if (argc < 1 || JS_ToInt64 (ctx, &id, argv[0]) < 0)
    return JS_ThrowTypeError (ctx, "amk.ask: an id is required");
  reply = amk_ask_poll ((unsigned long) id);
  if (reply == NULL)
    return JS_UNDEFINED;
  r = JS_NewString (ctx, reply);
  free (reply);
  return r;
}

static JSValue
js_amk_live (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  int32_t pid;
  (void) this_val;
  if (argc < 1 || JS_ToInt32 (ctx, &pid, argv[0]) < 0)
    return JS_EXCEPTION;
  return JS_NewBool (ctx, amk_spawn_live ((pid_t) pid));
}

/* amk.deadline(ms, fn, ...args): fn's result, or the error "deadline: ms ms" once ms milliseconds pass, in this guest or in any other it calls, catchable again at this call; a nested deadline keeps the tighter one, and a promise fn returns is not bounded past its return. */
static JSValue
js_amk_deadline (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  struct amk_deadline saved;
  int64_t ms;
  long hit;
  JSValue r;
  (void) this_val;

  if (argc < 2 || !JS_IsFunction (ctx, argv[1]))
    return JS_ThrowTypeError (ctx, "amk.deadline: needs ms and a function");
  if (JS_ToInt64 (ctx, &ms, argv[0]) < 0)
    return JS_EXCEPTION;
  if (ms < 0)
    return JS_ThrowRangeError (ctx, "amk.deadline: ms must not be negative");
  amk_deadline_push ((long) ms, &saved);
  r = js_call_bounded (ctx, argv[1], argc - 2, argv + 2);
  hit = amk_deadline_pop (&saved);
  if (JS_IsException (r) && hit >= 0)
    {
      JS_FreeValue (ctx, JS_GetException (ctx));
      return JS_ThrowInternalError (ctx, "deadline: %d ms", (int) hit);
    }
  return r;
}

/* The raw calls under a private global, which the prelude wraps and removes. */
static void
js_bind_amk (JSContext *ctx)
{
  JSValue g = JS_GetGlobalObject (ctx);
  JSValue raw = JS_NewObject (ctx);
  JS_SetPropertyStr (ctx, raw, "has", JS_NewCFunction (ctx, js_amk_has, "has", 0));
  JS_SetPropertyStr (ctx, raw, "expand", JS_NewCFunction (ctx, js_amk_expand, "expand", 1));
  JS_SetPropertyStr (ctx, raw, "eval", JS_NewCFunction (ctx, js_amk_eval, "eval", 1));
  JS_SetPropertyStr (ctx, raw, "call", JS_NewCFunction (ctx, js_amk_call, "call", 2));
  JS_SetPropertyStr (ctx, raw, "resolves", JS_NewCFunction (ctx, js_amk_resolves, "resolves", 1));
  JS_SetPropertyStr (ctx, raw, "callBegin", JS_NewCFunction (ctx, js_amk_call_begin, "callBegin", 2));
  JS_SetPropertyStr (ctx, raw, "callEnd", JS_NewCFunction (ctx, js_amk_call_end, "callEnd", 1));
  JS_SetPropertyStr (ctx, raw, "get", JS_NewCFunction (ctx, js_amk_get, "get", 1));
  JS_SetPropertyStr (ctx, raw, "set", JS_NewCFunction (ctx, js_amk_set, "set", 2));
  JS_SetPropertyStr (ctx, raw, "rawGet", JS_NewCFunction (ctx, js_amk_raw_get, "rawGet", 1));
  JS_SetPropertyStr (ctx, raw, "rawSet", JS_NewCFunction (ctx, js_amk_raw_set, "rawSet", 2));
  JS_SetPropertyStr (ctx, raw, "func", JS_NewCFunction (ctx, js_amk_func, "func", 2));
  JS_SetPropertyStr (ctx, raw, "module", JS_NewCFunction (ctx, js_amk_module, "module", 1));
  JS_SetPropertyStr (ctx, raw, "send", JS_NewCFunction (ctx, js_amk_send, "send", 1));
  JS_SetPropertyStr (ctx, raw, "deadline", JS_NewCFunction (ctx, js_amk_deadline, "deadline", 2));
  JS_SetPropertyStr (ctx, raw, "askFds", JS_NewCFunction (ctx, js_amk_ask_fds, "askFds", 0));
  JS_SetPropertyStr (ctx, raw, "askServe", JS_NewCFunction (ctx, js_amk_ask_serve, "askServe", 0));
  JS_SetPropertyStr (ctx, raw, "askBegin", JS_NewCFunction (ctx, js_amk_ask_begin, "askBegin", 1));
  JS_SetPropertyStr (ctx, raw, "askPoll", JS_NewCFunction (ctx, js_amk_ask_poll, "askPoll", 1));
  JS_SetPropertyStr (ctx, raw, "live", JS_NewCFunction (ctx, js_amk_live, "live", 1));
  JS_SetPropertyStr (ctx, g, "__amk", raw);
  JS_FreeValue (ctx, g);
}

/* amk over the raw calls: expand, eval, func, the var proxy that reads, assigns, and answers in, the hook table, the call's input, ask, whose promise the tagged reply settles, and exited, whose reactor handlers answer children's requests and exist only while a pid is awaited or an acall or an ask is pending; every call refuses under the engine flag, where make has parsed nothing; a name amk lacks loads the payload module of that name once, else stands for what the cascade resolves it to. */
static const char *js_amk_prelude =
  "globalThis.amk = new Proxy((function (raw) {\n"
  "  const need = () => { if (!raw.has()) throw new Error('amk: no make database, running outside a makefile'); };\n"
  "  const text = (v) => v == null ? '' : String(v);\n"
  "  const unexpanded = new Proxy({}, {\n"
  "    get: (_, k) => { need(); return raw.rawGet(String(k)); },\n"
  "    set: (_, k, v) => { need(); raw.rawSet(String(k), text(v)); return true; },\n"
  "    has: (_, k) => { need(); return raw.rawGet(String(k)) !== undefined; },\n"
  "  });\n"
  "  const waiting = new Map(), watched = new Set(), calls = new Set(), asks = new Map();\n"
  "  const settle = () => {\n"
  "    for (const [pid, oks] of waiting) {\n"
  "      const t = raw.call(0, 'amk.wait', String(pid), '0'), r = t ? JSON.parse(t) : undefined;\n"
  "      if (r && r.status !== 'stopped') { waiting.delete(pid); oks.forEach((ok) => ok(r)); }\n"
  "    }\n"
  "  };\n"
  "  const answer = (reply, ok, no) => {\n"
  "    const nl = reply.indexOf('\\n'), st = reply.slice(0, nl).split(' ')[0], body = reply.slice(nl + 1);\n"
  "    if (st === '0') ok(body);\n"
  "    else no(new Error(st === '3' ? 'amk.ask: the owner exited' : body.trim() || 'amk.ask: status ' + st));\n"
  "  };\n"
  "  const settleAsks = () => {\n"
  "    for (const [id, [ok, no]] of asks) {\n"
  "      const r = raw.askPoll(id);\n"
  "      if (r !== undefined) { asks.delete(id); answer(r, ok, no); }\n"
  "    }\n"
  "  };\n"
  "  const watch = () => {\n"
  "    const now = new Set(waiting.size || calls.size || asks.size ? raw.askFds() : []);\n"
  "    for (const fd of watched) if (!now.has(fd)) { os.setReadHandler(fd, null); watched.delete(fd); }\n"
  "    for (const fd of now) if (!watched.has(fd)) { os.setReadHandler(fd, pump); watched.add(fd); }\n"
  "  };\n"
  "  const pump = () => { raw.askServe(); settle(); settleAsks(); watch(); };\n"
  "  const begin = (kind, name, vals) => { need(); const h = raw.callBegin(kind, String(name), ...vals.map(text));\n"
  "    calls.add(h.pid); watch();\n"
  "    return new Promise((ok, no) => os.setReadHandler(h.fd, () => {\n"
  "      os.setReadHandler(h.fd, null); calls.delete(h.pid);\n"
  "      try { ok(raw.callEnd(h.pid)); } catch (e) { no(e); } finally { watch(); }\n"
  "    })); };\n"
  "  return {\n"
  "    expand: (t) => { need(); return raw.expand(String(t)); },\n"
  "    eval: (t) => { need(); raw.eval(String(t)); },\n"
  "    call: (name, ...vals) => { need(); const r = raw.call(0, String(name), ...vals.map(text)); if (asks.size) { settleAsks(); watch(); } return r; },\n"
  "    fxn: (name, ...vals) => { need(); return raw.call(1, String(name), ...vals.map(text)); },\n"
  "    macro: (name, ...vals) => { need(); return raw.call(2, String(name), ...vals.map(text)); },\n"
  "    ask: (op, ns, ...vals) => { need(); let id;\n"
  "      try { id = raw.askBegin([op, ns, ...vals].map(text).join(' ')); } catch (e) { return Promise.reject(e); }\n"
  "      return new Promise((ok, no) => { asks.set(id, [ok, no]); settleAsks(); watch(); }); },\n"
  "    acall: (name, ...vals) => begin(0, name, vals),\n"
  "    afxn: (name, ...vals) => begin(1, name, vals),\n"
  "    amacro: (name, ...vals) => begin(2, name, vals),\n"
  "    agoal: (name) => begin(0, 'amk.goal', [name]),\n"
  "    func: (name, fn) => { need(); raw.func(String(name), fn); },\n"
  "    var: new Proxy({}, {\n"
  "      get: (_, k) => { if (k === 'raw') return unexpanded; need(); return raw.get(String(k)); },\n"
  "      set: (_, k, v) => { need(); raw.set(String(k), text(v)); return true; },\n"
  "      has: (_, k) => { need(); return raw.get(String(k)) !== undefined; },\n"
  "    }),\n"
  "    on: {},\n"
  "    send: raw.send, deadline: raw.deadline,\n"
  "    exited: (pid) => new Promise((ok, no) => {\n"
  "      if (!raw.live(pid)) return no(new Error(`amk.exited: ${pid} is not a live job of this process`));\n"
  "      waiting.set(pid, (waiting.get(pid) || []).concat(ok));\n"
  "      pump();\n"
  "    }),\n"
  "  };\n"
  "})(globalThis.__amk), {\n"
  "  get: ((module, resolves) => {\n"
  "    const fn = (name) => new Proxy((...vals) => globalThis.amk.call(name, ...vals), {\n"
  "      get: (f, k, r) => typeof k === 'string' && !(k in f) ? fn(name + '.' + k) : Reflect.get(f, k, r),\n"
  "    });\n"
  "    return (t, k, r) => {\n"
  "      if (typeof k !== 'string' || k in t) return Reflect.get(t, k, r);\n"
  "      const ns = module(k), m = ns !== undefined && 'default' in ns ? ns.default : ns;\n"
  "      if (m !== undefined) { t[k] = m; return m; }\n"
  "      if (resolves(k)) { t[k] = fn(k); return t[k]; }\n"
  "      return undefined;\n"
  "    };\n"
  "  })(globalThis.__amk.module, globalThis.__amk.resolves),\n"
  "});\n"
  "delete globalThis.__amk;\n";

static JSValue
js_noop (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  (void) ctx;
  (void) this_val;
  (void) argc;
  (void) argv;
  return JS_UNDEFINED;
}

/* A chunk's promise is awaited here and its rejection reported here, so it gets a handler first: otherwise the std library counts it unhandled and exits the process, which in the persistent case is make. */
static JSValue
js_handled (JSContext *ctx, JSValue promise)
{
  if (JS_IsObject (promise))
    {
      JSValue catcher = JS_GetPropertyStr (ctx, promise, "catch");
      if (JS_IsFunction (ctx, catcher))
        {
          JSValue noop = JS_NewCFunction (ctx, js_noop, "noop", 1);
          JS_FreeValue (ctx, JS_Call (ctx, catcher, promise, 1, &noop));
          JS_FreeValue (ctx, noop);
        }
      JS_FreeValue (ctx, catcher);
    }
  return promise;
}

static int
js_guest_eval (JSContext *ctx, const char *src, const char *name, int flags)
{
  JSValue val;
  int rc = 0;

  if ((flags & JS_EVAL_TYPE_MASK) == JS_EVAL_TYPE_MODULE)
    {
      val = JS_Eval (ctx, src, strlen (src), name, flags | JS_EVAL_FLAG_COMPILE_ONLY);
      if (!JS_IsException (val))
        {
          js_module_set_import_meta (ctx, val, 1, 1);
          val = JS_EvalFunction (ctx, val);
        }
      val = js_std_await (ctx, js_handled (ctx, val));
    }
  else
    val = js_std_await (ctx, js_handled (ctx, JS_Eval (ctx, src, strlen (src), name, flags | JS_EVAL_FLAG_ASYNC)));

  if (JS_IsException (val))
    {
      js_std_dump_error (ctx);
      rc = 1;
    }
  JS_FreeValue (ctx, val);
  return rc;
}

/* A runtime and context with the std library, the preludes, and the handle bound; 0 when it is up. */
static int
js_state_open (JSRuntime **rt, JSContext **ctx, int argc, char **argv)
{
  int rc;

  *rt = JS_NewRuntime ();
  if (*rt == NULL)
    {
      fprintf (stderr, "js: cannot create runtime\n");
      return 1;
    }
  js_std_init_handlers (*rt);
  *ctx = JS_NewContext (*rt);
  if (*ctx == NULL)
    {
      fprintf (stderr, "js: cannot create context\n");
      JS_FreeRuntime (*rt);
      *rt = NULL;
      return 1;
    }
  js_init_module_std (*ctx, "std");
  js_init_module_os (*ctx, "os");
  JS_SetModuleLoaderFunc2 (*rt, js_module_normalize, js_module_loader, js_module_check_attributes, NULL);
  JS_SetHostPromiseRejectionTracker (*rt, js_std_promise_rejection_tracker, NULL);
  js_std_add_helpers (*ctx, argc, argv);
  js_bind_amk (*ctx);

  rc = js_guest_eval (*ctx, js_guest_prelude, "<prelude>", JS_EVAL_TYPE_MODULE);
  if (rc == 0)
    rc = js_guest_eval (*ctx, js_amk_prelude, "<amk>", JS_EVAL_TYPE_GLOBAL);
  return rc;
}

static void
js_state_close (JSRuntime *rt, JSContext *ctx)
{
  js_std_free_handlers (rt);
  JS_FreeContext (ctx);
  JS_FreeRuntime (rt);
}

/* A chunk as the one-shot entry runs it: a module when it looks like one, otherwise a script that may await at top level, with pending jobs run after. */
static int
js_run_chunk (JSContext *ctx, const char *src, int force_global)
{
  int flags = !force_global && JS_DetectModule (src, strlen (src)) ? JS_EVAL_TYPE_MODULE : JS_EVAL_TYPE_GLOBAL;
  int rc = js_guest_eval (ctx, src, "<chunk>", flags);
  if (rc == 0)
    js_std_loop (ctx);
  return rc;
}

/* argv[1] is JavaScript source text rather than a command line; whatever it prints is the result. */
__attribute__ ((visibility ("default"))) int
js_run_main (int argc, char **argv)
{
  JSRuntime *rt;
  JSContext *ctx;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "js: no chunk\n");
      return 2;
    }
  if (js_state_open (&rt, &ctx, argc - 1, argv + 1) != 0)
    return 1;
  rc = js_run_chunk (ctx, argv[1], 0);
  js_state_close (rt, ctx);
  fflush (stdout);
  return rc;
}

/* The amk object on the global, for the caller to read a property of and free. */
static JSValue
js_amk_object (JSContext *ctx)
{
  JSValue g = JS_GetGlobalObject (ctx);
  JSValue amk = JS_GetPropertyStr (ctx, g, "amk");
  JS_FreeValue (ctx, g);
  return amk;
}

static int
js_key_cmp (const void *a, const void *b)
{
  return strcmp (*(char *const *) a, *(char *const *) b);
}

/* The string keys of an object, own and enumerable, sorted; the caller frees the array and each string. */
static char **
js_sorted_keys (JSContext *ctx, JSValueConst obj, size_t *count)
{
  JSPropertyEnum *tab = NULL;
  uint32_t n = 0, i;
  char **keys;

  if (JS_GetOwnPropertyNames (ctx, &tab, &n, obj, JS_GPN_STRING_MASK | JS_GPN_ENUM_ONLY) < 0)
    {
      *count = 0;
      return NULL;
    }
  keys = malloc ((n ? n : 1) * sizeof *keys);
  for (i = 0; i < n; i++)
    {
      const char *s = JS_AtomToCString (ctx, tab[i].atom);
      keys[i] = strdup (s ? s : "");
      JS_FreeCString (ctx, s);
    }
  JS_FreePropertyEnum (ctx, tab, n);
  qsort (keys, n, sizeof *keys, js_key_cmp);
  *count = n;
  return keys;
}

static void
js_free_keys (char **keys, size_t n)
{
  size_t i;
  for (i = 0; i < n; i++)
    free (keys[i]);
  free (keys);
}

struct js_names
{
  char *s;
  size_t n, cap;
};

static void
js_names_add (struct js_names *names, const char *name)
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

static JSValue js_export_value (JSContext *ctx, const char *name, JSValueConst value, struct js_names *names);

/* An object as fields: one variable per key as name.key, in key order, recursing. */
static JSValue
js_export_fields (JSContext *ctx, const char *name, JSValueConst obj, struct js_names *names)
{
  size_t n, i;
  char **keys = js_sorted_keys (ctx, obj, &n);
  JSValue r = JS_UNDEFINED;
  for (i = 0; i < n && !JS_IsException (r); i++)
    {
      JSValue v;
      char *child;
      if (!amk_name_ok (keys[i]))
        {
          r = JS_ThrowTypeError (ctx, "amk import: %s has a key make cannot spell: %s", name, keys[i]);
          break;
        }
      child = malloc (strlen (name) + strlen (keys[i]) + 2);
      sprintf (child, "%s.%s", name, keys[i]);
      v = JS_GetPropertyStr (ctx, obj, keys[i]);
      r = js_export_value (ctx, child, v, names);
      JS_FreeValue (ctx, v);
      free (child);
    }
  js_free_keys (keys, n);
  return r;
}

/* One global into make: a function as a make function, an array as words, an object as fields, a boolean as true or nothing, and a string or number as its text; null and undefined are skipped. */
static JSValue
js_export_value (JSContext *ctx, const char *name, JSValueConst value, struct js_names *names)
{
  if (JS_IsUndefined (value) || JS_IsNull (value))
    return JS_UNDEFINED;
  if (JS_IsFunction (ctx, value))
    {
      JSValue r = js_define_func (ctx, name, value);
      if (JS_IsException (r))
        return r;
    }
  else if (JS_IsBool (value))
    amk_var_set (name, JS_ToBool (ctx, value) ? "true" : "");
  else if (JS_IsArray (ctx, value))
    {
      JSValue len = JS_GetPropertyStr (ctx, value, "length");
      uint32_t n = 0, i;
      struct js_names words = { NULL, 0, 0 };
      JS_ToUint32 (ctx, &n, len);
      JS_FreeValue (ctx, len);
      for (i = 0; i < n; i++)
        {
          JSValue item = JS_GetPropertyUint32 (ctx, value, i);
          const char *s = JS_ToCString (ctx, item);
          js_names_add (&words, s ? s : "");
          JS_FreeCString (ctx, s);
          JS_FreeValue (ctx, item);
        }
      amk_var_set (name, words.s ? words.s : "");
      free (words.s);
    }
  else if (JS_IsObject (value))
    return js_export_fields (ctx, name, value, names);
  else
    {
      const char *s = JS_ToCString (ctx, value);
      if (s == NULL)
        return JS_EXCEPTION;
      amk_var_set (name, s);
      JS_FreeCString (ctx, s);
    }
  js_names_add (names, name);
  return JS_UNDEFINED;
}

/* The globals as they were before an export chunk, copied so what the chunk added or rebound can be told apart afterwards. */
static JSValue
js_snapshot_globals (JSContext *ctx)
{
  JSValue g = JS_GetGlobalObject (ctx);
  JSValue before = JS_NewObject (ctx);
  size_t n, i;
  char **keys = js_sorted_keys (ctx, g, &n);
  for (i = 0; i < n; i++)
    JS_SetPropertyStr (ctx, before, keys[i], JS_GetPropertyStr (ctx, g, keys[i]));
  js_free_keys (keys, n);
  JS_FreeValue (ctx, g);
  return before;
}

/* Every global that is new or rebound since the snapshot, exported in name order, and the names to the sink. */
static int
js_export_globals (JSContext *ctx, JSValueConst before, struct amk_sink *out)
{
  JSValue g = JS_GetGlobalObject (ctx);
  size_t n, i;
  char **keys = js_sorted_keys (ctx, g, &n);
  struct js_names names = { NULL, 0, 0 };
  int rc = 0;

  for (i = 0; i < n && rc == 0; i++)
    {
      JSValue now, was;
      if (!amk_name_ok (keys[i]))
        continue;
      now = JS_GetPropertyStr (ctx, g, keys[i]);
      was = JS_GetPropertyStr (ctx, before, keys[i]);
      if (JS_IsUndefined (was) || !JS_StrictEq (ctx, now, was))
        {
          JSValue r = js_export_value (ctx, keys[i], now, &names);
          if (JS_IsException (r))
            {
              fprintf (stderr, "js.import: ");
              js_std_dump_error (ctx);
              rc = 1;
            }
        }
      JS_FreeValue (ctx, now);
      JS_FreeValue (ctx, was);
    }
  js_free_keys (keys, n);
  JS_FreeValue (ctx, g);
  if (names.n > 0)
    out->write (out, names.s, names.n);
  out->write (out, "\n", 1);
  free (names.s);
  return rc;
}

/* The create member: a kept state, which make holds for the life of the process, with the handle bound and its own table of make functions. */
__attribute__ ((visibility ("default"))) void *
js_create (void)
{
  struct js_state *s = calloc (1, sizeof *s);
  if (s == NULL)
    return NULL;
  if (js_state_open (&s->rt, &s->ctx, 0, NULL) != 0)
    {
      fprintf (stderr, "js: cannot create state\n");
      free (s);
      return NULL;
    }
  s->funcs = JS_NewObject (s->ctx);
  JS_SetContextOpaque (s->ctx, s);
  return s;
}

/* exec runs the chunk in the state with what it prints to the sink; import runs it with print on stderr, then hands make what it left on the global object and the sink their names. */
static int
js_run_op (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  struct js_state *s = state;
  struct amk_capture capture;
  int export = strcmp (op, "import") == 0;
  JSContext *ctx = s->ctx;
  JSValue before;
  int rc;

  if (prog == NULL)
    {
      fprintf (stderr, "js.%s: no chunk\n", op);
      return 2;
    }

  if (!export)
    {
      amk_capture_begin_to (&capture, out);
      rc = js_run_chunk (ctx, prog, 0);
      amk_capture_end (&capture, out);
      return rc;
    }

  before = js_snapshot_globals (ctx);
  amk_capture_begin (&capture);
  rc = js_run_chunk (ctx, prog, 1);
  amk_capture_end (&capture, &amk_sink_stderr);
  if (rc == 0)
    rc = js_export_globals (ctx, before, out);
  JS_FreeValue (ctx, before);
  return rc;
}

__attribute__ ((visibility ("default"))) int
js_exec (void *state, struct amk_sink *out, const char *prog)
{
  return js_run_op (state, out, "exec", prog);
}

__attribute__ ((visibility ("default"))) int
js_import (void *state, struct amk_sink *out, const char *prog)
{
  return js_run_op (state, out, "import", prog);
}

/* The hook primitive: amk.on[event], when the state holds a function there, is called with the event as an object. Its print goes to stderr, and an error reports there and is otherwise ignored. */
__attribute__ ((visibility ("default"))) void
js_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  JSContext *ctx = ((struct js_state *) state)->ctx;
  struct amk_capture capture;
  JSValue amk, on, fn, e, r;

  amk = js_amk_object (ctx);
  on = JS_GetPropertyStr (ctx, amk, "on");
  JS_FreeValue (ctx, amk);
  fn = JS_IsObject (on) ? JS_GetPropertyStr (ctx, on, event) : JS_UNDEFINED;
  JS_FreeValue (ctx, on);
  if (!JS_IsFunction (ctx, fn))
    {
      JS_FreeValue (ctx, fn);
      return;
    }

  e = JS_NewObject (ctx);
  JS_SetPropertyStr (ctx, e, "event", JS_NewString (ctx, event));
  JS_SetPropertyStr (ctx, e, "target", JS_NewString (ctx, target));
  JS_SetPropertyStr (ctx, e, "status", JS_NewString (ctx, status));
  JS_SetPropertyStr (ctx, e, "code", JS_NewInt32 (ctx, exit_code));
  JS_SetPropertyStr (ctx, e, "signal", JS_NewInt32 (ctx, exit_sig));
  JS_SetPropertyStr (ctx, e, "pid", JS_NewInt64 (ctx, pid));

  amk_capture_begin (&capture);
  r = JS_Call (ctx, fn, JS_UNDEFINED, 1, &e);
  if (JS_IsException (r))
    {
      fprintf (stderr, "js hook %s: ", event);
      js_std_dump_error (ctx);
    }
  amk_capture_end (&capture, &amk_sink_stderr);
  JS_FreeValue (ctx, r);
  JS_FreeValue (ctx, e);
  JS_FreeValue (ctx, fn);
}
