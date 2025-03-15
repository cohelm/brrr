{
  inputs = {
    garnix-lib.url = "github:garnix-io/garnix-lib";
    User.url = "github:garnix-io/user-module";
  };

  nixConfig = {
    extra-substituters = [ "https://cache.garnix.io" ];
    extra-trusted-public-keys = [ "cache.garnix.io:CTFPyKSLcx5RMJKfLo5EEPUObbA78b0YQ2DTCJXqr9g=" ];
  };

  outputs = inputs: inputs.garnix-lib.lib.mkModules {
    modules = [
      inputs.User.garnixModules.default
    ];

    config = { pkgs, ... }: {
      user = {
        user-project = {
          authorizedSshKeys = [ "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBxV3H9uRLwvKrkdTSHC3/TU8JN6QEe1FbNpJMSbXGLZ" ];
          groups = [ "wheel" ];
          shell = "bash";
          user = "user";
        };
      };

      garnix.deployBranch = "master";
    };
  };
}
