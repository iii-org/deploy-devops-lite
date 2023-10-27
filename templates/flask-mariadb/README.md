# Flask todo mariadb example

## 開發者注意事項

:warning: 若專案建立後程式碼Pull到local端下來無法執行, 此狀況為正常現象

* 要在local端測試部屬提供兩種方式，透過安裝docker來進行專案快速專案部屬或直接修改作業系統的環境變數
* 若非用docker快速部屬想直接採用原本安裝在作業系統上的資料庫的話，請設定環境變數

```env
db_host: 指向到您的資料庫，例如localhost或是其他IP
db_name: 指向到您的資料庫名稱
db_username: 指向到您的資料庫使用者名稱
db_password: 指向到您的資料庫密碼
```

## 修改程式碼注意事項

1. 修改Python版本  
   版本若非 Python:3.9, 想要更換版本請至`Dockefile`修改為自己想要的版本
2. 部屬環境額外環境變數
   若開發需求上可能有針對專案需要的特別環境變數，由於目前此需求不在系統開發考慮範圍內，因此可能要麻煩使用者透過修改`Dockerfile`
   的形式去加入

```dockerfile
ENV 環境變數名稱1 值1
ENV 環境變數名稱2 值2
ENV 環境變數名稱3 值3
```

## iiidevops

* 目前系統pipeline限制，因此寫的服務請一定要在port:`5000`，資料庫類型無法更改。
* `iiidevops`資料夾內`pipeline_settings.json`請勿更動

## 範例教學來源

https://youtu.be/yKHJsLUENl0

## reference

https://www.python-engineer.com/posts/flask-todo-app/
