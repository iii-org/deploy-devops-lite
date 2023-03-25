# ASP.NET MVC Web Example

## 注意事項
* 根目錄`sln`檔案為Sonarqube掃描必須檔案，若僅部屬服務不一定需要此sln檔案，僅原始碼+Dockerfile即可
* 掃描後仍需檢查確認送至Sonarqube UI的檔案是否相符

## 流程說明
![](https://i.imgur.com/l3UlTxh.png)

### (選擇性)透過Visual Studio 2019來建立專案
* 選擇`選擇建立新的專案`
![](https://i.imgur.com/XoGiezH.png)
* 上方過濾選擇`C#`、`所有平台`、`Web`
![](https://i.imgur.com/kMem7WO.png)
* 再選擇`ASP.NET Core Web 應用程式 (Model-View-Controller)`
這個選擇性非強制性的，就是只要是`.Net Core`或是其他有支援雲端的均可，只是此範本主要針對`Asp.Net Core`，以及初始範本建立即是MVC的選項。
![](https://i.imgur.com/vxcwd8w.png)
* 輸入專案名稱，這裡輸入自己的專案名稱
在這裡將以使用者常面臨的狀況，自訂專案名稱，因此取`WebApplication2`
![](https://i.imgur.com/j1L26QP.png)
* 在這裡勾選`啟用Docker`、並在下方下拉的`Docker OS`內選擇`Linux`
一般使用者若再自身電腦上安裝`Docker Deskktop`，其預設為`Linux`，而`Docker OS`為`Windows`的支援僅有`Windows pro`或是`enterprise`版本才有提供，`iiidevops`所提供的為`Linux`基礎的k8s部屬環境，所以無論是要在本地端或是iiidevops請都下拉`Docker OS`為`Linux`的選項。
![](https://i.imgur.com/Q1oUukq.png)
* 完成上述步驟後壓下`建立專案`
這個步驟請稍待幾分鐘，第一次會花費一些時間，若已完成會看到左下角出現`就緒`的文字
![](https://i.imgur.com/tdlfgtz.png)
* 測試本地端環境
上方執行測試環境請選擇`Docker`選項後執行一次確認是否Visual Studio建立的專案可以確實在本地端Docker上執行
![](https://i.imgur.com/FNilK6H.png)
選擇測試環境
![](https://i.imgur.com/5vMcIAm.png)
![](https://i.imgur.com/i6HoFSi.png)
正常運作畫面
* 均正常以後可以參考下方文件根據狀況做修改並放到專案內進行測試

### (選擇性)透過iiidevops的UI來建置專案
如果沒有現成專案的話可以考慮用範本
* 準備專案+從程式碼建立專案
用範本主要目的是為了省下.rancher-pipeline.yaml與iiidevops資料夾檔案
![](https://i.imgur.com/vpkFfIP.png)
* 放程式碼進去
`iiidevops`規定須放在`app`資料夾內
如果一般剛從`Visual Studio`建立專案名稱為`ASP-MVC-example`的專案，則會有下列目錄結構，sln檔案在上層，然後同一層會看到`ASP-MVC-example`的資料夾，這個資料夾放過去建立的iiidevops專案時資料夾要改名為`app`，sln檔案則一樣放在與專案同一層的目錄
```
D:.
│  .dockerignore
│  ASP-MVC-example.sln
│
└─ASP-MVC-example
    │  appsettings.Development.json
    │  appsettings.json
    │  ASP-MVC-example.csproj
    │  ASP-MVC-example.csproj.user
    │  Dockerfile
    │  Program.cs
    │  Startup.cs
    │
    ├─bin
    │  └─Debug
    │      └─netcoreapp3.1
    │              appsettings.Development.json
    │              appsettings.json
    │              ASP-MVC-example.deps.json
    │              ASP-MVC-example.dll
    │              ASP-MVC-example.exe
    │              ASP-MVC-example.pdb
    │              ASP-MVC-example.runtimeconfig.dev.json
    │              ASP-MVC-example.runtimeconfig.json
    │              ASP-MVC-example.Views.dll
    │              ASP-MVC-example.Views.pdb
    │
    ├─Controllers
    │      HomeController.cs
    │
    ├─Models
    │      ErrorViewModel.cs
    │
    ├─obj
    │  │  ASP-MVC-example.csproj.nuget.dgspec.json
    │  │  ASP-MVC-example.csproj.nuget.g.props
    │  │  ASP-MVC-example.csproj.nuget.g.targets
    │  │  project.assets.json
    │  │  project.nuget.cache
    │  │
    │  ├─Container
    │  │      ContainerDevelopmentMode.cache
    │  │      ContainerId.cache
    │  │      ContainerName.cache
    │  │      ContainerRunContext.cache
    │  │
    │  └─Debug
    │      └─netcoreapp3.1
    │          │  .NETCoreApp,Version=v3.1.AssemblyAttributes.cs
    │          │  apphost.exe
    │          │  ASP-MVC-example.AssemblyInfo.cs
    │          │  ASP-MVC-example.AssemblyInfoInputs.cache
    │          │  ASP-MVC-example.assets.cache
    │          │  ASP-MVC-example.csproj.AssemblyReference.cache
    │          │  ASP-MVC-example.csproj.CopyComplete
    │          │  ASP-MVC-example.csproj.CoreCompileInputs.cache
    │          │  ASP-MVC-example.csproj.FileListAbsolute.txt
    │          │  ASP-MVC-example.csprojAssemblyReference.cache
    │          │  ASP-MVC-example.dll
    │          │  ASP-MVC-example.GeneratedMSBuildEditorConfig.editorconfig
    │          │  ASP-MVC-example.genruntimeconfig.cache
    │          │  ASP-MVC-example.MvcApplicationPartsAssemblyInfo.cache
    │          │  ASP-MVC-example.pdb
    │          │  ASP-MVC-example.RazorAssemblyInfo.cache
    │          │  ASP-MVC-example.RazorAssemblyInfo.cs
    │          │  ASP-MVC-example.RazorCoreGenerate.cache
    │          │  ASP-MVC-example.RazorTargetAssemblyInfo.cache
    │          │  ASP-MVC-example.RazorTargetAssemblyInfo.cs
    │          │  ASP-MVC-example.TagHelpers.input.cache
    │          │  ASP-MVC-example.TagHelpers.output.cache
    │          │  ASP-MVC-example.Views.dll
    │          │  ASP-MVC-example.Views.pdb
    │          │
    │          ├─Razor
    │          │  └─Views
    │          │      │  _ViewImports.cshtml.g.cs
    │          │      │  _ViewStart.cshtml.g.cs
    │          │      │
    │          │      ├─Home
    │          │      │      Index.cshtml.g.cs
    │          │      │      Privacy.cshtml.g.cs
    │          │      │
    │          │      └─Shared
    │          │              Error.cshtml.g.cs
    │          │              _Layout.cshtml.g.cs
    │          │              _ValidationScriptsPartial.cshtml.g.cs
    │          │
    │          └─staticwebassets
    │                  ASP-MVC-example.StaticWebAssets.Manifest.cache
    │                  ASP-MVC-example.StaticWebAssets.xml
    │
    ├─Properties
    │      launchSettings.json
    │
    ├─Views
    │  │  _ViewImports.cshtml
    │  │  _ViewStart.cshtml
    │  │
    │  ├─Home
    │  │      Index.cshtml
    │  │      Privacy.cshtml
    │  │
    │  └─Shared
    │          Error.cshtml
    │          _Layout.cshtml
    │          _ValidationScriptsPartial.cshtml
    │
    └─wwwroot
        │  favicon.ico
        │
        ├─css
        │      site.css
        │
        ├─js
        │      site.js
        │
        └─lib
            ├─bootstrap
            │  │  LICENSE
            │  │
            │  └─dist
            │      ├─css
            │      │      bootstrap-grid.css
            │      │      bootstrap-grid.css.map
            │      │      bootstrap-grid.min.css
            │      │      bootstrap-grid.min.css.map
            │      │      bootstrap-reboot.css
            │      │      bootstrap-reboot.css.map
            │      │      bootstrap-reboot.min.css
            │      │      bootstrap-reboot.min.css.map
            │      │      bootstrap.css
            │      │      bootstrap.css.map
            │      │      bootstrap.min.css
            │      │      bootstrap.min.css.map
            │      │
            │      └─js
            │              bootstrap.bundle.js
            │              bootstrap.bundle.js.map
            │              bootstrap.bundle.min.js
            │              bootstrap.bundle.min.js.map
            │              bootstrap.js
            │              bootstrap.js.map
            │              bootstrap.min.js
            │              bootstrap.min.js.map
            │
            ├─jquery
            │  │  LICENSE.txt
            │  │
            │  └─dist
            │          jquery.js
            │          jquery.min.js
            │          jquery.min.map
            │
            ├─jquery-validation
            │  │  LICENSE.md
            │  │
            │  └─dist
            │          additional-methods.js
            │          additional-methods.min.js
            │          jquery.validate.js
            │          jquery.validate.min.js
            │
            └─jquery-validation-unobtrusive
                    jquery.validate.unobtrusive.js
                    jquery.validate.unobtrusive.min.js
                    LICENSE.txt
```
![](https://i.imgur.com/7cjHk66.png)
放過去以後會像是這樣
## 修改.rancher-pipeline.yaml檔案
範本預設的是NETCoreApp 3.1，如果開發者使用的版本比較新，這邊要才需要修改成相對應的版本，否則不用進行更改，只要有asp_dot_net.enabled: true即可，詳細如下:
### 原本範本(未修改前)

```
- name: Test--SonarQube for ASP.NET
  iiidevops: sonarqube
  steps:
  - applyAppConfig:
      answers:
        git.branch: ${CICD_GIT_BRANCH}
        git.commitID: ${CICD_GIT_COMMIT}
        git.repoName: ${CICD_GIT_REPO_NAME}
        git.url: ${CICD_GIT_URL}
        harbor.host: harbor-dev3.iiidevops.org
        pipeline.sequence: ${CICD_EXECUTION_SEQUENCE}
        asp_dot_net.enabled: true
      catalogTemplate: cattle-global-data:iii-dev-charts3-scan-sonarqube
      name: ${CICD_GIT_REPO_NAME}-${CICD_GIT_BRANCH}-sq
      targetNamespace: ${CICD_GIT_REPO_NAME}
      version: 0.2.5
  when:
    branch:
      include:
      - master
      - develop
```
### 修改範本(修改後)
如果開發環境比NETCoreApp 3.1版本更新，要增加一行tag` asp_dot_net.tag: ;`這邊請根據DockerFile裡面的版本進行修正。
![](https://i.imgur.com/qHLbn2R.png)
```
- name: Test--SonarQube for ASP.NET
  iiidevops: sonarqube
  steps:
  - applyAppConfig:
      answers:
        git.branch: ${CICD_GIT_BRANCH}
        git.commitID: ${CICD_GIT_COMMIT}
        git.repoName: ${CICD_GIT_REPO_NAME}
        git.url: ${CICD_GIT_URL}
        harbor.host: harbor-dev3.iiidevops.org
        pipeline.sequence: ${CICD_EXECUTION_SEQUENCE}
        asp_dot_net.enabled: true
        asp_dot_net.tag: 6.0
      catalogTemplate: cattle-global-data:iii-dev-charts3-scan-sonarqube
      name: ${CICD_GIT_REPO_NAME}-${CICD_GIT_BRANCH}-sq
      targetNamespace: ${CICD_GIT_REPO_NAME}
      version: 0.2.5
  when:
    branch:
      include:
      - master
      - develop
```

## 修改sln檔案
這個是因為前面有一個部分修改了專案的路徑從`專案名稱`資料夾，變成`app`資料夾，因此會有解析錯誤的問題需要修正。在下面說明將以範本內附送的sln檔案為例，變化主要就是`Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "ASP-MVC-example", "ASP-MVC-example\ASP-MVC-example.csproj", "{7898E239-AEB3-49F7-9707-394E19EADFE6}"`這裡變成`Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "ASP-MVC-example", "app\ASP-MVC-example.csproj", "{7898E239-AEB3-49F7-9707-394E19EADFE6}"
EndProject`。也就是`ASP-MVC-example\ASP-MVC-example.csproj`變成`app\ASP-MVC-example.csproj`
### 修改前
```
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 16
VisualStudioVersion = 16.0.31129.286
MinimumVisualStudioVersion = 10.0.40219.1
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "ASP-MVC-example", "ASP-MVC-example\ASP-MVC-example.csproj", "{7898E239-AEB3-49F7-9707-394E19EADFE6}"
EndProject
Global
	GlobalSection(SolutionConfigurationPlatforms) = preSolution
		Debug|Any CPU = Debug|Any CPU
		Release|Any CPU = Release|Any CPU
	EndGlobalSection
	GlobalSection(ProjectConfigurationPlatforms) = postSolution
		{7898E239-AEB3-49F7-9707-394E19EADFE6}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
		{7898E239-AEB3-49F7-9707-394E19EADFE6}.Debug|Any CPU.Build.0 = Debug|Any CPU
		{7898E239-AEB3-49F7-9707-394E19EADFE6}.Release|Any CPU.ActiveCfg = Release|Any CPU
		{7898E239-AEB3-49F7-9707-394E19EADFE6}.Release|Any CPU.Build.0 = Release|Any CPU
	EndGlobalSection
	GlobalSection(SolutionProperties) = preSolution
		HideSolutionNode = FALSE
	EndGlobalSection
	GlobalSection(ExtensibilityGlobals) = postSolution
		SolutionGuid = {B05AE01E-CEBE-4344-B3DA-646698293E91}
	EndGlobalSection
EndGlobal
```

### 修改後
```
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 16
VisualStudioVersion = 16.0.31129.286
MinimumVisualStudioVersion = 10.0.40219.1
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "ASP-MVC-example", "app\ASP-MVC-example.csproj", "{7898E239-AEB3-49F7-9707-394E19EADFE6}"
EndProject
Global
	GlobalSection(SolutionConfigurationPlatforms) = preSolution
		Debug|Any CPU = Debug|Any CPU
		Release|Any CPU = Release|Any CPU
	EndGlobalSection
	GlobalSection(ProjectConfigurationPlatforms) = postSolution
		{7898E239-AEB3-49F7-9707-394E19EADFE6}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
		{7898E239-AEB3-49F7-9707-394E19EADFE6}.Debug|Any CPU.Build.0 = Debug|Any CPU
		{7898E239-AEB3-49F7-9707-394E19EADFE6}.Release|Any CPU.ActiveCfg = Release|Any CPU
		{7898E239-AEB3-49F7-9707-394E19EADFE6}.Release|Any CPU.Build.0 = Release|Any CPU
	EndGlobalSection
	GlobalSection(SolutionProperties) = preSolution
		HideSolutionNode = FALSE
	EndGlobalSection
	GlobalSection(ExtensibilityGlobals) = postSolution
		SolutionGuid = {B05AE01E-CEBE-4344-B3DA-646698293E91}
	EndGlobalSection
EndGlobal
```

## 如果沒有Build Sonarqube會跳出甚麼錯誤
![](https://i.imgur.com/X5HUTPr.png)
```
09:29:30.676  The SonarScanner for MSBuild integration failed: SonarQube was unable to collect the required information about your projects.
Possible causes:
  1. The project has not been built - the project must be built in between the begin and end steps
  2. An unsupported version of MSBuild has been used to build the project. Currently MSBuild 14.0.25420.1 and higher are supported.
  3. The begin, build and end steps have not all been launched from the same folder
  4. None of the analyzed projects have a valid ProjectGuid and you have not used a solution (.sln)
09:29:30.676  Generation of the sonar-properties file failed. Unable to complete the analysis.
09:29:30.682  Post-processing failed. Exit code: 1
```


## 專案資料夾與檔案格式說明
檔案可按照需求做修改，此主要針對大部分專案規定來進行描述，針對不同專案可能會有些許變化，詳細使用方式請參考iiidevops教學說明文件。

| 型態 | 名稱 | 說明 | 路徑 |
| --- | --- | --- | --- |
| 資料夾 | app | 專案主要程式碼 | 根目錄 |
| 資料夾 | iiidevops | :warning: (不可更動)devops系統測試所需檔案 | 在根目錄 |
| 檔案 | pipeline_settings.json | :warning: (不可更動)devops系統測試所需檔案 | 在iiidevops資料夾內 |
| 檔案 | Dockerfile | (可調整)devops k8s環境部屬檔案 | 根目錄 |

## iiidevops
* `iiidevops`資料夾內`pipeline_settings.json`請勿更動。
* 若使用上有任何問題請至`https://www.iiidevops.org/`內的`聯絡方式`頁面做問題回報。

## Reference and FAQ

* [sonarscanner-for-msbuild/](https://docs.sonarqube.org/latest/analysis/scan/sonarscanner-for-msbuild/)
* [activity-diagram-beta](https://plantuml.com/zh/activity-diagram-beta)
:::info
**Find this document incomplete?** Leave a comment!
:::

###### tags: `iiidevops Templates README` `Sonarqube免費版` `Documentation`