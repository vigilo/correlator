NAME = correlator
GLUE = ../glue

all:
	@echo "Template Makefile, to be filled with build and install targets"

$(GLUE)/bin/buildout:
	make -C $(GLUE) bin/buildout

$(GLUE)/bin/python: $(GLUE)/bin/buildout
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

lint: $(GLUE)/bin/python
	$(GLUE)/bin/python "$$(which pylint)" --rcfile=$(GLUE)/extra/pylintrc src/vigilo

tests: $(GLUE)/bin/python
	PYTHONPATH=$(GLUE) VIGILO_SETTINGS_MODULE=settings_tests $(GLUE)/bin/python "$$(which nosetests)" tests

.PHONY: all clean buildclean apidoc lint tests

