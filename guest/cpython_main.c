/* The cpython guest's entry point and kept state: amk links libpython, not the python cli, so it supplies these. */

#define PY_SSIZE_T_CLEAN
#include "Python.h"

#include "amk_guest.h"

/* The one kept state, which make holds as main; the globals of __main__ it runs in, and the make functions it has defined by name. */
static int cpython_kept;
static PyObject *cpython_globals;
static PyObject *cpython_funcs;

/* Under the engine flag make has parsed nothing, so the handle refuses rather than reads. */
static int
cpython_need_make (void)
{
  if (amk_has_db ())
    return 0;
  PyErr_SetString (PyExc_RuntimeError, "amk: no make database, running outside a makefile");
  return -1;
}

/* A string make allocated, as a Python str, freed here; null becomes None. */
static PyObject *
cpython_take_str (char *s)
{
  PyObject *o;
  if (s == NULL)
    Py_RETURN_NONE;
  o = PyUnicode_DecodeUTF8 (s, (Py_ssize_t) strlen (s), "surrogateescape");
  gmk_free (s);
  return o;
}

/* A value as the text make gets: a str as is, None as nothing, and anything else as str would show it, as a new reference. */
static PyObject *
cpython_text (PyObject *value)
{
  if (value == Py_None)
    return PyUnicode_FromString ("");
  return PyObject_Str (value);
}

static PyObject *
cpython_expand (PyObject *self, PyObject *arg)
{
  const char *text = PyUnicode_AsUTF8 (arg);
  (void) self;
  if (text == NULL || cpython_need_make () < 0)
    return NULL;
  return cpython_take_str (gmk_expand (text));
}

static PyObject *
cpython_eval (PyObject *self, PyObject *arg)
{
  const char *text = PyUnicode_AsUTF8 (arg);
  (void) self;
  if (text == NULL || cpython_need_make () < 0)
    return NULL;
  amk_eval (text);
  Py_RETURN_NONE;
}

static PyObject *
cpython_var_get (PyObject *self, PyObject *arg)
{
  const char *name = PyUnicode_AsUTF8 (arg);
  (void) self;
  if (name == NULL || cpython_need_make () < 0)
    return NULL;
  return cpython_take_str (amk_var_get (name));
}

/* A store defines a simple variable with the literal text of the value. */
static PyObject *
cpython_var_set (PyObject *self, PyObject *args)
{
  const char *name;
  PyObject *value, *text;
  (void) self;
  if (!PyArg_ParseTuple (args, "sO", &name, &value) || cpython_need_make () < 0)
    return NULL;
  text = cpython_text (value);
  if (text == NULL)
    return NULL;
  amk_var_set (name, PyUnicode_AsUTF8 (text));
  Py_DECREF (text);
  Py_RETURN_NONE;
}

/* call(name, *values): the make function or macro of that name, each value one whole argument, never expanded. */
static PyObject *
cpython_call (PyObject *self, PyObject *args)
{
  Py_ssize_t n = PyTuple_GET_SIZE (args) - 1, i;
  PyObject **texts, *result = NULL;
  const char **vals, *name, *err = NULL;
  char *s;

  (void) self;
  if (n < 0)
    {
      PyErr_SetString (PyExc_TypeError, "amk.call: needs a name");
      return NULL;
    }
  name = PyUnicode_AsUTF8 (PyTuple_GET_ITEM (args, 0));
  if (name == NULL || cpython_need_make () < 0)
    return NULL;
  texts = PyMem_Calloc ((size_t) n + 1, sizeof *texts);
  vals = PyMem_Calloc ((size_t) n + 1, sizeof *vals);
  for (i = 0; i < n; i++)
    {
      texts[i] = cpython_text (PyTuple_GET_ITEM (args, i + 1));
      if (texts[i] == NULL || (vals[i] = PyUnicode_AsUTF8 (texts[i])) == NULL)
        goto done;
    }
  s = amk_call (name, (unsigned int) n, vals, &err);
  if (s == NULL)
    PyErr_Format (PyExc_ValueError, "amk.call: %s", err);
  else
    result = cpython_take_str (s);
done:
  for (i = 0; i < n; i++)
    Py_XDECREF (texts[i]);
  PyMem_Free (texts);
  PyMem_Free (vals);
  return result;
}

