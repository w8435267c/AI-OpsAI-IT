"""可在 Wagtail 模型加载期间导入的完成回调。"""


def publish_reviewed(workflow_state, user=None):
    from .services import _publish_reviewed

    return _publish_reviewed(workflow_state, user)
