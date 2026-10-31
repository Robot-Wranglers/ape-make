/* The engine table: one row per linked-in guest, and the one place that says which exist.  */

#ifndef AMK_H
#define AMK_H

#include <stdio.h>
#include <sys/types.h>
#include <sys/select.h>

/* The payload member make reads before any makefile.  */
#define AMK_PRELUDE_MK "/zip/__init__.mk"

/* The events make announces, and what each carries: goals names the goal list, settled names nothing and follows the parse, and the recipe, job and failure events name their target. */
enum amk_event
  {
    AMK_EVENT_GOALS,
    AMK_EVENT_RECIPE_START,
    AMK_EVENT_RECIPE_END,
    AMK_EVENT_SETTLED,
    AMK_EVENT_JOB_START,
    AMK_EVENT_TARGET_FAILED
  };

struct amk_event_info
  {
    const char *target;
    const char *status;
    int exit_code;
    int exit_sig;
    pid_t pid;
  };

extern const char *const amk_event_names[];

/* A mode: a named behaviour set over the whole make process. hook, when set, hears every event after the guest hooks; value_dir, when set, names the directory kept values live in. The default row has neither.  */
struct amk_mode
  {
    const char *name;
    void (*hook) (enum amk_event event, const struct amk_event_info *info);
    char *(*value_dir) (void);
  };
