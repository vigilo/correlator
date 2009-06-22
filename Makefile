NAME = correlator

all:
	@echo "Template Makefile, to be filled with build and install targets"

bin/buildout:
	python extra/bootstrap.py

bin/python: bin/buildout
	./bin/buildout

clean:
	find $(CURDIR) \( -name "*.pyc" -o -name "*~" \) -delete
buildclean: clean
	rm -rf eggs develop-eggs parts .installed.cfg bin src/vigilo_correlator.egg-info

apidoc: doc/apidoc/index.html
doc/apidoc/index.html: src/vigilo
	rm -rf $(CURDIR)/doc/apidoc/*
	PYTHONPATH=src epydoc -o $(dir $@) -v \
		   --name Vigilo --url http://www.projet-vigilo.org \
		   --docformat=epytext $^

lint: bin/python
	./bin/python "$$(which pylint)" --rcfile=extra/pylintrc src/vigilo

tests: 
	./unittests/runtests.py

.PHONY: all clean buildclean apidoc lint tests

