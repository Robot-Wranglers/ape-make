/* The quickjs guest's entry point: amk links the engine and its std library, not the qjs cli, so it supplies this. */

#include <stdio.h>
#include <string.h>

#include "quickjs.h"
#include "quickjs-libc.h"
#include "amk_guest.h"

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

/* The raw calls under a private global, which the prelude wraps and removes. */
static void
js_bind_amk (JSContext *ctx)
{
  JSValue g = JS_GetGlobalObject (ctx);
  JSValue raw = JS_NewObject (ctx);
  JS_SetPropertyStr (ctx, raw, "has", JS_NewCFunction (ctx, js_amk_has, "has", 0));
  JS_SetPropertyStr (ctx, raw, "expand", JS_NewCFunction (ctx, js_amk_expand, "expand", 1));
  JS_SetPropertyStr (ctx, raw, "eval", JS_NewCFunction (ctx, js_amk_eval, "eval", 1));
  JS_SetPropertyStr (ctx, raw, "get", JS_NewCFunction (ctx, js_amk_get, "get", 1));
  JS_SetPropertyStr (ctx, raw, "set", JS_NewCFunction (ctx, js_amk_set, "set", 2));
  JS_SetPropertyStr (ctx, g, "__amk", raw);
  JS_FreeValue (ctx, g);
}

/* amk over the raw calls: expand, eval, and a var proxy that reads, assigns, and answers in; every call refuses under the engine flag, where make has parsed nothing. */
static const char *js_amk_prelude =
  "globalThis.amk = (function (raw) {\n"
  "  const need = () => { if (!raw.has()) throw new Error('amk: no make database, running outside a makefile'); };\n"
  "  const text = (v) => v == null ? '' : String(v);\n"
  "  return {\n"
  "    expand: (t) => { need(); return raw.expand(String(t)); },\n"
  "    eval: (t) => { need(); raw.eval(String(t)); },\n"
  "    var: new Proxy({}, {\n"
  "      get: (_, k) => { need(); return raw.get(String(k)); },\n"
  "      set: (_, k, v) => { need(); raw.set(String(k), text(v)); return true; },\n"
  "      has: (_, k) => { need(); return raw.get(String(k)) !== undefined; },\n"
  "    }),\n"
  "  };\n"
  "})(globalThis.__amk);\n"
  "delete globalThis.__amk;\n";

/* The std and os modules are bound as globals the way qjs does it, so a plain chunk can use them without import. */
static const char *js_guest_prelude =
  "import * as std from 'std';\n"
  "import * as os from 'os';\n"
  "globalThis.std = std;\n"
  "globalThis.os = os;\n";

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
      val = js_std_await (ctx, val);
    }
  else
    val = js_std_await (ctx, JS_Eval (ctx, src, strlen (src), name, flags | JS_EVAL_FLAG_ASYNC));

  if (JS_IsException (val))
    {
      js_std_dump_error (ctx);
      rc = 1;
    }
  JS_FreeValue (ctx, val);
  return rc;
}

/* argv[1] is JavaScript source text rather than a command line, run as a module when it looks like one and otherwise as a script that may await at top level; whatever it prints is the result. */
__attribute__ ((visibility ("default"))) int
js_run_main (int argc, char **argv)
{
  JSRuntime *rt;
  JSContext *ctx;
  int flags, rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "js: no chunk\n");
      return 2;
    }

  rt = JS_NewRuntime ();
  if (rt == NULL)
    {
      fprintf (stderr, "js: cannot create runtime\n");
      return 1;
    }
  js_std_init_handlers (rt);
  ctx = JS_NewContext (rt);
  if (ctx == NULL)
    {
      fprintf (stderr, "js: cannot create context\n");
      JS_FreeRuntime (rt);
      return 1;
    }
  js_init_module_std (ctx, "std");
  js_init_module_os (ctx, "os");
  JS_SetModuleLoaderFunc2 (rt, NULL, js_module_loader, js_module_check_attributes, NULL);
  JS_SetHostPromiseRejectionTracker (rt, js_std_promise_rejection_tracker, NULL);
  js_std_add_helpers (ctx, argc - 1, argv + 1);
  js_bind_amk (ctx);

  rc = js_guest_eval (ctx, js_guest_prelude, "<prelude>", JS_EVAL_TYPE_MODULE);
  if (rc == 0)
    rc = js_guest_eval (ctx, js_amk_prelude, "<amk>", JS_EVAL_TYPE_GLOBAL);
  if (rc == 0)
    {
      flags = JS_DetectModule (argv[1], strlen (argv[1])) ? JS_EVAL_TYPE_MODULE : JS_EVAL_TYPE_GLOBAL;
      rc = js_guest_eval (ctx, argv[1], "<chunk>", flags);
    }
  if (rc == 0)
    js_std_loop (ctx);

  js_std_free_handlers (rt);
  JS_FreeContext (ctx);
  JS_FreeRuntime (rt);
  fflush (stdout);
  return rc;
}