/* make's call into a defined function: the arguments as strings, the result as text, and an error raised to whoever made the call. */
static char *
cpython_func_call (void *state, const char *nm, unsigned int argc, char **argv)
{
  PyObject *fn, *args, *result, *text;
  char *out = NULL;
  unsigned int i;

  (void) state;
  if (!cpython_kept || (fn = PyDict_GetItemString (cpython_funcs, nm)) == NULL)
    return NULL;
  args = PyTuple_New (argc);
  for (i = 0; args != NULL && i < argc; i++)
    PyTuple_SET_ITEM (args, i, PyUnicode_DecodeUTF8 (argv[i], (Py_ssize_t) strlen (argv[i]), "surrogateescape"));
  result = args != NULL ? PyObject_Call (fn, args, NULL) : NULL;
  Py_XDECREF (args);
  text = result != NULL ? cpython_text (result) : NULL;
  Py_XDECREF (result);
  if (text != NULL && PyUnicode_AsUTF8 (text) != NULL)
    {
      const char *t = PyUnicode_AsUTF8 (text);
      out = gmk_alloc ((unsigned int) strlen (t) + 1);
      strcpy (out, t);
    }
  else
    {
      PyObject *exc = PyErr_GetRaisedException ();
      PyObject *why = PyUnicode_FromFormat ("%s: %S", Py_TYPE (exc)->tp_name, exc);
      amk_func_raise ("cpython", nm, why != NULL ? PyUnicode_AsUTF8 (why) : Py_TYPE (exc)->tp_name);
      Py_XDECREF (why);
      Py_XDECREF (exc);
      PyErr_Clear ();
    }
  Py_XDECREF (text);
  return out;
}

/* func(name, fn): make gains a function of that name whose arguments reach fn as strings and whose result is what fn returns; only the kept state outlives the call to answer. */
static PyObject *
cpython_func (PyObject *self, PyObject *args)
{
  const char *name;
  PyObject *fn;
  (void) self;
  if (!PyArg_ParseTuple (args, "sO", &name, &fn))
    return NULL;
  if (!cpython_kept)
    {
      PyErr_SetString (PyExc_RuntimeError, "amk.func: only from cpython.exec, since a one-shot call's state ends with the call");
      return NULL;
    }
  if (cpython_need_make () < 0)
    return NULL;
  if (!PyCallable_Check (fn))
    {
      PyErr_SetString (PyExc_TypeError, "amk.func: fn must be callable");
      return NULL;
    }
  if (amk_func_add (name, &cpython_kept, cpython_func_call) < 0)
    {
      PyErr_Format (PyExc_RuntimeError, "amk.func: %s is a make function already", name);
      return NULL;
    }
  if (PyDict_SetItemString (cpython_funcs, name, fn) < 0)
    return NULL;
  Py_RETURN_NONE;
}

static PyMethodDef cpython_amk_methods[] = {
  { "expand", cpython_expand, METH_O, "The text expanded by make." },
  { "eval", cpython_eval, METH_O, "The text read by make as makefile syntax." },
  { "var_get", cpython_var_get, METH_O, "A make variable's value, or None." },
  { "var_set", cpython_var_set, METH_VARARGS, "Define a simple make variable." },
  { "call", cpython_call, METH_VARARGS, "Call a make function or macro." },
  { "func", cpython_func, METH_VARARGS, "Define a make function." },
  { NULL, NULL, 0, NULL },
};

