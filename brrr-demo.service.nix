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

# Brrr-demo module for services-flake.  Awkwardly named file because
# services-flake insists on auto-deriving the module name from the filename.
# Ok.

{ config, pkgs, name, lib, ... }: {
  options = with lib.types; {
    # You’ll want to override this unless you use an overlay
    package = lib.mkPackageOption pkgs "brrr-demo" { };
    args = lib.mkOption {
      default = [];
      type = listOf str;
    };
    environment = lib.mkOption {
      type = types.attrsOf types.str;
      default = { };
      example = {
        AWS_ENDPOINT_URL = "http://localhost:12345";
      };
      description = ''
        Extra environment variables passed to the `brrr-demo` process.
      '';
    };
  };
  config = {
    outputs.settings.processes.${name} = {
      environment = config.environment;
      command = "${lib.getExe config.package} ${lib.escapeShellArgs config.args}";
    };
  };
}
