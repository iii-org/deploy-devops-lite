# react-nginx-todo list
  * React ＋ Nginx Web開發範本
  * 使用Vite 取代原 yarn 的build tool, 其建置時間大幅縮減50%以上
    - [注意] .env 的變數，須以 VITE_REACT_APP_ 為開頭作為環境變數的傳遞
  * 此範本是 React To do list的範例, 並內建建立 III DevOps 的 pipeline 基本專案功能目錄, 預設只進行 SonarQube 原始碼掃描功能
  * 請𡢅前端程式碼請放入 app 內

## to do list
一個簡易的React to do list 的GitHub專案網頁，用戶可以從中管理待辦事項列表，添加和刪除任務，並以簡單客觀的方式組織它們。
詳細資訊請參照： [https://github.com/heitorgandolfi/to-dolist](https://github.com/heitorgandolfi/to-dolist)

## Lint 
  * 新增Lint程序至CI，若有需求檢查規則，請直接修改 .eslintrc.js ，
  * Lint預設為關閉，若需要可至 DevOps UI內的pipeline 開啟即可。
  * package.json 內備有預設的eslint 版本，使用者可依實際需求進行版本或套件更改