static struct PyModuleDef cpython_amk_module = { PyModuleDef_HEAD_INIT, "_amk", NULL, -1, cpython_amk_methods };

static PyObject *
cpython_amk_init (void)
{
  return PyModule_Create (&cpython_amk_module);
}

/* The amk module over _amk, and the export import runs: a callable as a make function, a list or tuple as words, a dict as fields named name.key, a bool as true or nothing, and a str or number as its text; None, modules, and types are skipped. */
static const char *cpython_amk_prelude =
  "import sys, types, _amk\n"
  "amk = types.ModuleType('amk')\n"
  "class _Var:\n"
  "  def __getattr__(self, name): return _amk.var_get(name)\n"
  "  def __setattr__(self, name, value): _amk.var_set(name, value)\n"
  "  def __getitem__(self, name): return _amk.var_get(name)\n"
  "  def __setitem__(self, name, value): _amk.var_set(name, value)\n"
  "amk.var = _Var()\n"
  "amk.expand, amk.eval, amk.call, amk.func = _amk.expand, _amk.eval, _amk.call, _amk.func\n"
  "amk.on = {}\n"
  "_spell = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.')\n"
  "def _ok(name):\n"
  "  return bool(name) and name[0] != '_' and set(name) <= _spell\n"
  "def _text(v):\n"
  "  return '' if v is None else v if isinstance(v, str) else str(v)\n"
  "def _export(before, g):\n"
  "  names = []\n"
  "  def put(name, v):\n"
  "    if v is None or isinstance(v, (types.ModuleType, type)):\n"
  "      return\n"
  "    if isinstance(v, dict):\n"
  "      for k in v:\n"
  "        if not isinstance(k, str):\n"
  "          raise ValueError('amk import: %s has a key that is not a str' % name)\n"
  "      for k in sorted(v):\n"
  "        if not _ok(k):\n"
  "          raise ValueError('amk import: %s has a key make cannot spell: %s' % (name, k))\n"
  "        put(name + '.' + k, v[k])\n"
  "      return\n"
  "    if callable(v):\n"
  "      _amk.func(name, v)\n"
  "    elif isinstance(v, bool):\n"
  "      _amk.var_set(name, 'true' if v else '')\n"
  "    elif isinstance(v, (list, tuple)):\n"
  "      _amk.var_set(name, ' '.join(_text(i) for i in v))\n"
  "    else:\n"
  "      _amk.var_set(name, _text(v))\n"
  "    names.append(name)\n"
  "  for k in sorted(g):\n"
  "    if _ok(k) and not (k in before and before[k] is g[k]):\n"
  "      put(k, g[k])\n"
  "  return ' '.join(names)\n"
  "amk._export = _export\n"
  "sys.modules['amk'] = amk\n";

/* Python's own buffers on stdout and stderr written through, then C's, so a capture sees everything the chunk printed. */
static void
cpython_flush (void)
{
  static const char *const names[] = { "stdout", "stderr" };
  size_t i;
  for (i = 0; i < 2; i++)
    {
      PyObject *f = PySys_GetObject (names[i]), *r;
      if (f == NULL || f == Py_None)
        continue;
      r = PyObject_CallMethod (f, "flush", NULL);
      Py_XDECREF (r);
      PyErr_Clear ();
    }
  fflush (stdout);
  fflush (stderr);
}

/* The pending exception settled: the SystemExit status when the chunk exits, 1 with the traceback on stderr otherwise. */
static int
cpython_settle (void)
{
  int status = 1;
  if (PyErr_ExceptionMatches (PyExc_SystemExit))
    {
      PyObject *exc = PyErr_GetRaisedException ();
      PyObject *code = PyObject_GetAttrString (exc, "code");
      if (code == NULL || code == Py_None)
        status = 0;
      else if (PyLong_Check (code))
        status = (int) (PyLong_AsLong (code) & 255);
      else
        {
          PyObject *s = PyObject_Str (code);
          cpython_flush ();
          fprintf (stderr, "%s\n", s != NULL ? PyUnicode_AsUTF8 (s) : "");
          Py_XDECREF (s);
        }
      Py_XDECREF (code);
      Py_XDECREF (exc);
      PyErr_Clear ();
      return status;
    }
  PyErr_Print ();
  cpython_flush ();
  return status;
}

