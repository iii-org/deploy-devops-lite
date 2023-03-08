# Java 8 Gradle 5.6 離線版本建制教學
1. 範本裡提供的 gradle 5.6 和 jdk8 的版本

## 如何修改範本設定
### 1. Jacoco
可以透過修改reportsDir以及xml.destination file來修改jacoco報告(.xml)產生路徑(一般不建議修改)．gradle在編譯時，會在build.gradle的路徑中產生/build資料夾，並將編譯檔和jacoco產出的報告放在/build中．

```
jacoco {
    toolVersion = "0.8.5"
    reportsDir = file("$buildDir/reports")
}

jacocoTestReport {
    dependsOn test
   // build.dependsOn jacocoTestReport
    reports {
        xml.enabled true
        xml.destination file("$buildDir/reports/jacoco.xml")

     }
}
```
## 2. Artifactory (Jfrog)
本範例中，會將編譯完成的.jar上傳到指定的Artifactor(即Upload)，同時也可以從Artifactory中取得相關套件(.jar)並引用至專案中(即Download)．若不使用Artifactory，則相關片段程式皆可註解
### 2.1 Upload
2.1.1 上傳前可先調整上傳至Artifactory的結構和版本，參考以下片段
```
 group "org.example"
  version '1.1'
```
2.1.2 在離線環境中，須架設私人Artifactory server，因此需修改以下片段將編譯後產生的.jar檔傳送至私人Artifactory
contextUrl: 表示要傳送的Artifactory的位置． repoKey: 為Artifactory上repo的名子(建立server後，須先透過Jfrog的UI建立repo，否則程式會因為找不到repoKey而報錯) username, password: 即為Artifactory的帳號密碼．
```
artifactory {
    contextUrl = 'http://10.20.2.205:8081/artifactory/'
    publish {
        repository {
            repoKey = 'gradle_repo' // The Artifactory repository key to publish to
            username = "admin" // The publisher user name
            password = "password" // The publisher password
        }
        defaults {
            // Reference to Gradle publications defined in the build script.
            // This is how we tell the Artifactory Plugin which artifacts should be
            // published to Artifactory.
            publications('mavenJava')
            publishArtifacts = true
            // Properties to be attached to the published artifacts.
            properties = ['qa.level': 'basic', 'dev.team' : 'core']
            // Publish generated POM files to Artifactory (true by default)
            publishPom = true
        }
    }
}
```

### 2.2 Download (dependencies)
針對不同專案，可透過修改以下指令至Artifactory中找到相關.jar．

2.2.1 在repositories中找到url, username, password，修改為私人Artifactory路徑和登入資訊．
以下片段代表的意義為專案在build時，會依序去搜尋不同的repo底下的相關套件．Jcenter()以及mavenLocal()分別會至預設的路徑中尋找套件．

```
repositories {
    // Use jcenter for resolving dependencies.
    // You can declare any Maven/Ivy/file repository here.
    // mavenLocal(): deafult repo path : /User/.m2/repository
    // jcenter():    deafult repo path : /User/.gradle/caches/modules-2/files-2.1 

    maven {
       url = "http://10.20.205:8081/artifactory/gradle_repo"
       credentials{
            username = "admin"
            password = "password"
       }
    }
    jcenter()
    mavenLocal()
}
dependencies {
    // This dependency is used by the application.
    implementation 'com.google.guava:guava:28.0-jre'

    // this is dependency from Artifactory( Jfrog)
    implementation group: 'org.example', name: 'app', version: '1.1'
    
    // Use JUnit test framework
    testImplementation 'junit:junit:4.12'
}
```
### 3. Sonarqube
3.1 若有額外建立sonarqube server則可修改以下片段，將報告送至指定的server．反之，若是運行在III devops平台，以下片段則可直接註解（devops平台會自動建立sonarqube服務）
若未修改預設jacoco.xml檔產出路徑，則以下片段只需修改host.url, login以及password即可．

```
sonarqube {
    properties {
        property "sonar.java.coveragePlugin", "jacoco"
        property "sonar.host.url", "http://10.20.2.205:6004"
        property "sonar.coverage.jacoco.xmlReportPath", "$buildDir/reports/jacoco.xml"
        property "sonar.login", "admin"
        property "sonar.password", "IIIdevops123!"
    }
}
```

