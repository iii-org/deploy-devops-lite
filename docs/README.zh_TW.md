<p align="center">
  <p align="center">
   <img width="128px" src="icons/iii_logo.png" />
  </p>
	<h1 align="center"><b>III DevOps Community</b></h1>
	<p align="center">
		All-in-One Project Management and Development Platform
    <br />
    <a href="https://www.iii-devsecops.org"><strong>www.iii-devsecops.org »</strong></a>
  </p>
</p>

<br/>

[English](../README.md) | [繁體中文](README.zh_TW.md)

## 系統需求

- 作業系統
    - Ubuntu 20.04
- Docker
    - Docker Engine 20.10+
    - Compose 2.20+
- 硬體需求
    - 2 vCPU
    - 8 GB RAM
    - 60 GB 磁碟空間 (建議使用 SSD)
- 磁碟 IO 速度
    - 300 MB/s

### 在開始之前...

我們需要在開始部署之前準備以下資訊。

- [ ] 伺服器的 IP 位址 (任何瀏覽器都可以連線的 IP 位址)
- [ ] 伺服器的帳號與密碼 (不是 root 但 **必須** 要有 sudo 權限) (e.g. `ubuntu`)

## 安裝

### 步驟 1. 下載部署程式

- 取得最新版本的部署程式

    ```shell
    git clone https://github.com/iii-org/deploy-devops-lite.git DevOps
    ```

### 步驟 2. 執行部署程式（包含自動安裝 docker 與其他必要的系統套件）

> [!NOTE]\
> 這個步驟會花費最多 10 分鐘的時間。

在這個步驟中，我們將會執行設定腳本。  
如果問題後面有預設值，你可以按下 `<Enter>` 來使用預設值。

對於我們需要的環境變數，如果尚未設定腳本會檢查並提示你輸入它們。  
你輸入的結果會設定到 `.env` 檔案中作為使用的環境變數。

請進入部署程式目錄，然後執行安裝腳本

```shell
cd DevOps
./run.sh
```

如果任何錯誤發生，它會顯示以 `[ERROR]` 開頭的訊息並退出腳本。  
如果腳本執行成功，它會顯示類似以下的訊息

```
[INFO] XX:XX:XX Script executed successfully
```

你可以打開瀏覽器並連上 `http://<IP_ADDRESS>` 來檢查 III DevOps Community 是否已經成功部署。

## 升級

進入部署程式目錄並執行 `./run.sh upgrade` 來升級 III DevOps Community。  
升級腳本會自動取得最新版本的部署程式並執行。

## 移除

> [!WARNING]\
> 移除腳本會移除所有的 docker 容器、映像檔與儲存空間。  
> 它會 **移除你已經建立的所有資料**  
> 請確保你已經備份所有的資料。

執行 `./run.sh clean` 來移除 III DevOps Community。

## 已知問題

- Docker Compose 版本問題（安裝腳本將嘗試下載可執行的版本進行自動修復）
    - 版本: 2.24.1
        - 出現訊息: xxx array items[0,1] must be unique
        - 參考: https://github.com/docker/compose/issues/11371
        - 解法: 降級 docker-compose 版本到 2.21 或升級 docker-compose 版本到 2.24.6 以上
    - 版本: 2.24.4, 2.24.5
        - 出現訊息: Circular reference in xxx yaml
        - 參考: https://github.com/docker/compose/issues/11430
        - 解法: 降級 docker-compose 版本到 2.21 或升級 docker-compose 版本到 2.24.6 以上

### 降級 docker-compose 套件

```shell
# 查看可用的版本
apt list -a docker-compose-plugin

# 安裝特定版本
sudo apt install docker-compose-plugin=2.21.0-1~ubuntu.20.04~focal
```