# Copyright © 2024  Brrr Authors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixpkgs-unstable";
    systems.url = "systems";
    flake-parts.url = "github:hercules-ci/flake-parts";
    devshell.url = "github:numtide/devshell";
    services-flake.url = "github:juspay/services-flake";
    process-compose-flake.url = "github:Platonic-Systems/process-compose-flake";
    # Heavily inspired by
    # https://pyproject-nix.github.io/uv2nix/usage/hello-world.html
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, flake-parts, ... }@inputs: flake-parts.lib.mkFlake { inherit inputs; } {
    systems = import inputs.systems;
    imports = [
      inputs.process-compose-flake.flakeModule
      inputs.devshell.flakeModule
    ];
    # A reusable process-compose module (for flake-parts) with either a full
    # demo environment, or just the dependencies if you want to run a server
    # manually.
    flake = {
      processComposeModules.default = { pkgs, ... }: {
        imports = [
          ./localstack.nix
          (inputs.services-flake.lib.multiService ./brrr-demo.nix)
        ];
        services = let
          demoEnv = {
            AWS_ENDPOINT_URL = "http://localhost:4566";
            AWS_ACCESS_KEY_ID = "000000000000";
            AWS_SECRET_ACCESS_KEY = "localstack-foo";
            AWS_DEFAULT_REGION = "us-east-1";
          };
        in {
          redis.r1.enable = true;
          localstack.enable = true;
          brrr-demo.worker = {
            package = self.packages.${pkgs.system}.brrr-demo;
            args = [ "worker" ];
            environment = demoEnv;
          };
          brrr-demo.server = {
            package = self.packages.${pkgs.system}.brrr-demo;
            args = [ "server" ];
            environment = demoEnv;
          };
        };
      };
    };
    perSystem = { config, self', inputs', pkgs, lib, system, ... }: let
      uvWorkspace = inputs.uv2nix.lib.workspace.loadWorkspace {
        workspaceRoot = ./.;
      };
      uvOverlay = uvWorkspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };
      python = pkgs.python312;
      pythonSet = (pkgs.callPackage inputs.pyproject-nix.build.packages {
        inherit python;
      }).overrideScope (
        lib.composeManyExtensions [
          inputs.pyproject-build-systems.overlays.default
          uvOverlay
        ]
      );
    in {
      config = {
        process-compose.demo = {
          imports = [
            inputs.services-flake.processComposeModules.default
            self.processComposeModules.default
          ];
          services.brrr-demo.server.enable = true;
          services.brrr-demo.worker.enable = true;
        };
        process-compose.deps = {
          imports = [
            inputs.services-flake.processComposeModules.default
            self.processComposeModules.default
          ];
          services.brrr-demo.server.enable = false;
          services.brrr-demo.worker.enable = false;
        };
        packages = {
          inherit python;
          inherit (pkgs) uv;
          # As far as I understand pyprojectnix and uv2nix, you want to use
          # virtual envs even for prod-level final derivations because a
          # virtualenv includes all the dependencies and a python which knows
          # how to find them.
          default = pythonSet.mkVirtualEnv "brrr-env" uvWorkspace.deps.default;
          # Bare package without any env setup for other packages to include as
          # a lib (again: I think?)
          brrr = pythonSet.brrr;
          # Stand-alone brrr_demo.py script
          brrr-demo = pkgs.stdenvNoCC.mkDerivation {
            name = "brrr-demo.py";
            dontUnpack = true;
            installPhase = ''
              mkdir -p $out/bin
              cp ${./brrr_demo.py} $out/bin/brrr_demo.py
            '';
            buildInputs = [
              # Dependencies for the demo are marked as ‘dev’
              (pythonSet.mkVirtualEnv "brrr-dev-env" uvWorkspace.deps.all)
            ];
            # The patch phase will automatically use the python from the venv as
            # the interpreter for the demo script.
            meta.mainProgram = "brrr_demo.py";
          };
          docker = let
            pkg = self'.packages.brrr-demo;
          in pkgs.dockerTools.buildLayeredImage {
            name = "brrr-demo";
            tag = "latest";
            config.Entrypoint = [ "${lib.getExe pkg}" ];
          };
        };
        devshells = {
          impure = {
            packages = with self'.packages; [
              python
              uv
            ];
            env = [
              {
                name = "PYTHONPATH";
                unset = true;
              }
              {
                name = "UV_PYTHON_DOWNLOADS";
                value = "never";
              }
            ];
          };
          default = let
            editableOverlay = uvWorkspace.mkEditablePyprojectOverlay {
              # Set by devshell
              root = "$PRJ_ROOT";
            };
            editablePythonSet = pythonSet.overrideScope editableOverlay;
            virtualenv = editablePythonSet.mkVirtualEnv "brrr-dev-env" uvWorkspace.deps.all;
          in {
            env = [
              {
                name = "PYTHONPATH";
                unset = true;
              }
              {
                name = "UV_PYTHON_DOWNLOADS";
                value = "never";
              }
              {
                name = "UV_NO_SYNC";
                value = "1";
              }
            ];
            packages = [
              pkgs.process-compose
              self'.packages.uv
              self'.packages.brrr-demo
              virtualenv
            ];
            commands = [
              # Always build aarch64-linux
              {
                name = "brrr-build-docker";
                category = "build";
                help = "Build and load a Docker image (requires a Nix Linux builder)";
                command = let
                  drv = self'.packages.docker;
                in ''
                  (
                    set -o pipefail
                    if nix build --no-link --print-out-paths .#packages.aarch64-linux.docker | xargs cat | docker load; then
                      echo 'Start a new worker with `docker run ${drv.imageName}:${drv.imageTag}`'
                    fi
                  )
                '';
              }
              {
                name = "brrr-demo-full";
                category = "demo";
                help = "Launch a full demo locally";
                command = ''
                  nix run .#demo
                '';
              }
              {
                name = "brrr-demo-deps";
                category = "demo";
                help = "Start all dependent services without any brrr workers / server";
                command = ''
                  nix run .#deps
                '';
              }
            ];
          };
        };
      };
    };
  };
}
