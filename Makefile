NAME = correlator

all:
	@echo "Template Makefile, to be filled with build and install targets"

clean:
	find $(CURDIR) -name "*.pyc" -exec rm {} \;
	find $(CURDIR) -name "*~" -exec rm {} \;

apidoc: doc/apidoc/index.html
doc/apidoc/index.html: lib/vigilo
	rm -rf $(CURDIR)/doc/apidoc/*
	PYTHONPATH=lib epydoc -o $(dir $@) -v --name Vigilo --url http://www.projet-vigilo.org \
		--docformat=epytext $^

lint: lib/vigilo
	PYTHONPATH=lib pylint vigilo

.PHONY: all clean apidoc lint