extern const struct amk_mode *const amk_modes[];
extern const struct amk_mode amk_dataflow_mode;
void amk_mode_init (void);
const struct amk_mode *amk_mode_active (void);
char *amk_setting (const char *name, const char *env, const char *dflt);
unsigned long amk_cksum_file (const char *path, int *ok);
int amk_split_argv (char *args, char **av, int max);
/* The spawn api: a goal list run in a fork of this parsed image as its own process group, the wait that collects it, the signal and terminal verbs over it, and the parking make's own reaping hands a spawned pid to. */
pid_t amk_spawn_goals (int n, char **words, int foreground, const char *stdout_path);
int amk_spawn_capture (const char *text, int n, char **words, char **value);
int amk_wait_child (pid_t want, int block, pid_t *got, int *code, int *sig, int *stopped);
int amk_kill_child (pid_t pid, int sig);
int amk_stop_child (pid_t pid);
int amk_spawn_live (pid_t pid);
int amk_resume_child (pid_t pid);
int amk_foreground (pid_t pid);
void amk_signal_spawned (int sig);
void amk_reap_foreign (pid_t pid, int code, int sig);
int amk_mail_take (pid_t pid, char **buf, size_t *len);
int amk_mail_send (const char *s, size_t n);
void amk_spawn_init (void);
/* The jobserver's ledgers, from posixos.c: make's own is the goals ledger, and amk opens more with the same verbs. Under acquire, ms below zero waits, zero answers at once, and any other is a bound in milliseconds; the wait serves the ask channel either way. */
struct jobserver;
struct jobserver *jobserver_goals (void);
struct jobserver *jobserver_new (void);
unsigned int jobserver_setup_on (struct jobserver *js, int slots, const char *style);
unsigned int jobserver_parse_auth_on (struct jobserver *js, const char *auth);
char *jobserver_get_auth_on (struct jobserver *js);
unsigned int jobserver_enabled_on (struct jobserver *js);
void jobserver_clear_on (struct jobserver *js);
void jobserver_release_on (struct jobserver *js, int is_fatal);
void jobserver_pre_child_on (struct jobserver *js, int recursive);
void jobserver_post_child_on (struct jobserver *js, int recursive);
void jobserver_signal_on (struct jobserver *js);
void jobserver_pre_acquire_on (struct jobserver *js);
unsigned int jobserver_acquire_on (struct jobserver *js, int ms);
#define JOBSERVER_WIDTH_MAX 64
void jobserver_width_on (struct jobserver *js, unsigned int width);
const char *jobserver_token_on (void);
void jobserver_release_token_on (struct jobserver *js, int is_fatal, const char *t);
/* Pools: named semaphores generalizing the jobserver into colored tokens for control structures and bounded concurrency, each a ledger of a size, goals being make's own with -j as its size; the builtins that open and read one, what this process holds given back at exit and forgotten in a fork. An abstraction over a pool, a goal pool with its spawn and map, opens one through these and holds its own tokens. */
void amk_pool_init (void);
void amk_pool_release_all (void);
void amk_pool_forget_held (void);
/* How a guest names make. A call resolves by the cascade: the name itself, then the name under amk., each as a make function first and a macro second since a promoted define is both; a name both spellings answer is refused. The explicit kinds take one layer by its full name; the bridge in function.c runs one layer, the cascade and the forked form sit on it. */
enum amk_as { AMK_AS_ANY, AMK_AS_FXN, AMK_AS_MACRO };
int amk_resolve (const char *name, char *full, size_t len, const char **err);
char *amk_call_as (int kind, const char *name, unsigned int argc, const char **args, const char **err);
char *amk_call (const char *name, unsigned int argc, const char **args, const char **err);
char *amk_call_kind (int kind, const char *name, unsigned int argc, const char **args, const char **err);
pid_t amk_call_begin (int kind, const char *name, unsigned int argc, const char **args, int *fd);
int amk_call_end (pid_t pid, char **text, const char **err);
struct amk_deadline { double at; long ms; };
void amk_deadline_push (long ms, struct amk_deadline *saved);
long amk_deadline_pop (const struct amk_deadline *saved);
int amk_deadline_active (void);
int amk_deadline_expired (void);
long amk_deadline_budget (void);
int amk_deadline_check (const char **err);
void amk_func_raise (const char *engine, const char *name, const char *msg);
void amk_raise (const char *msg);
int amk_call_open (void);
void amk_fail (const char *why);
void amk_call_enter (void);
int amk_call_leave (const char **err);
char *amk_var_get (const char *name);
char *amk_var_raw_get (const char *name);
int amk_has_db (void);
int amk_function_exists (const char *name);
void amk_var_set (const char *name, const char *value);
void amk_var_raw_set (const char *name, const char *value);
void amk_eval (const char *text);
extern int amk_queue_fd;
char *amk_collect (int *out, size_t *outlen, int *q, int *in, const char *feed, size_t feedlen);
void amk_queue_drain (int *fd, char **buf, size_t *len, size_t *cap);
char *amk_func_goal (char *o, char **argv, const char *funcname);
void amk_goal_init (void);
char *amk_func_require (char *o, char **argv, const char *funcname);
char *amk_func_dedent (char *o, char **argv, const char *funcname);
/* A warning at a location that honors silent as the command line and the environment asked it, and its builtin.  */
extern int amk_silent;
void amk_warning (const floc *flocp, const char *msg);
char *amk_func_warning (char *o, char **argv, const char *funcname);
char *amk_func_val_dedent (char *o, char **argv, const char *funcname);
char *amk_dedent (const char *text, size_t *basep, int *badp);
char *amk_func_cksum (char *o, char **argv, const char *funcname);
unsigned long amk_cksum (const unsigned char *data, size_t len);
char *amk_func_match (char *o, char **argv, const char *funcname);
/* The function profiler's frame: one per timed expansion, so a parent's self time excludes its children.  */
struct amk_prof_frame { double start; double child; struct amk_prof_frame *up; };
extern int amk_profile_on;
int amk_profile_enter (struct amk_prof_frame *f);
void amk_profile_leave (struct amk_prof_frame *f, const char *kind, const char *name);
void amk_profile_report (void);
void amk_import_target (const char *name, const char *engine, const char *body, const char *flags, const char *prereqs, const floc *flocp);
struct child;
struct amk_engine;
void amk_fork_settle (void);
void amk_engine_program (const struct amk_engine *e, const char *flags, const char *program);
char *amk_func_stdin (char *o, char **argv, const char *funcname);
char *amk_func_sys (char *o, char **argv, const char *funcname);
char *amk_func_bash (char *o, char **argv, const char *funcname);
char *amk_func_args (char *o, char **argv, const char *funcname);
unsigned int amk_call_argc (void);
void amk_args_macro (void);
char *amk_func_fxn (char *o, char **argv, const char *funcname);
/* The name an immediate assignment offers the one call that is its whole value: the call depth that call runs at, the variable, and the function armed with it.  */
struct amk_lhs
  {
    int depth;
    const char *var;
    const char *armed;
  };
