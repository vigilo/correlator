NAME := correlator
include ../glue/Makefile.common
MODULE := vigilo.corr
CODEPATH := src/vigilo/corr
lint: lint_pylint
tests: tests_nose
all:
	@echo "Template Makefile, to be filled with build and install targets"


