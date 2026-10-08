# W3C scxml implementation report tests, core groups

`core.json` maps a test id to its scxml document: the W3C template with the conformance
attributes instantiated for a Lua datamodel, the way lxsc's own suite runner instantiates
them. `conf:pass` and `conf:fail` are the final states `pass` and `fail`, `targetpass` and
`targetfail` are targets, and the condition and expression attributes are Lua.

The tests are chapter 3 of the specification, states, transitions, parallel, history and
the selection of transitions, with `raise` from 4.2, `if` from 4.3 and the null datamodel
from B.1: forty-five documents, test 403 in three parts. The source is
https://www.w3.org/Voice/2013/scxml-irp/, dual-licensed under the W3C Test Suite License
and the W3C 3-clause BSD License.
