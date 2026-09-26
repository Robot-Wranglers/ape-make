/* The quickjs guest's entry point: amk links the engine and its std library, not the qjs cli, so it supplies this. */

#include <stdio.h>
#include <string.h>

#include "quickjs.h"
#include "quickjs-libc.h"

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

  rc = js_guest_eval (ctx, js_guest_prelude, "<prelude>", JS_EVAL_TYPE_MODULE);
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
