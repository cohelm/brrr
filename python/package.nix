{
  lib,
  callPackage,
  python,

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
    ]
  );
  editableOverlay = uvWorkspace.mkEditablePyprojectOverlay {
    # Set by devshell
    root = "$REPO_ROOT/python";
  };
  editablePythonSet = pythonSet.overrideScope editableOverlay;
in
{
  brrr = pythonSet.brrr;
  brrr-venv = pythonSet.mkVirtualEnv "brrr-env" uvWorkspace.deps.default;
  # A virtual env with all optional dependencies installed for demo & tests.
  brrr-venv-test = pythonSet.mkVirtualEnv "brrr-env-test" uvWorkspace.deps.all;
  brrr-venv-editable = editablePythonSet.mkVirtualEnv "brrr-env-editable" uvWorkspace.deps.all;
}
