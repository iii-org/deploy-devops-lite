# Deploy Devops Lite

## System requirements

- Operating system
    - Ubuntu 20.04+
    - Debian 11
- Hardware requirements
    - 1 vCPU
    - 8 GB RAM
    - 40 GB disk space (SSD recommended)

### Before we start...

We should prepare the info we need to deploy the devops lite.

- [ ] The IP address of the server
- [ ] The default password used to log in the server

## Installation

### Step 1. Download deployment program and install docker and other system packages

- Fetching the latest version of the deployment program

    ```shell
    git clone https://github.com/iii-org/deploy-devops-lite.git Lite
    ```

### Step 2. Setting up the environment variables (Optional)

- If you wish setting up the environment variables before running the deployment program, you can run the following

    ```shell
    # Change to the project root directory
    cd Lite
    ./script/generate_env.sh all
    ```

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
./setup.sh
```

If any error occurs, it will show the message starting with `[ERROR]` and exit the script.  
If the script runs successfully, it will show the message below

```
[NOTICE] Script executed successfully
```

You can open the browser and visit `http://<IP_ADDRESS>` to check if the DevOps Lite has been deployed successfully.

## Upgrade

Run `script/upgrade.sh` to upgrade the DevOps Lite.  
The script will automatically pull the latest code from the repository and run the deployment program.