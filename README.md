<p align="center">
  <p align="center">
   <img width="128px" src="docs/icons/iii_logo.png" />
  </p>
	<h1 align="center"><b>III DevOps Community</b></h1>
	<p align="center">
		All-in-One Project Management and Development Platform
    <br />
    <a href="https://www.iii-devsecops.org"><strong>www.iii-devsecops.org »</strong></a>
  </p>
</p>

<br/>

[English](README.md) | [繁體中文](docs/README.zh_TW.md)

## System requirements

- Operating system
    - Ubuntu 20.04
- Docker
    - Docker Engine 20.10+
    - Compose 2.20+
- Hardware requirements
    - 2 vCPU
    - 8 GB RAM
    - 60 GB disk space (SSD recommended)
- Disk IO speed
    - 300 MB/s

### Before we start...

We need to prepare the following information before we start the deployment program.

- [ ] The IP address of the server (Any IP address that can be accessed by the browser)
- [ ] The account and password of the server (not root but **must** have sudo permission) (e.g. `ubuntu`)

## Installation

### Step 1. Download deployment program 

- Fetching the latest version of the deployment program

    ```shell
    git clone https://github.com/iii-org/deploy-devops-lite.git DevOps
    ```

### Step 2. Run the deployment program (including automatic installation of Docker and other necessary system packages)

> [!NOTE]\
> This step will take up to 10 minutes to complete.

In this step, we will run the setup script.  
During the execution of the script, it will prompt you to enter the environment variables.  
If the question followed by a default value, you can press `<Enter>` to use the default value.

For the environment variables we need, the script will check and prompt you to enter them if they are not already set.  
The results you enter will be set in the `.env` file as the environment variables used.

Make sure you are in the deployment program directory, and run the script as following command

```shell
cd DevOps
./run.sh
```

If you haven't installed Docker yet, this script will automatically install Docker for you and will terminate after the installation is complete. You will need to re-run `./run.sh`.
If any error occurs, it will show the message starting with `[ERROR]` and exit the script.  
If the script runs successfully, it will show the message something like

```
[INFO] XX:XX:XX Script executed successfully
```

You can open the browser and visit `http://<IP_ADDRESS>` to check if the III DevOps Community has been deployed successfully.

## Upgrade

Enter the deployment program directory and run `./run.sh upgrade` to upgrade the III DevOps Community.  
The upgrade script will automatically fetch the latest version of the deployment program and run it.

## Uninstall

> [!WARNING]\
> The uninstall script will remove all the docker containers, images, and volumes.    
> It will **REMOVE ALL YOUR DATA**.  
> Please make sure you have backed up all the data.

Run `./run.sh clean` to uninstall the III DevOps Community.

## Known issues

- Docker compose related (The installation script will try to download the correct version for automatic repair)
    - version: 2.24.1
        - Message: xxx array items[0,1] must be unique
        - See: https://github.com/docker/compose/issues/11371
        - Solution: Downgrade docker-compose version to 2.21 or upgrade docker-compose version to 2.24.6 or above
    - version: 2.24.4, 2.24.5
        - Message: Circular reference in xxx yaml
        - See: https://github.com/docker/compose/issues/11430
        - Solution: Downgrade docker-compose version to 2.21 or upgrade docker-compose version to 2.24.6 or above

### Downgrade docker compose plugin

```shell
# List all the available versions
apt list -a docker-compose-plugin

# Install the specific version
sudo apt install docker-compose-plugin=2.21.0-1~ubuntu.20.04~focal
```