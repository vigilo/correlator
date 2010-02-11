NAME := correlator
PKGNAME := vigilo-$(NAME)
MODULE := vigilo.corr
CODEPATH := src/vigilo/corr
SYSCONFDIR := /etc
LOCALSTATEDIR := /var
DESTDIR = 

define find-distro
if [ -f /etc/debian_version ]; then \
	echo "debian" ;\
elif [ -f /etc/mandriva-release ]; then \
	echo "mandriva" ;\
else \
	echo "unknown" ;\
fi
endef
DISTRO := $(shell $(find-distro))
ifeq ($(DISTRO),debian)
	INITCONFDIR = /etc/default
else ifeq ($(DISTRO),mandriva)
	INITCONFDIR = /etc/sysconfig
else
	INITCONFDIR = /etc/sysconfig
endif

all: build settings.ini

settings.ini: settings.ini.in
	sed -e 's,@LOCALSTATEDIR@,$(LOCALSTATEDIR),g' settings.ini.in > settings.ini

install: settings.ini
	$(PYTHON) setup.py install --single-version-externally-managed --root=$(DESTDIR) --record=INSTALLED_FILES
	# init
	install -p -m 755 -D pkg/init.$(DISTRO) $(DESTDIR)/etc/rc.d/init.d/$(PKGNAME)
	echo /etc/rc.d/init.d/$(PKGNAME) >> INSTALLED_FILES
	install -p -m 644 -D pkg/initconf.$(DISTRO) $(DESTDIR)$(INITCONFDIR)/$(PKGNAME)
	echo $(INITCONFDIR)/$(PKGNAME) >> INSTALLED_FILES

clean: clean_python
	rm -f settings.ini

include ../glue/Makefile.common
lint: lint_pylint
tests: tests_nose
