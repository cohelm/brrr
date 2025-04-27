#!/usr/bin/env bash

set -euo pipefail

# Like ‘nix flake check’, but ignores any checks which are available on a binary
# cache.  Default nix flake check will download those to the local store.  On CI
# you don’t need that.


# Transform the output of nix-build or nix build --dry-run (the header which
# tells you what it’s about to do) into a list of deriving paths (specifically:
# output paths).  You can feed this directly back into nix build to actually
# build the derivations.  Notably this omits derivations which are just planned
# for _downloading_, which is useful on CI: if the binary cache has a copy,
# that’s good enough for me, no need to download it to an ephemeral CI runner
# only to discard it again.
#
# https://nix.dev/manual/nix/2.28/store/derivation/#deriving-path
plan-to-output() {
  sed -ne '/will be built:$/ {
	# label
	:b
	# next line
	n
	# If the line is indented, it is a store path
	/^ /{
	  # Print it
	  p
	  # goto label b
	  bb
	}
  }' | sed -e 's/$/^*/'
}

# shellcheck disable=SC2016
nix-build --dry-run --expr '(builtins.getFlake "git+file://${toString ./.}").checks.${builtins.currentSystem}' 2>&1 | \
	tee /dev/stderr | \
	plan-to-output | \
	xargs -r nix build --no-link --print-build-logs --keep-going
