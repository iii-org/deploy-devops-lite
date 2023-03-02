from typing import Any, Optional
from xmlrpc.client import Boolean

from flask_jwt_extended import get_jwt_identity
from sqlalchemy.engine import Row

from model import PluginSoftware, UIRouteData, db

key_return_json = ["parameter"]
MAX_DEPTH: int = 50


def get_plugin_software(simple=False) -> list[dict[str, Any]]:
    plugins: list[Row] = PluginSoftware.query.with_entities(
        PluginSoftware.id, PluginSoftware.name, PluginSoftware.disabled
    ).all()
    if simple:
        disable_list = []
        if PluginSoftware.query.filter_by(disabled=True).first():
            rows = PluginSoftware.query.filter_by(disabled=True).all()
            disable_list = [row.name for row in rows]
        output: list[dict[str, Any]] = [
            {"id": plugin["id"], "name": plugin["name"], "disabled": plugin["disabled"]}
            for plugin in plugins
            if plugin and plugin["name"] not in disable_list
        ]
    else:
        output: list[dict[str, Any]] = [
            {"id": plugin["id"], "name": plugin["name"], "disabled": plugin["disabled"]} for plugin in plugins
        ]
    return output


def get_error_route() -> dict[str, ...]:
    error_route: UIRouteData = UIRouteData.query.filter_by(role="").first()
    return error_route.ui_route


def display_by_permission() -> list[dict[str, ...]]:
    role_name: str = get_jwt_identity()["role_name"]

    route_list: list[dict[str, ...]] = []
    node: UIRouteData = UIRouteData.query.filter_by(parent=0, role=role_name, old_brother=0).first()
    route_list.append(get_ui_route(node, role_name))

    while node.next_node:
        node: UIRouteData = node.next_node
        route_list.append(get_ui_route(node, role_name))

    route_list.append(get_error_route())
    return route_list


def get_ui_route(node: UIRouteData, role_name: str) -> dict[str, ...]:
    route: dict[str, ...] = node.ui_route

    if node.children_nodes:
        child_routes: list[dict[str, ...]] = []
        child: UIRouteData = node.children_nodes[0].first_node
        child_routes.append(get_ui_route(child, role_name))

        depth: int = 0
        while child.next_node:
            depth += 1

            if depth > MAX_DEPTH:
                break

            child: UIRouteData = child.next_node
            child_routes.append(get_ui_route(child, role_name))

        route["children"] = child_routes

    return route


def move_node(original: UIRouteData, move_to: Optional[UIRouteData]) -> None:
    """
    將 original 移動到 move_to 的位置

    :param original: 原始節點
    :param move_to: 移動到的節點位置
    :return:
    """
    _prev: UIRouteData = original.prev_node
    _next: UIRouteData = original.next_node

    # Step 1: Update next node's link
    if _next:
        _next.prev_node = _prev

    # Step 2: Check if the move_to is not None, if None, means move to the end
    if move_to:
        # Step 2.1: Move node to the new position
        original.prev_node = move_to.prev_node

        # Step 2.2: Add move_to node position point to the original node
        move_to.prev_node = original
    else:
        # Step 2.3: If move_to is None, means move to the end
        original.prev_node = _next.last_node


def update_node_index(node: UIRouteData, index: int) -> None:
    """
    將 node 移動到指定 index 的位置

    :param node: 要移動的 node
    :param index: 要移動到的 index
    :return:
    """
    current_index: int = node.node_index

    # Index value check
    if index < 1:
        raise ValueError("Index must be greater than 0")
    if index > node.node_counts:
        raise ValueError("Index must be less than or equal to node counts")

    # Do nothing if index is the same
    if index == current_index:
        return

    # Calculate the move distance
    diff: int = current_index - index

    if diff > 0:
        _move: UIRouteData = node
        for _ in range(diff):
            _move = _move.prev_node

    elif diff < 0:
        _move: UIRouteData = node
        for _ in range(abs(diff) + 1):
            _move = _move.next_node
    else:
        raise ValueError("diff is neither greater than 0 nor less than 0")

    # Move node to the new position
    move_node(node, _move)

    # Commit the change to database
    db.session.commit()


def print_list(node: UIRouteData) -> None:
    """
    除錯用 print 整條 UI Route List 的連結資訊。

    :param node: 想查看的 node
    :return:
    """
    checker: UIRouteData = node.first_node
    print("(head)", end=" ")

    if not checker.prev_node:
        print("<", end="")
    print("=>", end=" ")
    print(checker.id, end=" ")

    while checker.next_node:
        next_node = checker.next_node

        if next_node.prev_node == checker:
            print("<", end="")
        print("=>", end=" ")
        print(next_node.id, end=" ")

        checker = next_node

    if not checker.next_node:
        print("<=> (tail)")


def update_plugin_hidden(plugin_name: str, hidden: Boolean) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    plugin_name_mapping = {
        "checkmarx": "Checkmarx",
        "cmas": "Cmas",
        "postman": "Postmans",
        "webinspect": "Webinspects",
        "zap": "Zap",
        "sbom": "Sbom",
        "sonarqube": "Sonarqube",
        "sideex": "Sideex",
        "excalidraw": "Whiteboard",
    }
    plugin_name = plugin_name_mapping.get(plugin_name)
    if plugin_name is None:
        return
    ui_route_obj_list = UIRouteData.query.filter_by(name=plugin_name).all()
    for ui_route_obj in ui_route_obj_list:
        ui_route_value = ui_route_obj.ui_route
        ui_route_value["hidden"] = hidden
        ui_route_obj.ui_route = ui_route_value
        flag_modified(ui_route_obj, "ui_route")
        db.session.commit()
