/* The engine table: one row per linked-in guest, and the one place that says which exist.  */

#ifndef AMK_H
#define AMK_H

#include <stdio.h>
#include <sys/types.h>
#include <sys/select.h>

/* The payload member make reads before any makefile.  */
#define AMK_PRELUDE_MK "/zip/__init__.mk"

/* The events make announces, and what each carries: goals names the goal list, the recipe events name their target. */
enum amk_event
  {
    AMK_EVENT_GOALS,
    AMK_EVENT_RECIPE_START,
    AMK_EVENT_RECIPE_END
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
/* The spawn api: a goal list run in a fork of this parsed image as its own process group, the wait that collects it, the signal and terminal verbs over it, and the parking make's own reaping hands a spawned pid to. */
pid_t amk_spawn_goals (int n, char **words, int foreground, const char *stdout_path);
void amk_spawn_stdout_to_mail (void);
int amk_wait_child (pid_t want, int block, pid_t *got, int *code, int *sig, int *stopped);
int amk_kill_child (pid_t pid, int sig);
int amk_foreground (pid_t pid);
void amk_signal_spawned (int sig);
void amk_reap_foreign (pid_t pid, int code, int sig);
int amk_mail_take (pid_t pid, char **buf, size_t *len);
int amk_mail_send (const char *s, size_t n);
pid_t amk_call_begin (const char *name, unsigned int argc, const char **args, int *fd);
int amk_call_end (pid_t pid, char **text, const char **err);
char *amk_call (const char *name, unsigned int argc, const char **args, const char **err);
char *amk_var_get (const char *name);
int amk_has_db (void);
int amk_function_exists (const char *name);
void amk_var_set (const char *name, const char *value);
void amk_eval (const char *text);
extern int amk_queue_fd;
char *amk_collect (int *out, size_t *outlen, int *q, int *in, const char *feed, size_t feedlen);
char *amk_func_goal (char *o, char **argv, const char *funcname);
char *amk_func_require (char *o, char **argv, const char *funcname);
char *amk_func_dedent (char *o, char **argv, const char *funcname);
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
void amk_import_target (const char *name, const char *engine, const char *body, const char *flags, const floc *flocp);
struct child;
struct amk_engine;
void amk_fork_settle (void);
void amk_engine_program (const struct amk_engine *e, const char *flags, const char *program);
char *amk_func_stdin (char *o, char **argv, const char *funcname);
char *amk_func_sys (char *o, char **argv, const char *funcname);
void amk_stdin_pending (struct child *child);
int amk_stdin_fd (const void *child);
void amk_stdin_drop (struct child *child);
void amk_program_from_stdin (const struct amk_engine *e, int argc, char **argv);
void amk_forget_children (void);
void amk_hook_fire (enum amk_event event, const struct amk_event_info *info);
void amk_engine_init (void);
extern char *amk_goal_autofill;
void amk_default_goal_settle (void);

/* The call channel: recipes and jobs ask a workspace row's persist entry over a pipe pair and read a line-framed reply, answered while make waits on children; a process that inherited a live pair forwards up it instead of holding a workspace. */
struct amk_chan { int req; int rep; char *buf; size_t len; };
void amk_call_init (void);
void amk_call_dispatch (int req, int rep);
void amk_call_wait (int ms);
/* Any other wait that blocks while children run adds the channel descriptors to its set and serves the ready ones after. */
int amk_call_fdset (fd_set *rd);
void amk_call_ready (fd_set *rd);
/* A recipe child's own pair: made before the spawn, its ends dup'd onto the named descriptors in the child, this side served while make waits, and dropped with the child. */
void amk_call_child_pending (void);
int amk_call_child_fds (int *req, int *rep, int *req_at, int *rep_at);
void amk_call_child_spawned (struct child *child);
void amk_call_child_drop (struct child *child);
pid_t amk_wait_any (int *status);
int amk_call_forwarding (void);
/* The channel's state the spawn side sets up for a job: a pair per spawned slot and one for this process's own recipes, the pair a forwarder sends up, and the numbers recipes read theirs at.  */
#define AMK_SPAWNED 64
extern struct amk_chan amk_chan[];
extern int amk_up_req, amk_up_rep;
extern int amk_call_fd[2];
void amk_chan_close (struct amk_chan *c);
void amk_call_export (int req, int rep);
void amk_call_children_drop (void);
int amk_fd_is_pipe (const char *spec);
int amk_write_all (int fd, const void *buf, size_t len);
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
#define AMK_CALLFD    4
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
int amk_call_forward (const char *line, struct amk_sink *out);
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
/* The workspace builtins and the bridges they use into make's function table.  */
void amk_handle_add (const char *ns, const char *op, size_t oplen, int star);
void *amk_ns_state (const struct amk_engine *e, const char *name, int open);
char *amk_trim (char *s);
int amk_is_workspace_import (const char *name);
char *func_op (char *o, char **argv, const char *funcname);
char *func_handle (char *o, char **argv, const char *funcname);
char *func_ns (char *o, char **argv, const char *funcname);
char *func_import_target (char *o, char **argv, const char *funcname);
char *func_workspace_import (char *o, char **argv, const char *funcname);
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

/* The kept-state primitives, when a row has them: open gives a fresh opaque state, or null when the engine cannot open another; run executes one operation's program in a state, its output to the sink, and answers the status; hook hears every event in the given state; filter, when a row has one, runs a program over an input text with no state. ops names the operations make registers over run, space-separated. Make owns every state and the namespace it belongs to; no guest sees a namespace name. */
/* A workspace row is one with run and whole, and it meets the call channel's contract: ops holds get, update and load; get with the whole program prints the whole value; load with a text replaces it; every output is a sequence of lines, counted by the reply; filter, when the row has one, is its stateless run, and a row without one refuses the channel's filter. A backing writes the whole value out and loads it back through those two. */
struct amk_engine
  {
    const char *name;
    const char *aliases;
    int (*main) (int, char **);
    unsigned int dashdash:1;
    unsigned int cmdline:1;
    unsigned int argv:1;
    void *(*open) (void);
    int (*run) (void *state, struct amk_sink *out, const char *op, const char *prog);
    void (*hook) (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);
    int (*filter) (struct amk_sink *out, const char *prog, const char *input);
    const char *ops;
    const char *whole;
  };

extern const struct amk_engine amk_engines[];
const struct amk_engine *amk_engine_by_name (const char *name);
int amk_engine_called (const struct amk_engine *e, const char *word);
/* Whether a row is a workspace row, and the workspace row a namespace name reaches: its owner, else the first workspace row in the build, else null. */
int amk_engine_is_workspace (const struct amk_engine *e);
const struct amk_engine *amk_workspace_engine (const char *ns);

/* The call channel's way into a workspace: one operation on a namespace, made on first use, and the stateless filter.  */
int amk_workspace_call (struct amk_sink *out, const char *op, const char *ns, const char *prog);
int amk_workspace_filter (struct amk_sink *out, const char *prog, const char *input);
/* A workspace's backing declaration for a namespace: a mode word, then a path past run; a repeat must match. */
int amk_workspace_backing (const char *ns, const char *spec);

/* A guest's make function: fn answers make's call with the state it was defined in; a name make has already is refused with -1, a name this state defined before is rebound with 1, and a new one answers 0. */
int amk_func_add (const char *name, void *state, char *(*fn) (void *state, const char *name, unsigned int argc, char **argv));

extern int gawk_main (int argc, char **argv);
extern int jq_main (int argc, char **argv);
extern void *jq_open (void);
extern int jq_run (void *state, struct amk_sink *out, const char *op, const char *prog);
extern int jq_filter (struct amk_sink *out, const char *prog, const char *input);
extern int sqlite_main (int argc, char **argv);
extern void *sqlite_open (void);
extern int sqlite_run (void *state, struct amk_sink *out, const char *op, const char *prog);
extern int lua_run_main (int argc, char **argv);
extern void *lua_open (void);
extern int lua_run (void *state, struct amk_sink *out, const char *op, const char *prog);
extern void lua_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);
extern int s7_run_main (int argc, char **argv);
extern void *s7_open (void);
extern int s7_run (void *state, struct amk_sink *out, const char *op, const char *prog);
extern void s7_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);
extern int micropy_run_main (int argc, char **argv);
extern void *micropy_open (void);
extern int micropy_run (void *state, struct amk_sink *out, const char *op, const char *prog);
extern void micropy_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);
extern int wasm3_main (int argc, char **argv);
extern int js_run_main (int argc, char **argv);
extern void *js_open (void);
extern int js_run (void *state, struct amk_sink *out, const char *op, const char *prog);
extern void js_hook (void *state, const char *event, const char *target, const char *status, int exit_code, int exit_sig, long pid);

#endif
