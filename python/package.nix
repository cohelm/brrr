{
  lib,
  callPackage,
  python,
  stdenvNoCC,

  pyproject-build-systems,
  uv2nix,
  pyproject-nix
}:

let
  uvWorkspace = uv2nix.lib.workspace.loadWorkspace {
    workspaceRoot = ./.;
  };
  uvOverlay = uvWorkspace.mkPyprojectOverlay {
    sourcePreference = "wheel";
  };
  pythonSet = (callPackage pyproject-nix.build.packages {
    inherit python;
  }).overrideScope (
    lib.composeManyExtensions [
      pyproject-build-systems.overlays.default
      uvOverlay
      # https://pyproject-nix.github.io/uv2nix/patterns/testing.html
      (final: prev: {
        brrr = prev.brrr.overrideAttrs (old: {
          passthru = old.passthru or {} // {
            tests = {
              mypy = stdenvNoCC.mkDerivation {
                inherit (old) src;
                nativeBuildInputs = [ brrr-venv-test ];
                dontConfigure = true;
                name = "brrr-mypy";
                buildPhase = ''
                  runHook preBuild
                  mypy src
                  runHook postBuild
                '';
                installPhase = ''
                  runHook preInstall
                  touch $out
                  runHook postInstall
                '';
              };
            } // (old.passthru.tests or {});
          };
        });
      })
    ]
  );
  editableOverlay = uvWorkspace.mkEditablePyprojectOverlay {
    # Set by devshell
    root = "$REPO_ROOT/python";
  };
  editablePythonSet = pythonSet.overrideScope (
    lib.composeManyExtensions [
      editableOverlay
      (final: prev: {
        brrr = prev.brrr.overrideAttrs (old: {
          src = lib.cleanSource ./.;
          nativeBuildInputs = old.nativeBuildInputs or [] ++ final.resolveBuildSystem {
            editables = [];
          };
        });
      })
    ]
  );
  brrr-venv = pythonSet.mkVirtualEnv "brrr-env" uvWorkspace.deps.default;
  # A virtual env with all optional dependencies installed for demo & tests.
  brrr-venv-test = pythonSet.mkVirtualEnv "brrr-env-test" uvWorkspace.deps.all;
  brrr-venv-editable = editablePythonSet.mkVirtualEnv "brrr-env-editable" uvWorkspace.deps.all;
in
{
  brrr = pythonSet.brrr;
  inherit
    brrr-venv
    brrr-venv-test
    brrr-venv-editable;
}
