# The make blocks of README.md, extracted beside this by the smoke.readme target, and the value each one promises.
include examples.mk

readme: check
	$(if $(filter awk,$(.FEATURES)),test "$(shout)" = "HELLO")
	$(if $(filter awk,$(.FEATURES)),test "$(head)" = "hell")
	$(if $(filter awk,$(.FEATURES)),test "$(pair)" = "a-b")
	$(if $(filter awk,$(.FEATURES)),test "$(second)" = "beta")
	$(if $(filter awk,$(.FEATURES)),test "$(pct)" = "37.5")
	$(if $(filter awk,$(.FEATURES)),test "$(longest)" = "portable")
	$(if $(filter jq,$(.FEATURES)),test "$(pkg.version)" = "1.2.3")
	$(if $(filter jq,$(.FEATURES)),test '$(strip $(frame))' = 'k/a k/b|')
	$(if $(filter lua,$(.FEATURES)),test "$(answer.lua)" = "42")
	$(if $(filter lua,$(.FEATURES)),test "$(count)" = "9")
	$(if $(filter s7,$(.FEATURES)),test "$(answer.s7)" = "42")
	$(if $(filter s7,$(.FEATURES)),test "$(big)" = "2432902008176640000")
	$(if $(filter micropy,$(.FEATURES)),test "$(answer.py)" = "7")
	$(if $(filter micropy,$(.FEATURES)),test "$(top)" = "bob")
	$(if $(filter js,$(.FEATURES)),test "$(answer.js)" = "42")
	$(if $(filter js,$(.FEATURES)),test "$(newest)" = "cmk")
	$(if $(filter jq,$(.FEATURES)),test "$(version)" = "1.2.3")
	$(if $(filter wasm,$(.FEATURES)),test "$(echoed)" = "Args: test.wasm; hello;")
	$(if $(filter wasm,$(.FEATURES)),test "$(strip $(fibs))" = "55 6765 832040")
	echo "readme: every example holds"
