# Deploy DevOps Lite

[English](README.md) | [繁體中文](README.zh_TW.md)

## 系統需求

- 作業系統
    - Ubuntu 20.04+ 或更新版本
    - Debian 11
- 硬體需求
    - 1 個虛擬 CPU
    - 8 GB RAM 記憶體
    - 40 GB 硬碟空間（建議使用 SSD）

### 開始前須知

在執行 Deploy DevOps Lite 之前，需先準備以下資訊：

- [ ] 伺服器的 IP 位址
- [ ] 伺服器登入預設密碼

## 安裝步驟

### 步驟 1：下載部署程式，並安裝 Docker 和其他系統套件

- 下載最新版部署程式

  ```shell
  git clone https://github.com/iii-org/deploy-devops-lite.git Lite
  ```

- 或直接下載 [更新腳本](https://raw.githubusercontent.com/iii-org/deploy-devops-lite/master/script/upgrade.sh)

  ```shell
  wget https://raw.githubusercontent.com/iii-org/deploy-devops-lite/master/script/upgrade.sh -O upgrade.sh
  chmod +x upgrade.sh
  
  ./upgrade.sh
  ```

### 步驟 2：設定環境變數（可選）

- 如果您希望在執行部署程式之前設定環境變數，請執行以下指令：

  ```shell
  # 切換到專案根目錄
  cd Lite
  ./script/generate_env.sh all
  ```

您可以確認設定的環境變數在 `.env` 檔案中。

或者您也可以跳過此步驟，當您執行部署程式時，它會提示您輸入環境變數。

### 步驟 3：執行部署程式

> 此步驟需耗時至少 10 分鐘。

在此步驟中，我們將執行設定腳本。  
對於我們尚未安裝的套件，腳本將會自動完成安裝及設定。  
對於上一步驟中未設定的環境變數，腳本將會檢查並提示您輸入。

要執行腳本，請確保您在專案根目錄中，然後執行以下命令：

```shell
./setup.sh
```

如果發生任何錯誤，它將顯示以 “[ERROR]” 開頭的訊息並退出腳本。  
如果腳本成功執行，它將顯示以下訊息：

```shell
[NOTICE] Script executed successfully
```

您可以在您的瀏覽器中輸入 `http://<IP_ADDRESS>` 來檢查 DevOps Lite 是否已成功部署。

## 更新

執行 `script/update.sh` 來更新 DevOps Lite。  
此腳本會拉取最新更新並重新啟動 docker compose。