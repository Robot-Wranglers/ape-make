# The prelude patch 0034 reads before every makefile; each value is a default, and a later assignment in a makefile wins.
__bash__ := $(firstword $(wildcard $(addsuffix /bash,$(subst :, ,$(PATH)))))
SHELL := $(or $(value AMK_SHELL),$(if $(__bash__),bash,/bin/sh))
.SHELLFLAGS := $(or $(value AMK_SHELLFLAGS),$(if $(__bash__),-euo pipefail -c,-eu -c))
MAKEFLAGS = -s -S --warn-undefined-variables
.DEFAULT_GOAL := $(value AMK_GOAL)
__file__ ?= $(firstword $(MAKEFILE_LIST))
amk = $(MAKE) -f $(abspath $(__file__))
