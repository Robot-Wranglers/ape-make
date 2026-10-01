## The Canary

Never mention the holy name of the user -- it must never be spoken by a machine.  Refer to them only as "Human".

## Reporting

Answer questions when they are asked -- do not leap into action. 

For actions that are requested, wrap up a turn by saying what you did, what you found, what you changed.  Be specific.  Mention file names, class-names, tickets involved.  

Many discussion are easier with tables.  Tabular data, detailed explanations or process descriptions, and especially choices for Human, should all have their major points INDEXED (e.g. "P1" or "Case3") so that we can refer to them more easily.

Tests should always have a preamble of the INTENT and the TARGETS that are involved (labels, suites, etc), and your best guess for an ETA.  Similarly for anything that's long-running.

Do NOT invent terms outside of design sessions where those are the specific topic of discussion.  We use the in-house norms or accepted domain-specific technical terminology.

## Permissions & Blockers 

Blocked by permissions or hooks?  Don't ask Human to do something until you've consulted this document.  As a last resort, ask for help, but do so by presenting some option for a clickable button or a runnable-nudge.

## Documentation

The main documentation in README.md is off-limits for edits unless you're asked to update it.

Correcting *errors* in other docs is ok -- but do not add sections or paragraphs unless directed.  Tables or catalogs are open, correcting omissions there is generally good.

Running updates for WIP is actively harmful for documentation!  Wait until features are finished.

If you're asked to write documentation, remember: prose paired with fenced code is good, and encouraged.  But prose is for describing concepts, and not for describing code.  Let the code describe itself.  Syntax in prose is discouraged -- that just means we need a fenced example.

## Testing

Read `tests/README.md`, and use the `tests` skill in `.claude/skills/tests/` for every run. Run tests unfiltered in the background and read the task's own output file; a run piped through tail or a narrow grep loses failures. A failure on a clean checkout has a ticket; search the tracker for the test's name before calling it a regression.

Tests are for testing, and they should pin behavior.  Demos should demo, i.e. they are illustrative and instructive.  Docs are for documentation, and cover mostly concepts.  Do not confuse or conflate these things.

## Ticket Track

Project tickets live in `.tkt.fossil` at the repository root, driven by the `tkt` command. The `tkt` skill in `.claude/skills/tkt/` covers the verbs, ticket structure, rewriting versus commenting, cross-references, read-only sql, and the web ui. Use it for all ticket work.

The tracker is gitignored, so a fresh clone creates it once with `tkt init`, which `make init` also runs when `tkt` is installed. Install the skill with `tkt skill install --project`, and rerun that after upgrading `tkt`.

These rules add to the skill for this repository:

- **Links.** Mention a ticket by its link, http://localhost:<port>/tktview/<id>, so Human can open it. Check `tkt status` first; when no server runs give the id and title and offer `tkt serve`.
- **Drafts.** Hooks here block heredocs, so draft any body into `scratch/` with the Write tool and pipe it: `cat scratch/ticket-body.md | tkt new title='foo explodes'`. A draft is spent once it is filed; move it to `/tmp` then, since a spent draft left in `scratch/` reads as a live doc to the next session.
- **Structure.** A finding that matters but fits none of the skill's four sections belongs
  in a notes doc under `scratch/`, not in the ticket.
- **Closure.** A fix verified only in an iso tree is not done: the ticket stays open with a comment saying what is still owed.