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
- IO 速度
    - 300 MB/s

### 在開始之前...

我們需要在開始部署之前準備以下資訊。

- [ ] 伺服器的 IP 位址 (任何瀏覽器都可以連線的 IP 位址)
- [ ] 伺服器的帳號與密碼 (不是 root 但 **必須** 要有 sudo 權限) (e.g. `ubuntu`)

## 安裝

### 步驟 1. 下載部署程式並安裝 docker 與其他系統套件

- 取得最新版本的部署程式

    ```shell
    git clone https://github.com/iii-org/deploy-devops-lite.git DevOps
    ```

### 步驟 2. 設定環境變數 (可選)

- 如果你想在執行部署程式之前先設定環境變數，你可以執行以下指令

    ```shell
    # 切換到專案根目錄
    cd DevOps
    ./scripts/generate-env.sh all
    ```

在執行腳本的過程中，它會提示你輸入環境變數。  
如果問題後面有預設值，你可以按下 `<Enter>` 來使用預設值。

你可以在 `.env` 檔案中檢查環境變數。

或者你可以直接跳過這個步驟，它會在執行部署程式時提示你輸入環境變數。

### 步驟 3. 執行部署程式

> [!NOTE]\
> 這個步驟會花費最多 10 分鐘的時間。

在這個步驟中，我們將會執行設定腳本。  
對於我們還沒安裝的套件，腳本會自動安裝並設定它們。  
對於我們在前一個步驟中還沒設定的環境變數，腳本會檢查並提示你輸入它們。

要執行腳本，請確定你在專案根目錄，然後執行以下指令

```shell
./run.sh
```

如果任何錯誤發生，它會顯示以 `[ERROR]` 開頭的訊息並退出腳本。  
如果腳本執行成功，它會顯示類似以下的訊息

```
[INFO] XX:XX:XX Script executed successfully
```

你可以打開瀏覽器並訪問 `http://<IP_ADDRESS>` 來檢查 III DevOps Community 是否已經成功部署。

## 升級

執行 `./run.sh upgrade` 來升級 III DevOps Community。  
升級腳本會自動取得最新版本的部署程式並執行。

## 移除

> [!WARNING]\
> 移除腳本會移除所有的 docker 容器、映像檔與儲存空間。  
> 它會 **移除所有的資料**  
> 請確保你已經備份所有的資料。

執行 `./run.sh clean` 來移除 III DevOps Community。
