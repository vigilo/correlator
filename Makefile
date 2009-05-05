NAME = correlator

all:
	@echo "Template Makefile, to be filled with build and install targets"

bin/buildout:
	python extra/bootstrap.py

bin/python: bin/buildout
	./bin/buildout

clean:
	find $(CURDIR) \( -name "*.pyc" -o -name "*~" \) -delete

apidoc: doc/apidoc/index.html
doc/apidoc/index.html: lib/vigilo
	rm -rf $(CURDIR)/doc/apidoc/*
	PYTHONPATH=lib epydoc -o $(dir $@) -v \
		   --name Vigilo --url http://www.projet-vigilo.org \
		   --docformat=epytext $^

lint: bin/python
	./bin/python "$$(which pylint)" --rcfile=extra/pylintrc lib/vigilo

.PHONY: all clean apidoc lint

