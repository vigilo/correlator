NAME := correlator
CODEPATH := src/vigilo/corr
EPYDOC_PARSE := vigilo\.correlator

all: build settings.ini

include buildenv/Makefile.common

settings.ini: settings.ini.in
	sed -e 's,@LOCALSTATEDIR@,$(LOCALSTATEDIR),g' settings.ini.in > settings.ini

install: install_python install_data
install_pkg: install_python_pkg install_data

install_python: settings.ini $(PYTHON)
	$(PYTHON) setup.py install --root=$(DESTDIR) --record=INSTALLED_FILES
install_python_pkg: settings.ini $(PYTHON)
	$(PYTHON) setup.py install --single-version-externally-managed --root=$(DESTDIR)

install_data: pkg/init pkg/initconf
	# init
	install -p -m 755 -D pkg/init $(DESTDIR)/etc/rc.d/init.d/$(PKGNAME)
	echo /etc/rc.d/init.d/$(PKGNAME) >> INSTALLED_FILES
	install -p -m 644 -D pkg/initconf $(DESTDIR)$(INITCONFDIR)/$(PKGNAME)
	echo $(INITCONFDIR)/$(PKGNAME) >> INSTALLED_FILES

clean: clean_python
	rm -f settings.ini
	rm -f src/twisted/plugins/dropin.cache

lint: lint_pylint
tests: tests_nose

.PHONY: install_pkg install_python install_python_pkg install_data
