% payload/lib/trilog/lib/event_calculus.pl:
%  Shanahan's simplified event calculus, "The Event Calculus Explained", 1999,
%  loaded as text ahead of a rule base, which supplies initially/1, happens/2,
%  initiates/3 and terminates/3 and asks holdsAt/2. Time is any order the
%  comparison operators accept. Each supplied predicate has a failing clause
%  here, so the axioms hold on an empty rule base; loaded by name instead,
%  those clauses would be static and a rule base could not add to them.

initially(_) :- fail.
happens(_, _) :- fail.
initiates(_, _, _) :- fail.
terminates(_, _, _) :- fail.

holdsAt(F, T) :- initially(F), \+ clipped(0, F, T).
holdsAt(F, T) :- happens(E, T1), T1 < T, initiates(E, F, T1), \+ clipped(T1, F, T).
clipped(T1, F, T2) :- happens(E, T), T1 < T, T < T2, terminates(E, F, T).
declipped(T1, F, T2) :- happens(E, T), T1 < T, T < T2, initiates(E, F, T).