### 4. 透過Dockerfile建立環境
4.1 dockerfile建置環境
Dockfile僅提供java JDK8和gradle 5.6，當build完Dockerfile後須在有線網路的情況下，重新build一次java範本，便可將範本所需用到的資源下載到images中
完成後將範本掛載到容器內，至~/app中，執行以下指令即可跑build、jacoco、sonarqube、上傳和下載Artifactory資源到專案內(可依據需求調整帶入參數)
```
$ ./gradlew clean build jacocoTestReport sonarqube artifactoryPublish
```
## 如何增加Sonarqube掃描(用預設的QualiyGate)
在`app/build.gradle`的檔案內plugins新增`id "org.sonarqube" version "3.1.1"`後pipeline即可運行Sonarqube掃描
1. 確認您專案的 gradle 版本，並將它更新至專案的 Dockerfile
2. 若欲使用SonarQube，則請將下列文字新增至 build.gradle 的檔案裡。
```
plugins {
	id 'org.springframework.boot' version '2.3.3.RELEASE'
	id 'io.spring.dependency-management' version '1.0.8.RELEASE'
	id 'java'
	id "org.sonarqube" version "3.1.1"
}
```
2.1 填入位置可參考下列圖示所示

![](https://i.imgur.com/FZL7uD3.png)

若要設定其他額外的細節也可寫在`app/build.gradle`，例如排除特定資料夾(與程式碼無關的)、指定的QualityGate、Rule等等  
相關可用額外參數說明可參考[sonarscanner-for-gradle](https://docs.sonarqube.org/latest/analysis/scan/sonarscanner-for-gradle/)

### 如何關閉Sonarqube UnitTest
在`SonarScan`內修改特定段落內新增`-x test`即可跳過unit Test，以下為跳過unit Test範例，跳過unit Test後則不會出現覆蓋率
```
echo '========== SonarQube(Gradle) =========='
cd app && chmod -R 777 .
./gradlew -Dsonar.host.url=http://sonarqube-server-service.default:9000\
    -Dsonar.projectKey=${CICD_GIT_REPO_NAME} -Dsonar.projectName=${CICD_GIT_REPO_NAME}\
	-Dsonar.projectVersion=${CICD_GIT_BRANCH}:${CICD_GIT_COMMIT}\
    -Dsonar.log.level=DEBUG -Dsonar.qualitygate.wait=true -Dsonar.qualitygate.timeout=600\
    -Dsonar.login=$SONAR_TOKEN -x test jacocoTestReport sonarqube
```
### jacoco Coverage 參考說明
https://dzone.com/articles/reporting-code-coverage-using-maven-and-jacoco-plu
https://blog.miniasp.com/post/2021/08/11/Spring-Boot-Maven-JaCoCo-Test-Coverage-Report-in-VSCode

## 專案資料夾與檔案格式說明

| 型態 | 名稱 | 說明 | 路徑 |
| --- | --- | --- | --- |
| 檔案 | .rancher-pipeline.yml | :warning: (不可更動)devops系統所需檔案 | 根目錄 |
| 檔案 | README.md | 本說明文件 | 根目錄 |
| 檔案 | Dockerfile | (可調整)devops k8s環境部署檔案 | 根目錄 |
| 檔案 | SonarScan | (可調整)整合SonarQube執行檔案 | 根目錄 |
| 資料夾 | app | 專案主要程式碼 | 根目錄 |
| 資料夾 | iiidevops | :warning: devops系統測試所需檔案 | 根目錄 |
| 檔案 | app.env | (可調整)提供實證環境之環境變數(env)定義檔 | iiidevops |
| 檔案 | app.env.develop | (可調整)提供特定分支(develop)實證環境之環境變數(env)定義檔 | iiidevops |
| 檔案 | pipeline_settings.json | :warning: (不可更動)devops系統測試所需檔案 | iiidevops |
| 資料夾 | bin | :warning: devops系統測試所需執行檔案 | iiidevops |


## iiidevops
* 專案內`.rancher-pipeline.yml`是 pipeline 的定義檔, 除非對 yml 與 rancher pipeline 的語法有足夠的了解, 否則建議不要隨意對內容進行更動, 有可能會造成 pipeline 無法正常運作
* 目前範本是依照 tomcat 預設服務的定義 port:8080 設定服務 port 號，如果您的程式需要更改使用其他 port 號 , 請將 `.rancher-pipeline.yml` 內所有 web.port: 所定義的 8080 改成您實際需要的 port 號。
* `iiidevops`資料夾
  * `postman`資料夾內是devops整合API測試工具(postman)的自動測試檔案放置目錄，devops系統會以`postman`資料夾內 postman_collection.json 的檔案內容進行自動測試
  * `sideex`資料夾內則是devops整合Web測試工具(sideex)的自動測試檔案放置目錄，devops系統會以`sideex`資料夾內 sideex 匯出的 json 檔案內容進行自動測試
* `Dockerfile`內加上前置dockerhub，是為使image能透過本地端harbor擔任Image Proxy的方式抓取Docker Hub上的Images，增加不同專案抓取相同 Image 的效率
