# mip.mk: packages for the micropy guest, named in mip.manifest as json with spec, version, and sha256, cached once by version, on the guest's import path, and ready after the mip.install target.
$(amk.require micropy jq)

mip.cache ?= $(HOME)/.cache/amk/mip
mip.q = $(strip $(jq.argv -r,$(1),$(mip.manifest)))
mip.pkgs = $(if $(value mip.manifest),$(call mip.q,keys[]))
mip.dir = $(mip.cache)/$(1)/$(call mip.q,."$(1)".version)
mip.path = $(foreach p,$(mip.pkgs),$(call mip.dir,$(p)))
mip.missing = $(foreach p,$(mip.pkgs),$(if $(wildcard $(call mip.dir,$(p))/.ok),,$(p)))
MICROPYPATH += $(mip.path)

# The mip.get function installs a package into a fresh directory, digests every file by path and content, and publishes by rename only when the digest is the pinned one.
@micropy.exec
define micropy.mip
  import amk, binascii, hashlib, mip, os

  def _walk(d, rel=""):
    for e in sorted(os.ilistdir(d)):
      if e[1] == 0x4000:
        yield from _walk(d + "/" + e[0], rel + e[0] + "/")
      else:
        yield rel + e[0], d + "/" + e[0]

  def _get(name, dest):
    field = lambda f: amk.expand('$(call mip.q,."%s".%s)' % (name, f))
    tmp = dest + ".tmp-" + binascii.hexlify(os.urandom(4)).decode()
    mip.install(field("spec"), version=field("version"), target=tmp)
    h = hashlib.sha256()
    for rel, path in _walk(tmp):
      h.update(rel.encode() + b"\0" + open(path, "rb").read())
    got = binascii.hexlify(h.digest()).decode()
    if got != field("sha256"):
      amk.expand("$(error mip: %s digests to %s; pin it as its sha256 in mip.manifest)" % (name, got))
    open(tmp + "/.ok", "w").close()
    try:
      os.rename(tmp, dest)
    except OSError:
      pass

  amk.func("mip.get", _get)
endef

# A package's stamp is its version pinned, so the ones not on disk are the whole install.
.PHONY: mip.install
mip.install:
	$(foreach p,$(mip.missing),$(mip.get $(p),$(call mip.dir,$(p))))