void amk_lhs_open (struct amk_lhs *saved, const char *varname, const char *value);
void amk_lhs_close (struct amk_lhs *saved);
int amk_lhs_enter (void);
void amk_lhs_arm (int depth, const char *funcname);
void amk_lhs_leave (void);
char *amk_func_resolves (char *o, char **argv, const char *funcname);
char *amk_trim (char *s);
char *amk_kwarg (char *arg, char **value);
char *amk_func_kwarg (char *o, char **argv, const char *funcname);
char *amk_func_json5 (char *o, char **argv, const char *funcname);
char *amk_func_lib_find (char *o, char **argv, const char *funcname);
char *amk_func_lib_roots (char *o, char **argv, const char *funcname);
void amk_stdin_pending (struct child *child);
int amk_stdin_fd (const void *child);
void amk_stdin_drop (struct child *child);
void amk_program_from_stdin (const struct amk_engine *e, int argc, char **argv);
void amk_forget_children (void);
void amk_hook_fire (enum amk_event event, const struct amk_event_info *info);
void amk_engine_init (void);
extern char *amk_goal_autofill;
void amk_default_goal_settle (void);

/* The ask channel: recipes and jobs ask an op on a namespace over a pipe pair and read a line-framed reply, answered while make waits on children; a process that inherited a live pair forwards its workspace ops up it instead of holding a workspace. */
struct amk_chan { int req; int rep; char *buf; size_t len; };
void amk_ask_init (void);
void amk_ask_dispatch (int req, int rep);
void amk_ask_wait (int ms);
int amk_ask_fds (int *fds, int max);
/* Any other wait that blocks while children run adds the channel descriptors to its set and serves the ready ones after. */
int amk_ask_fdset (fd_set *rd);
void amk_ask_ready (fd_set *rd);
/* A recipe child's own pair: made before the spawn, its ends dup'd onto the named descriptors in the child, this side served while make waits, and dropped with the child. */
void amk_ask_child_pending (void);
int amk_ask_child_fds (int *req, int *rep, int *req_at, int *rep_at);
void amk_ask_child_spawned (struct child *child);
void amk_ask_child_drop (struct child *child);
pid_t amk_wait_any (int *status);
int amk_ask_forwarding (void);
/* The channel's state the spawn side sets up for a job: a pair per spawned slot and one for this process's own recipes, the pair a forwarder sends up, and the numbers recipes read theirs at.  */
#define AMK_SPAWNED 64
extern struct amk_chan amk_chan[];
extern int amk_up_req, amk_up_rep;
extern int amk_ask_fd[2];
void amk_chan_close (struct amk_chan *c);
void amk_ask_export (int req, int rep);
void amk_ask_children_drop (void);
/* A version per namespace, moved by each change an engine reports, and the requests held on the channel until one: a wait on the version, or an operation that answered park; the flag a serve raises instead of answering, the bump that retries what is held, and the answer never at exit.  */
#define AMK_NEVER 3
#define AMK_PARK 4
extern int amk_ask_hold;
struct amk_sink;
void amk_ns_changed (void);
void amk_ns_answered (void);
int amk_ns_answered_take (void);
int amk_ns_channel_op (const char *op);
unsigned long amk_ns_version (const char *ns);
void amk_ns_version_write (struct amk_sink *out, const char *ns);
void amk_ns_version_bump (const char *ns);
void amk_held_end (void);
int amk_fd_is_pipe (const char *spec);
int amk_write_all (int fd, const void *buf, size_t len);
/* The same write with the broken-pipe signal ignored around it, for a reader that may have gone.  */
int amk_write_quiet (int fd, const void *buf, size_t len);
/* What spawn and serve share: a served child's connection, a job's mail pipe, the goal list a job runs, the pid names it rearms, and the sweep at exit.  */
extern int amk_conn;
extern int amk_mail_fd;
extern int amk_exit_status;
int amk_run_goals (int n, char **words);
void amk_rearm_pid (const char *names);
void amk_sweep_spawned (void);

