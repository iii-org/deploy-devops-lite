from marshmallow import Schema, fields
from util import CommonBasicResponse


class SonarqubeHistoryData(Schema):
    link = fields.Str(required=True)
    history = fields.Dict(
        required=True,
        example={
            "1970-01-01T00:00:00+0000": {
                "coverage": "0.0",
                "duplicated_blocks": "0",
                "duplicated_lines_density": "0.0",
                "code_smells": "0",
                "bugs": "0",
                "vulnerabilities": "0",
                "alert_status": "OK",
                "security_hotspots": "0",
                "sqale_index": "0",
                "sqale_rating": "1.0",
                "reliability_rating": "1.0",
                "security_rating": "1.0",
                "branch": "master",
                "commit_id": "0db78e9",
                "issue_link": "http://issue_link",
            }
        },
    )


class SonarqubeHistoryResponse(CommonBasicResponse):
    data = fields.Nested(SonarqubeHistoryData, required=True)
