from . import sonarqube_main

ui_route = ["Sonarqube"]

# --------------------- API router ---------------------


def router(api, add_resource):
    api.add_resource(sonarqube_main.SonarqubeHistory, "/sonarqube/<project_name>")
    api.add_resource(sonarqube_main.SonarqubeHistoryV2, "/v2/sonarqube/<project_name>")
    add_resource(sonarqube_main.SonarqubeHistoryV2, "public")
    api.add_resource(sonarqube_main.SonarqubeCodelen, "/sonarqube/<project_name>/codelen")
