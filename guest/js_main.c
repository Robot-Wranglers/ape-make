/* The quickjs guest's entry point: amk links the engine and its std library, not the qjs cli, so it supplies this. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

/* The raw call: the name, then each value as one whole argument; the prelude has already made every argument a string. */
static JSValue
js_amk_call (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char *err = NULL, **vals;
  char *s;
  JSValue r;
  int i, n = argc - 1;
  (void) this_val;
  if (argc < 1)
    return JS_ThrowTypeError (ctx, "amk.call: a name is required");
  vals = calloc ((size_t) argc + 1, sizeof *vals);
  for (i = 0; i < argc; i++)
    if ((vals[i] = JS_ToCString (ctx, argv[i])) == NULL)
      break;
  s = i == argc ? amk_call (vals[0], (unsigned int) n, vals + 1, &err) : NULL;
  r = s != NULL ? JS_NewString (ctx, s) : i == argc ? JS_ThrowTypeError (ctx, "amk.call: %s", err) : JS_EXCEPTION;
  gmk_free (s);
  while (i-- > 0)
    JS_FreeCString (ctx, vals[i]);
  free (vals);
  return r;
}

/* The raw deferred call: the name and the values as for call, answered with the pid and the fd the prelude waits on. */
static JSValue
js_amk_call_begin (JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
  const char **vals;
  JSValue r;
  int i, n = argc - 1, fd = -1;
  pid_t pid = -1;
  (void) this_val;
  if (argc < 1)
    return JS_ThrowTypeError (ctx, "amk.acall: a name is required");
  vals = calloc ((size_t) argc + 1, sizeof *vals);
  for (i = 0; i < argc; i++)
    if ((vals[i] = JS_ToCString (ctx, argv[i])) == NULL)
      break;
  if (i == argc)
    pid = amk_call_begin (vals[0], (unsigned int) n, vals + 1, &fd);
  while (i-- > 0)
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

/* make's call into a defined function, in the state that defined it: the arguments as strings, the result as text, and an error reported on stderr and answered empty. */
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
  result = JS_Call (ctx, fn, JS_UNDEFINED, (int) argc, args);
  for (i = 0; i < argc; i++)
    JS_FreeValue (ctx, args[i]);
  free (args);
  JS_FreeValue (ctx, fn);
  if (JS_IsException (result))
    {
      fprintf (stderr, "js $(%s ...): ", nm);
      js_std_dump_error (ctx);
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

/* The raw calls under a private global, which the prelude wraps and removes. */
static void
js_bind_amk (JSContext *ctx)
{
  JSValue g = JS_GetGlobalObject (ctx);
  JSValue raw = JS_NewObject (ctx);
  JS_SetPropertyStr (ctx, raw, "has", JS_NewCFunction (ctx, js_amk_has, "has", 0));
  JS_SetPropertyStr (ctx, raw, "expand", JS_NewCFunction (ctx, js_amk_expand, "expand", 1));
  JS_SetPropertyStr (ctx, raw, "eval", JS_NewCFunction (ctx, js_amk_eval, "eval", 1));
  JS_SetPropertyStr (ctx, raw, "call", JS_NewCFunction (ctx, js_amk_call, "call", 1));
  JS_SetPropertyStr (ctx, raw, "callBegin", JS_NewCFunction (ctx, js_amk_call_begin, "callBegin", 1));
  JS_SetPropertyStr (ctx, raw, "callEnd", JS_NewCFunction (ctx, js_amk_call_end, "callEnd", 1));
  JS_SetPropertyStr (ctx, raw, "get", JS_NewCFunction (ctx, js_amk_get, "get", 1));
  JS_SetPropertyStr (ctx, raw, "set", JS_NewCFunction (ctx, js_amk_set, "set", 2));
  JS_SetPropertyStr (ctx, raw, "func", JS_NewCFunction (ctx, js_amk_func, "func", 2));
  JS_SetPropertyStr (ctx, g, "__amk", raw);
  JS_FreeValue (ctx, g);
}

/* amk over the raw calls: expand, eval, func, the var proxy that reads, assigns, and answers in, the hook table, and the call's input; every call refuses under the engine flag, where make has parsed nothing. */
static const char *js_amk_prelude =
  "globalThis.amk = (function (raw) {\n"
  "  const need = () => { if (!raw.has()) throw new Error('amk: no make database, running outside a makefile'); };\n"
  "  const text = (v) => v == null ? '' : String(v);\n"
  "  return {\n"
  "    expand: (t) => { need(); return raw.expand(String(t)); },\n"
  "    eval: (t) => { need(); raw.eval(String(t)); },\n"
  "    call: (name, ...vals) => { need(); return raw.call(String(name), ...vals.map(text)); },\n"
  "    acall: (name, ...vals) => { need(); const h = raw.callBegin(String(name), ...vals.map(text));\n"
  "      return new Promise((ok, no) => os.setReadHandler(h.fd, () => {\n"
  "        os.setReadHandler(h.fd, null);\n"
  "        try { ok(raw.callEnd(h.pid)); } catch (e) { no(e); }\n"
  "      })); },\n"
  "    func: (name, fn) => { need(); raw.func(String(name), fn); },\n"
  "    var: new Proxy({}, {\n"
  "      get: (_, k) => { need(); return raw.get(String(k)); },\n"
  "      set: (_, k, v) => { need(); raw.set(String(k), text(v)); return true; },\n"
  "      has: (_, k) => { need(); return raw.get(String(k)) !== undefined; },\n"
  "    }),\n"
  "    on: {},\n"
  "  };\n"
  "})(globalThis.__amk);\n"
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
  JS_SetModuleLoaderFunc2 (*rt, NULL, js_module_loader, js_module_check_attributes, NULL);
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

/* The open primitive: a kept state, which make holds for the life of the process, with the handle bound and its own table of make functions. */
__attribute__ ((visibility ("default"))) void *
js_open (void)
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

/* The run primitive: exec runs the chunk in the state with what it prints to the sink; import runs it with print on stderr, then hands make what it left on the global object and the sink their names. */
__attribute__ ((visibility ("default"))) int
js_run (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  struct js_state *s = state;
  struct amk_capture capture;
  int export = strcmp (op, "import") == 0;
  JSContext *ctx = s->ctx;
  JSValue before;
  int rc;

  if (!export && strcmp (op, "exec") != 0)
    {
      fprintf (stderr, "js: unknown operation %s\n", op);
      return 2;
    }
  if (prog == NULL)
    {
      fprintf (stderr, "js.%s: no chunk\n", op);
      return 2;
    }

  if (!export)
    {
      amk_capture_begin (&capture);
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
