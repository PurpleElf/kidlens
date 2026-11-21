"""SQLite 任务状态机（展示项目可降级为内存态）。

状态：pending -> processing -> done / failed

TODO:
- init_db()
- create_task(file_md5, path)
- update_task(task_id, status, extra)
- get_task(task_id)
"""
