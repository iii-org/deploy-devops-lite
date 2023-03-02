from . import view


def template_url(api, add_resource):
    api.add_resource(view.TemplateFromProject, "/v2/template_from_project/<sint:project_id>")
    api.add_resource(view.TemplateFromProjectList, "/v2/template_from_project/template/list")
    api.add_resource(view.TemplateEdit, "/v2/template_from_project/template/<int:id>")
    add_resource(view.TemplateFromProject, "private")
    add_resource(view.TemplateFromProjectList, "private")
    add_resource(view.TemplateEdit, "private")
