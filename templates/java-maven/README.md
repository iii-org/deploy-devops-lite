# Java Spring Boot (Maven) - Testsite

## 如何增加Sonarqube掃描(用預設的QualiyGate)
在`app/pom.xml`的檔案內plugins新增如下段落後pipeline即可運行Sonarqube掃描，(此專案Sonarqube掃描包含Unit Test)  
在Spring專案的Sonarqube掃描會在openjdk11的環境執行(目前安裝僅支援到java11)，但是對Dockerfile編寫或是部署的網頁用任意Java版本都沒問題。
```
	<build>
		<plugins>
			<plugin>
          		<groupId>org.sonarsource.scanner.maven</groupId>
          		<artifactId>sonar-maven-plugin</artifactId>
          		<version>3.7.0.1746</version>
        	</plugin>
        	<plugin>
          		<groupId>org.jacoco</groupId>
          		<artifactId>jacoco-maven-plugin</artifactId>
          		<version>0.8.6</version>
        	</plugin>
		</plugins>
	</build>

	<profiles>
    <profile>
      <id>coverage</id>
      <activation>
        <activeByDefault>true</activeByDefault>
      </activation>
      <build>
        <plugins>
          <plugin>
            <groupId>org.jacoco</groupId>
            <artifactId>jacoco-maven-plugin</artifactId>
            <executions>
              <execution>
                <id>prepare-agent</id>
                <goals>
                  <goal>prepare-agent</goal>
                </goals>
              </execution>
            </executions>
          </plugin>
        </plugins>
      </build>
    </profile>
  </profiles>
```
### 如何關閉Sonarqube UnitTest
在`SonarScan`內修改特定段落內新增`-DskipTests`即可跳過unit Test，以下為跳過unit Test範例，跳過unit Test後則不會出現覆蓋率
```
echo '========== SonarQube(Maven) =========='
cd app && mvn install -DskipTests &&
mvn clean -DskipTests verify sonar:sonar -Dsonar.host.url=http://sonarqube-server-service.default:9000\
    -Dsonar.projectName=${CICD_GIT_REPO_NAME} -Dsonar.projectKey=${CICD_GIT_REPO_NAME}\
    -Dsonar.projectVersion=${CICD_GIT_BRANCH}:${CICD_GIT_COMMIT}\
	-Dsonar.log.level=DEBUG -Dsonar.qualitygate.wait=true -Dsonar.qualitygate.timeout=600\
	-Dsonar.login=$SONAR_TOKEN
```

### 程式覆蓋率教學
```
1.確認有哪些code需要Coverage
2.在test case新增test function
3.在該test function呼叫需覆蓋的功能function
4.可透過IDE的Coverage As junit test確認覆蓋的地方

```
### jacoco Coverage 參考說明
https://dzone.com/articles/reporting-code-coverage-using-maven-and-jacoco-plu
https://blog.miniasp.com/post/2021/08/11/Spring-Boot-Maven-JaCoCo-Test-Coverage-Report-in-VSCode

若要設定其他額外的細節也可寫在`app/pom.xml`，例如排除特定資料夾(與程式碼無關的)、指定的QualityGate、Rule等等  
相關可用額外參數說明可參考[sonarscanner-for-maven](https://docs.sonarqube.org/latest/analysis/scan/sonarscanner-for-maven/)

## 專案資料夾與檔案格式說明

| 型態 | 名稱 | 說明 | 路徑 |
| --- | --- | --- | --- |
| 資料夾 | app | 專案主要程式碼 | 根目錄 |
| 檔案 | .rancher-pipeline.yml | :warning: (不可更動)devops系統所需檔案 | 根目錄 |
| 檔案 | Dockerfile | (可調整)devops k8s環境部署檔案 | 根目錄 |
| 檔案 | README.md | 本說明文件 | 根目錄 |
| 檔案 | SonarScan | (可調整)整合SonarQube執行檔案 | 根目錄 |
| 資料夾 | app | 專案主要程式碼 | 根目錄 |
| 資料夾 | iiidevops | :warning: devops系統測試所需檔案 | 根目錄 |
| 檔案 | app.env | (可調整)提供實證環境之環境變數(env)定義檔 | iiidevops |
| 檔案 | app.env.develop | (可調整)提供特定分支(develop)實證環境之環境變數(env)定義檔 | iiidevops |
| 檔案 | pipeline_settings.json | :warning: (不可更動)devops系統測試所需檔案 | iiidevops |
| 資料夾 | bin | :warning: devops系統測試所需執行檔案 | iiidevops |
| 資料夾 | postman | :warning: devops系統整合postman測試所需執行檔案 | iiidevops |
| 檔案 | postman_collection.json | (可調整)devops newman部署測試檔案 | iiidevops/postman |
| 檔案 | postman_environment.json | (可調整)devops newman部署測試檔案 | iiidevops/postman |
| 資料夾 | sideex | :warning: devops系統測整合sideex試所需執行檔案 | iiidevops |
| 檔案 | Global Variables.json | (可調整)devops sideex部署測試檔案 | iiidevops/sideex |
| 檔案 | sideex.json | (可調整)devops sideex部署測試檔案 | iiidevops/sideex |

## iiidevops
* 專案內`.rancher-pipeline.yml`是 pipeline 的定義檔, 除非對 yml 與 rancher pipeline 的語法有足夠的了解, 否則建議不要隨意對內容進行更動, 有可能會造成 pipeline 無法正常運作
* 目前範本是依照 tomcat 預設服務的定義 port:8080 設定服務 port 號，如果您的程式需要更改使用其他 port 號 , 請將 `.rancher-pipeline.yml` 內所有 web.port: 所定義的 8080 改成您實際需要的 port 號。
* `iiidevops`資料夾
  * `postman`資料夾內是devops整合API測試工具(postman)的自動測試檔案放置目錄，devops系統會以`postman`資料夾內 postman_collection.json 的檔案內容進行自動測試
  * `sideex`資料夾內則是devops整合Web測試工具(sideex)的自動測試檔案放置目錄，devops系統會以`sideex`資料夾內 sideex 匯出的 json 檔案內容進行自動測試
* `Dockerfile`內加上前置dockerhub，是為使image能透過本地端harbor擔任Image Proxy的方式抓取Docker Hub上的Images，增加不同專案抓取相同 Image 的效率