/* Run the chunk in the given globals: 0 on success, else as cpython_settle answers. */
static int
cpython_run_chunk (const char *src, PyObject *globals)
{
  PyObject *r = PyRun_StringFlags (src, Py_file_input, globals, globals, NULL);
  if (r == NULL)
    return cpython_settle ();
  Py_DECREF (r);
  return 0;
}

/* The interpreter, once per process: its home the payload, so the standard library zipped under lib/python3.12/ is found in place, with make keeping its signals, then the amk module bound in __main__. */
static int
cpython_open (void)
{
  PyConfig config;
  PyStatus status;
  PyObject *prelude;

  if (Py_IsInitialized ())
    return 0;
  if (PyImport_AppendInittab ("_amk", cpython_amk_init) < 0)
    return -1;
  PyConfig_InitPythonConfig (&config);
  config.site_import = 0;
  config.write_bytecode = 0;
  config.install_signal_handlers = 0;
  config.parse_argv = 0;
  status = PyConfig_SetString (&config, &config.home, L"/zip");
  if (!PyStatus_Exception (status))
    status = Py_InitializeFromConfig (&config);
  PyConfig_Clear (&config);
  if (PyStatus_Exception (status))
    {
      fprintf (stderr, "cpython: %s\n", status.err_msg ? status.err_msg : "cannot initialize");
      return -1;
    }
  cpython_globals = PyModule_GetDict (PyImport_AddModule ("__main__"));
  cpython_funcs = PyDict_New ();
  prelude = PyDict_New ();
  if (cpython_run_chunk (cpython_amk_prelude, prelude) != 0)
    return -1;
  PyDict_SetItemString (cpython_globals, "amk", PyDict_GetItemString (prelude, "amk"));
  Py_DECREF (prelude);
  return 0;
}

/* The module amk as the prelude built it, borrowed. */
static PyObject *
cpython_amk (void)
{
  return PyDict_GetItemString (cpython_globals, "amk");
}

/* argv[1] is Python source text rather than a command line; whatever it prints is the result. A fork of an image that holds the kept state runs it in fresh globals, so a one-shot call sees none of that state. */
__attribute__ ((visibility ("default"))) int
cpython_run_main (int argc, char **argv)
{
  PyObject *globals;
  int rc;

  if (argc < 2 || argv[1] == NULL)
    {
      fprintf (stderr, "cpython: no chunk\n");
      return 2;
    }
  if (cpython_open () != 0)
    return 1;
  cpython_kept = 0;
  globals = PyDict_New ();
  PyDict_SetItemString (globals, "__name__", PyUnicode_FromString ("__main__"));
  PyDict_SetItemString (globals, "__builtins__", PyEval_GetBuiltins ());
  PyDict_SetItemString (globals, "amk", cpython_amk ());
  rc = cpython_run_chunk (argv[1], globals);
  Py_DECREF (globals);
  cpython_flush ();
  return rc;
}

/* CPython's own command line over the words as given, its home the payload unless the caller named one; nothing of amk is bound. */
__attribute__ ((visibility ("default"))) int
cpython_tool_main (int argc, char **argv)
{
  PyConfig config;
  PyStatus status;

  PyConfig_InitPythonConfig (&config);
  status = PyConfig_SetBytesArgv (&config, argc, argv);
  if (!PyStatus_Exception (status) && getenv ("PYTHONHOME") == NULL)
    status = PyConfig_SetString (&config, &config.home, L"/zip");
  if (!PyStatus_Exception (status))
    status = Py_InitializeFromConfig (&config);
  PyConfig_Clear (&config);
  if (PyStatus_Exception (status))
    Py_ExitStatusException (status);
  return Py_RunMain ();
}