/* A served request: status 75 declines it, and it carries the three standard descriptors, the caller's mail pipe, and the call pair the caller's recipe holds.  */
#define AMK_STALE     75
#define AMK_NFD       6
#define AMK_MAILFD    3
#define AMK_ASKFD    4
#define AMK_REPLYFD   5
struct goaldep;
extern const char *amk_serve_path;
extern int amk_serve_argc;
extern char **amk_serve_argv;
void amk_serve (const char *sockpath, struct goaldep *deps) NORETURN;
void amk_client (const char *sockpath, int argc, char **argv) NORETURN;
int amk_resident (int argc, char **argv);
void amk_dispatch (int conn) NORETURN;
void amk_write_status (int fd, int status);
size_t amk_get_u32 (const char **p);
int amk_recv_request (int fd, char **bufp, int fds[AMK_NFD]);
void amk_clear_zygote_env (void);
char *amk_env_value (const char *p, size_t envc, const char *key);
void amk_import_env (const char *p, size_t envc, const char *rearm);
int amk_opt_takes_arg (const char *tok);
int amk_negotiate (const char *p, size_t argc);

/* make's own signal installer, from main.c, under the guards main.c defines it with.  */
#if !HAVE_DECL_BSD_SIGNAL && !defined bsd_signal
# if !defined HAVE_SIGACTION
#  define bsd_signal signal
# else
void (*bsd_signal (int sig, void (*func) (int))) (int);
# endif
#endif

/* A recipe asked its make to halt: the recipe's remaining lines and the process's remaining goals are dropped, and it leaves with AMK_HALT, which a make whose recursive recipe child leaves with it takes as the same request.  */
#define AMK_HALT 112
extern unsigned int amk_halt;

/* Where an engine's result goes: write appends bytes, and the make side decides where they land. */
struct amk_sink
  {
    void (*write) (struct amk_sink *, const char *, size_t);
  };
extern struct amk_sink amk_sink_stderr;
extern struct amk_sink amk_sink_stdout;
int amk_ask_forward (const char *line, struct amk_sink *out);
long amk_ask_begin (const char *line);
char *amk_ask_poll (unsigned long id);
char *amk_ask_collect (unsigned long id);
int amk_ask_result (char *reply, char **text, const char **err);
/* The expansion being built, as a sink: what an engine writes lands in make's own buffer at the call's place, with no copy between.  */
struct amk_expand_sink
  {
    struct amk_sink base;
    char *o;
  };
void amk_expand_write (struct amk_sink *s, const char *p, size_t n);
/* The engine whose kept-state call is running, and the ledger of what each engine gave make, shared by the workspaces and make's function definitions.  */
extern const char *amk_binding_engine;
void amk_binding_add (const char *engine, const char *kind, const char *name, size_t len);
void amk_binding_vars (const char *engine, const char *text, size_t len);
/* The namespace and workspace builtins and the bridges they use into make's function table.  */
void amk_handle_add (const char *ns, const char *op, size_t oplen, int star);
void *amk_ns_state (const struct amk_engine *e, const char *name, int open);
int amk_is_workspace_import (const char *name);
char *func_op (char *o, char **argv, const char *funcname);
char *func_handle (char *o, char **argv, const char *funcname);
char *func_ns (char *o, char **argv, const char *funcname);
char *func_ns_create (char *o, char **argv, const char *funcname);
char *func_workspace_import (char *o, char **argv, const char *funcname);
/* Engine builtins outside the kept states: an import target, and any builtin the row's interface lacks, a fatal error naming the engine and what it has.  */
char *func_import_target (char *o, char **argv, const char *funcname);
char *func_refuse (char *o, char **argv, const char *funcname);
/* The payload's entry points, which main calls before and while it reads its options.  */
void amk_payload_boot (int argc, char **argv);
void amk_payload_path (void);
void amk_payload_main (int *argcp, char ***argvp);
int amk_ape_unpack (const char *name, const char *dest, int force);
int amk_ape_list (void);
int amk_bundle (int n, char **files, const char *out);
/* make's table of every file it knows, which the goal references resolve against.  */
extern struct hash_table files;
/* The engine builtin and the bindings query, registered by make's function table.  */
char *func_engine (char *o, char **argv, const char *funcname);
char *func_bindings (char *o, char **argv, const char *funcname);

/* Every engine: main is its command line, the $(name ...) builtin, and an imported target's job; dashdash puts -- ahead of the program, cmdline splits the program into words, argv gives the $(name.argv ...) form. */
struct amk_cli_ops
  {
    int (*main) (int, char **);
    unsigned int dashdash:1;
    unsigned int cmdline:1;
    unsigned int argv:1;
  };

