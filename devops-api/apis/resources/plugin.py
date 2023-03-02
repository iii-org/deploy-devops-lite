from flask_jwt_extended import jwt_required
from flask_restful import Resource, reqparse

import plugins
import util as util
from resources import role, project

invalid_plugin_name = "Unable get plugin software"


class Plugins(Resource):
    @jwt_required()
    def get(self):
        return util.success(plugins.list_plugins())


class Plugin(Resource):
    @jwt_required()
    def get(self, plugin_name):
        role.require_admin("Only admins can get plugin software.")
        return util.success(plugins.get_plugin_config(plugin_name))

    @jwt_required()
    def patch(self, plugin_name):
        role.require_admin("Only admins can modify plugin software.")
        parser = reqparse.RequestParser()
        parser.add_argument("arguments", type=dict)
        parser.add_argument("disabled", type=bool)
        args = parser.parse_args()
        plugins.update_plugin_config(plugin_name, args)
        return util.respond(204)