/* The create member: the one kept state, which make holds as main; a second create answers null, since the interpreter has one set of globals. */
__attribute__ ((visibility ("default"))) void *
cpython_create (void)
{
  if (cpython_kept)
    return NULL;
  if (cpython_open () != 0)
    {
      fprintf (stderr, "cpython: cannot create state\n");
      return NULL;
    }
  cpython_kept = 1;
  return &cpython_kept;
}

/* exec runs the chunk with what it writes to stdout going to the sink; import runs it with output on stderr, then hands make the globals it defined or rebound and the sink their names. */
static int
cpython_run_op (void *state, struct amk_sink *out, const char *op, const char *prog)
{
  struct amk_capture capture;
  PyObject *before, *names;
  const char *text;
  int rc;

  (void) state;
  if (prog == NULL)
    {
      fprintf (stderr, "cpython.%s: no chunk\n", op);
      return 2;
    }
  cpython_flush ();
  if (strcmp (op, "import") != 0)
    {
      amk_capture_begin_to (&capture, out);
      rc = cpython_run_chunk (prog, cpython_globals);
      cpython_flush ();
      amk_capture_end (&capture, out);
      return rc;
    }

  before = PyDict_Copy (cpython_globals);
  amk_capture_begin (&capture);
  rc = cpython_run_chunk (prog, cpython_globals);
  cpython_flush ();
  amk_capture_end (&capture, &amk_sink_stderr);
  if (rc != 0)
    {
      Py_DECREF (before);
      return rc;
    }
  names = PyObject_CallMethod (cpython_amk (), "_export", "OO", before, cpython_globals);
  Py_DECREF (before);
  if (names == NULL || (text = PyUnicode_AsUTF8 (names)) == NULL)
    {
      Py_XDECREF (names);
      fprintf (stderr, "cpython.import: ");
      return cpython_settle ();
    }
  out->write (out, text, strlen (text));
  out->write (out, "\n", 1);
  Py_DECREF (names);
  return 0;
}

__attribute__ ((visibility ("default"))) int
cpython_exec (void *state, struct amk_sink *out, const char *prog)
{
  return cpython_run_op (state, out, "exec", prog);
}

__attribute__ ((visibility ("default"))) int
cpython_import (void *state, struct amk_sink *out, const char *prog)
{
  return cpython_run_op (state, out, "import", prog);
}

/* The hook primitive: amk.on[event], when the state holds a callable there, is called with the event as a dict. Its print goes to stderr, and an error reports there and is otherwise ignored. */
__attribute__ ((visibility ("default"))) void
cpython_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid)
{
  struct amk_capture capture;
  PyObject *on, *fn, *e, *r;

  (void) state;
  on = PyObject_GetAttrString (cpython_amk (), "on");
  fn = on != NULL && PyDict_Check (on) ? PyDict_GetItemString (on, event) : NULL;
  if (fn == NULL || !PyCallable_Check (fn))
    {
      Py_XDECREF (on);
      PyErr_Clear ();
      return;
    }
  cpython_flush ();
  amk_capture_begin (&capture);
  e = Py_BuildValue ("{s:s,s:s,s:s,s:i,s:i,s:l}", "event", event, "target", target, "status", status,
                     "code", exit_code, "signal", exit_sig, "pid", pid);
  r = e != NULL ? PyObject_CallOneArg (fn, e) : NULL;
  if (r == NULL)
    {
      cpython_flush ();
      fprintf (stderr, "cpython hook %s: ", event);
      cpython_settle ();
    }
  Py_XDECREF (r);
  Py_XDECREF (e);
  Py_DECREF (on);
  cpython_flush ();
  amk_capture_end (&capture, &amk_sink_stderr);
}