/* Every kept state: create gives a fresh opaque state, or null when the engine cannot make another; single marks an engine whose only state is main. Make owns every state and the namespace it belongs to; no guest sees a namespace name. */
struct amk_kept_ops
  {
    void *(*create) (void);
    unsigned int single:1;
  };

/* A scripting guest: exec runs code in a state; import runs code and lifts what it defines into make, printing the names of the variables it gave; module marks an import that takes a file's path rather than its text; hook, when set, hears every event in the state. */
struct amk_state_ops
  {
    struct amk_kept_ops kept;
    int (*exec) (void *state, struct amk_sink *out, const char *prog);
    int (*import) (void *state, struct amk_sink *out, const char *prog);
    unsigned int module:1;
    void (*hook) (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);
  };

/* A datastructure guest: get runs a program over the state and leaves it as it was; update runs one that may change it; load replaces the whole state with a text, all or nothing; dump prints the whole state as the text load takes back. Every output is a sequence of lines. filter, when set, runs a program over an input text with no state. open, when set, makes a backing file the store itself: it answers the state attached to that path, the old one closed, or null. */
struct amk_workspace_ops
  {
    struct amk_kept_ops kept;
    int (*get) (void *state, struct amk_sink *out, const char *prog);
    int (*update) (void *state, struct amk_sink *out, const char *prog);
    int (*load) (void *state, const char *text);
    int (*dump) (void *state, struct amk_sink *out);
    int (*filter) (struct amk_sink *out, const char *prog, const char *input);
    void *(*open) (void *state, const char *path, int shared);
  };

/* An engine is its command line and at most one of the two kept-state interfaces; amk_engines_check refuses any other row at startup. language is what its programs are written in, implementation the guest linked in, and version that guest's release. */
struct amk_engine
  {
    const char *name;
    const char *aliases;
    const char *language;
    const char *implementation;
    const char *version;
    const struct amk_cli_ops *cli;
    const struct amk_state_ops *state;
    const struct amk_workspace_ops *workspace;
    /* How a call is bounded in time: "handle" for the guest's deadline call, "option" for a leading --deadline, none when it cannot be.  */
    const char *deadline;
  };

extern const struct amk_engine amk_engines[];
const struct amk_engine *amk_engine_by_name (const char *name);
int amk_engine_called (const struct amk_engine *e, const char *word);
void amk_engines_check (void);
void amk_engines_json (FILE *out);
void amk_engine_versions (void);
void amk_star_macro (const char *star, int max_args);
char *amk_engine_filter (const struct amk_engine *e, int ac, char **av, const char *input, int *status);
unsigned char *amk_slurp (const char *path, size_t *len);
/* Every regular file under a directory, appended to a list the caller frees, and the order a sort gives them.  */
void amk_walk (const char *dir, char ***names, size_t *n, size_t *cap);
int amk_walk_cmp (const void *a, const void *b);
/* The define decorator rewrite, the awk rule in the payload: a makefile's text before the parse, evaluated text, and the command that does only the rewrite.  */
char *amk_preprocess (const char *text, const char *filenm, int *status);
char *amk_preprocess_file (FILE *fp, const char *filenm);
char *amk_preprocess_text (const char *text, const floc *flocp);
int amk_preprocess_main (int argc, char **argv);
/* The kept-state interface a row has, if any, the operation words that interface takes on a namespace, and whether a word is one of them; every engine registers the names of all of them.  */
#define AMK_OPS_ALL "exec import get update load"
const struct amk_kept_ops *amk_engine_kept (const struct amk_engine *e);
const char *amk_engine_ops (const struct amk_engine *e);
int amk_engine_has_op (const struct amk_engine *e, const char *word, size_t len);
/* Whether a row is a workspace row, and the workspace row a namespace name reaches: its owner, else the first workspace row in the build, else null. */
int amk_engine_is_workspace (const struct amk_engine *e);
const struct amk_engine *amk_workspace_engine (const char *ns);
/* A load line: every row claims its name and aliases as file extensions, the first row in the table wins a contested one, and the file goes to that row's import or workspace load in main.  */
const struct amk_engine *amk_engine_by_extension (const char *ext);
const char *amk_engine_extensions (void);
int amk_load_file (const floc *flocp, const char *path, int noerror);

