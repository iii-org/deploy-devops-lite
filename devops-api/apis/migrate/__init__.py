import os
import config
import model
from model import db, UIRouteData, PluginSoftware, SystemParameter
from resources.logger import logger
from migrate.upgrade_function.ui_route_upgrade import ui_route_first_version
from migrate.upgrade_function import v1_22_upgrade
from resources.router import update_plugin_hidden

# Each time you add a migration, add a version code here.

VERSIONS = [
    "1.22.0.1",
    "1.22.0.2",
    "1.22.0.3",
    "1.22.0.4",
    "1.22.0.5",
    "1.23.0.1",
    "1.23.0.2",
    "1.24.0.1",
    "1.24.0.2",
    "1.25.0.1",
    "1.25.0.3",
    "1.25.0.4",
    "1.25.0.5",
    "1.25.0.6",
    "1.25.0.7",
    "1.26.0.1",
    "1.26.0.2",
]
ONLY_UPDATE_DB_MODELS = [
    "1.22.0.1",
    "1.22.0.2",
    "1.22.0.3",
    "1.23.0.2",
    "1.24.0.1",
    "1.24.0.2",
    "1.25.0.3",
    "1.25.0.4",
    "1.25.0.5",
    "1.25.0.6",
    "1.25.0.7",
    "1.26.0.1",
]


def upgrade(version):
    """
    Upgraded function need to check it can handle multi calls situation,
    just in case multi pods will call it several times.
    ex. Insert data need to check data has already existed or not.
    """
    if version in ONLY_UPDATE_DB_MODELS:
        alembic_upgrade()
    elif version == "1.22.0.4":
        recreate_ui_route()
    elif version == "1.22.0.5":
        if SystemParameter.query.filter_by(name="upload_file_size").first() is None:
            row = SystemParameter(name="upload_file_size", value={"upload_file_size": 5}, active=True)
            db.session.add(row)
            db.session.commit()
    elif version == "1.23.0.1":
        recreate_ui_route()
    elif version == "1.25.0.1":
        model.NotificationMessage.query.filter_by(alert_service_id=303, close=False).delete()
        db.session.commit()
    elif version == "1.26.0.2":
        recreate_ui_route()


def recreate_ui_route():
    UIRouteData.query.delete()
    ui_route_first_version()

    for plugin_software in PluginSoftware.query.all():
        update_plugin_hidden(plugin_software.name, plugin_software.disabled)


def init():
    latest_api_version, deploy_version = VERSIONS[-1], config.get("DEPLOY_VERSION")
    logger.info(f"Creat NexusVersion, api_version={latest_api_version}, deploy_version={deploy_version}")
    new = model.NexusVersion(api_version=latest_api_version, deploy_version=deploy_version)
    db.session.add(new)
    db.session.commit()

    # For the new server, need to add some default value
    # 1.22
    logger.info("Start insert default value in v1.22")
    v1_22_upgrade.insert_default_value_in_lock()
    logger.info("Insert default value in Lock done")
    v1_22_upgrade.insert_default_value_in_system_parameter()
    logger.info("Insert default value in SystemParameter done")
    ui_route_first_version()
    logger.info("Insert default value in UiRouteData done")


def needs_upgrade(current, target):
    r = current.split(".")
    c = target.split(".")
    for i in range(4):
        if int(c[i]) > int(r[i]):
            return True
        elif int(c[i]) < int(r[i]):
            return False
    return False


def alembic_upgrade():
    # Rewrite ini file
    with open("alembic.ini", "w") as ini:
        with open("_alembic.ini", "r") as template:
            for line in template:
                if line.startswith("sqlalchemy.url"):
                    ini.write("sqlalchemy.url = {0}\n".format(config.get("SQLALCHEMY_DATABASE_URI")))
                else:
                    ini.write(line)
    os_ret = os.system("alembic upgrade head")
    if os_ret != 0:
        raise RuntimeError("Alembic has error, process stop.")


def current_version():
    if db.engine.has_table(model.NexusVersion.__table__.name):
        # Cannot write in ORM here since NexusVersion table itself may be modified
        result = db.engine.execute("SELECT api_version FROM nexus_version")
        row = result.fetchone()
        result.close()
        if row is not None:
            current = row["api_version"]
        else:
            # This is a new server, so NexusVersion table scheme should match the ORM
            current = "1.22.9.9"
            new = model.NexusVersion(api_version=current)
            db.session.add(new)
            db.session.commit()
    else:
        # Backward compatibility
        if os.path.exists(".api_version"):
            with open(".api_version", "r") as f:
                current = f.read()
        else:
            current = "1.22.9.9"
    return current


def run():
    current = current_version()
    try:
        for version in VERSIONS:
            if needs_upgrade(current, version):
                current, deploy_version = version, config.get("DEPLOY_VERSION")
                row = model.NexusVersion.query.first()
                if row.deploy_version != deploy_version:
                    row.deploy_version = deploy_version
                row.api_version = current
                db.session.commit()
                logger.info("Upgrade to {0}".format(version))
                upgrade(version)
    except Exception as e:
        raise e
