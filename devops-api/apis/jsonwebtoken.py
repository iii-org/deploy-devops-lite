from flask_jwt_extended import JWTManager
from resources.apiError import build

jsonwebtoken = JWTManager()


@jsonwebtoken.expired_token_loader
def my_expired_token_callback(jwt_header, jwt_payload):
    return build(3005, jwt_header), 401


@jsonwebtoken.invalid_token_loader
def custom_error(jwt_header):
    return build(3006, jwt_header), 422