/* The ask channel's ways in: an op on any namespace, a workspace's made on first use, and a workspace row's stateless filter.  */
int amk_ns_ask (struct amk_sink *out, const char *op, const char *ns, const char *prog);
int amk_workspace_filter (struct amk_sink *out, const char *engine, const char *prog, const char *input);
/* A workspace's backing declaration for a namespace: a mode word, then a path past run; a repeat must match. */
int amk_workspace_backing (const char *ns, const char *spec);

/* What the workspaces use of the namespaces: a name's owner, whether a name is one word, a name held and opened on first use, one operation run in a state or applied to a namespace with its backing around it, and create with its handles.  */
const struct amk_engine *amk_ns_owner (const char *name);
int amk_ns_valid (const char *name);
void *amk_ns_open (const struct amk_engine *e, const char *name, int open);
int amk_state_run (const struct amk_engine *e, void *state, struct amk_sink *out, const char *op, const char *prog);
int amk_ns_apply (const struct amk_engine *e, const char *ns, struct amk_sink *out, const char *op, const char *prog);
void amk_ns_create (const struct amk_engine *e, const char *ns, const char *funcname);
/* What the namespaces use of the workspaces: the backing read before an operation and written after a write, a forwarder's call up the channel, and a backing named at create.  */
int amk_backing_sync_in (const struct amk_engine *e, const char *ns, void **statep);
int amk_backing_sync_out (const struct amk_engine *e, const char *ns, void *state, const char *op);
int amk_workspace_forward (struct amk_sink *out, const char *op, const char *ns, const char *prog, const char *funcname);
void amk_workspace_declare (char *o, const struct amk_engine *e, const char *ns, const char *spec, const char *funcname);

/* A guest's make function: fn answers make's call with the state it was defined in; a name make has already is refused with -1, a name this state defined before is rebound with 1, and a new one answers 0. */
int amk_func_add (const char *name, void *state, char *(*fn) (void *state, const char *name, unsigned int argc, char **argv));

extern int gawk_main (int argc, char **argv);
extern int jq_main (int argc, char **argv);
extern void *jq_create (void);
extern int jq_get (void *state, struct amk_sink *out, const char *prog);
extern int jq_update (void *state, struct amk_sink *out, const char *prog);
extern int jq_load (void *state, const char *text);
extern int jq_dump (void *state, struct amk_sink *out);
extern int jq_filter (struct amk_sink *out, const char *prog, const char *input);
extern int sqlite_main (int argc, char **argv);
extern void *sqlite_create (void);
extern void *sqlite_open (void *state, const char *path, int shared);
extern int sqlite_get (void *state, struct amk_sink *out, const char *prog);
extern int sqlite_update (void *state, struct amk_sink *out, const char *prog);
extern int sqlite_load (void *state, const char *text);
extern int sqlite_dump (void *state, struct amk_sink *out);
extern char *sqlite_json5 (const char *text, const char **err);
extern int lua_run_main (int argc, char **argv);
extern void *lua_create (void);
extern int lua_exec (void *state, struct amk_sink *out, const char *prog);
extern int lua_import (void *state, struct amk_sink *out, const char *prog);
extern void lua_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);
extern int s7_run_main (int argc, char **argv);
extern void *s7_create (void);
extern int s7_exec (void *state, struct amk_sink *out, const char *prog);
extern int s7_import (void *state, struct amk_sink *out, const char *prog);
extern void s7_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);
extern int micropy_run_main (int argc, char **argv);
extern void *micropy_create (void);
extern int micropy_exec (void *state, struct amk_sink *out, const char *prog);
extern int micropy_import (void *state, struct amk_sink *out, const char *prog);
extern void micropy_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);
extern int wasm3_main (int argc, char **argv);
extern void *wasm_create (void);
extern int wasm_exec (void *state, struct amk_sink *out, const char *prog);
extern int wasm_import (void *state, struct amk_sink *out, const char *prog);
extern int js_run_main (int argc, char **argv);
extern void *js_create (void);
extern int js_exec (void *state, struct amk_sink *out, const char *prog);
extern int js_import (void *state, struct amk_sink *out, const char *prog);
extern void js_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);

#endif
