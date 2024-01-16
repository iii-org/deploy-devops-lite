# III DevOps Community

[English](README.md) | [繁體中文](docs/README.zh_TW.md)

## Table of Contents

[toc]

## System requirements

- Operating system
    - Ubuntu 20.04
- Hardware requirements
    - 2 vCPU
    - 8 GB RAM
    - 60 GB disk space (SSD recommended)
- IO speed
    - 300 MB/s

### Before we start...

We need to prepare the following information before we start the deployment program.

- [ ] The IP address of the server (Any IP address that can be accessed by the browser)
- [ ] The account and password of the server (not root but **must** have sudo permission) (e.g. `ubuntu`)

## Installation

### Step 1. Download deployment program and install docker and other system packages

- Fetching the latest version of the deployment program

    ```shell
    git clone https://github.com/iii-org/deploy-devops-lite.git IIIDevOps
    ```

### Step 2. Setting up the environment variables (Optional)

- If you wish setting up the environment variables before running the deployment program, you can run the following

    ```shell
    # Change to the project root directory
    cd IIIDevOps
    ./scripts/generate-env.sh all
    ```

During the execution of the script, it will prompt you to enter the environment variables.  
If the question followed by a default value, you can press `<Enter>` to use the default value.

You can check the environment variables in the `.env` file.

Or you can simply skip this step, it will prompt you to enter the environment variables when you run the deployment
program.

### Step 3. Run the deployment program

> This step will take up to 10 minutes to complete.

In this step, we will run the setup script.  
For the packages we haven't installed, the script will automatically install and configure them.  
For the environment variables we haven't set up in the previous step, the script will check and prompt you to enter
them.

To run the script, make sure you are in the project root directory, and run the following command

```shell
./run.sh
```

If any error occurs, it will show the message starting with `[ERROR]` and exit the script.  
If the script runs successfully, it will show the message something like

```
[INFO] XX:XX:XX Script executed successfully
```

You can open the browser and visit `http://<IP_ADDRESS>` to check if the III DevOps Community has been deployed
successfully.

## Upgrade

Run `./run.sh upgrade` to upgrade the III DevOps Community.  
The upgrade script will automatically fetch the latest version of the deployment program and run it.

## Uninstall

> The uninstall script will remove all the docker containers, images, and volumes, it will **REMOVE ALL THE DATA**.
> Please make sure you have backed up all the data.

Run `./run.sh clean` to uninstall the III DevOps Community.
