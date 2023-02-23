#!/usr/bin/env bash

set -e

sudo sysctl -w vm.max_map_count=524288
sudo sysctl -w fs.file-max=131072
ulimit -n 131072
ulimit -u 8192

curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt-get install docker-ce=5:19.03.14~3-0~ubuntu-focal docker-ce-cli=5:19.03.14~3-0~ubuntu-focal docker-compose-plugin containerd.io -y

docker compose up -d
