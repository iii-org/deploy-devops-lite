from marshmallow import Schema, fields
from util import CommonBasicResponse


class CreateTemplateFormProjectScheme(Schema):
    name = fields.Str(required=False, description="範本名稱", example="Default")
    description = fields.Str(
        required=False,
        description="範本描述",
        example=" <a class='el-link el-link--primary' \
    href='https://github.com/iiidevops-templates/default-dev/blob/master/README.md' \
    target='_blank'>簡易網頁說明</a><hr size=1 />  <li><b>v1.16</b>:SonarQube均改用 helm chart 架構, \
    Postman POD 名稱加上 git hash  <li><b>v1.15</b>:支援Web部署上傳檔案大小設定(預設1MB)  \
    <li><b>v1.13</b>:支援 SonarQube 8.9 功能與可指定 harbor.host 功能, 整合 Android APK 黑箱掃描 CMAS 工具",
    )
