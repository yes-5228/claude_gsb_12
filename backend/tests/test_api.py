"""接口级测试：覆盖台账、巡查、问题整改与统计看板。"""

from datetime import datetime, timedelta

from tests.conftest import full_items


def test_health_and_dictionaries(client):
    assert client.get("/health").json()["status"] == "ok"
    payload = client.get("/api/v1/meta/dictionaries").json()
    assert "待整改" in payload["issue_status"]
    assert len(payload["inspection_check_items"]) == 8
    assert payload["issue_transitions"]["待整改"] == ["整改中", "已关闭"]


def test_restroom_crud_and_delete_guard(client, restroom):
    assert restroom["code"].startswith("WC-")

    listed = client.get("/api/v1/restrooms", params={"district": "测试区"}).json()
    assert listed["meta"]["total"] >= 1

    detail = client.get(f"/api/v1/restrooms/{restroom['id']}").json()
    assert detail["inspection_count"] == 0
    assert detail["open_issue_count"] == 0

    updated = client.patch(
        f"/api/v1/restrooms/{restroom['id']}", json={"status": "维修中", "manager": "新责任人"}
    ).json()
    assert updated["status"] == "维修中"
    assert updated["manager"] == "新责任人"

    # 存在关联数据时不允许直接删除
    client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "测试巡查员",
            "shift": "早班",
            "items": full_items(9),
        },
    )
    blocked = client.delete(f"/api/v1/restrooms/{restroom['id']}")
    assert blocked.status_code == 409

    ok = client.delete(f"/api/v1/restrooms/{restroom['id']}", params={"force": "true"})
    assert ok.status_code == 200
    assert client.get(f"/api/v1/restrooms/{restroom['id']}").status_code == 404


def test_inspection_scoring_and_filter(client, restroom):
    good = client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "李巡查",
            "shift": "中班",
            "items": full_items(9),
            "remark": "整体良好",
        },
    ).json()
    assert good["score"] == 90.0
    assert good["grade"] == "优秀"
    assert good["result"] == "正常"

    bad_items = full_items(9)
    bad_items[0]["score"] = 3
    bad_items[0]["remark"] = "地面污渍"
    bad = client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "李巡查",
            "shift": "晚班",
            "items": bad_items,
        },
    ).json()
    assert bad["result"] == "发现问题"
    assert bad["score"] < 90

    filtered = client.get(
        "/api/v1/inspections", params={"result": "发现问题", "restroom_id": restroom["id"]}
    ).json()
    assert filtered["meta"]["total"] == 1
    assert filtered["items"][0]["id"] == bad["id"]
    assert filtered["items"][0]["restroom"]["name"] == restroom["name"]

    today = datetime.now().date().isoformat()
    ranged = client.get(
        "/api/v1/inspections", params={"date_from": today, "date_to": today}
    ).json()
    assert ranged["meta"]["total"] == 2

    duplicate = full_items(5) + [{"name": "地面与台阶清洁", "score": 4}]
    rejected = client.post(
        "/api/v1/inspections",
        json={"restroom_id": restroom["id"], "inspector": "李巡查", "items": duplicate},
    )
    assert rejected.status_code == 400

    empty = client.post(
        "/api/v1/inspections",
        json={"restroom_id": restroom["id"], "inspector": "李巡查", "items": []},
    )
    assert empty.status_code == 422


def test_issue_lifecycle(client, restroom):
    inspection = client.post(
        "/api/v1/inspections",
        json={
            "restroom_id": restroom["id"],
            "inspector": "王巡查",
            "items": full_items(4),
        },
    ).json()

    issue = client.post(
        "/api/v1/issues",
        json={
            "restroom_id": restroom["id"],
            "inspection_id": inspection["id"],
            "title": "地面污渍未清理",
            "description": "巡查发现地面有明显污渍",
            "category": "保洁不到位",
            "severity": "严重",
            "reporter": "王巡查",
            "assignee": "保洁班组",
            "deadline": (datetime.now() - timedelta(days=1)).isoformat(),
        },
    ).json()
    assert issue["status"] == "待整改"
    assert len(issue["records"]) == 1
    assert issue["records"][0]["action"] == "上报问题"

    # 越级流转被拒绝：待整改 -> 已完成
    invalid = client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "已完成", "operator": "值班长"},
    )
    assert invalid.status_code == 400
    assert "不允许流转" in invalid.json()["detail"]

    options = client.get(f"/api/v1/issues/{issue['id']}/transitions").json()
    assert {option["status"] for option in options} == {"整改中", "已关闭"}

    processing = client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "整改中", "operator": "保洁班组张伟", "remark": "已安排清洗"},
    ).json()
    assert processing["status"] == "整改中"
    assert processing["assignee"] == "保洁班组"

    reviewing = client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "待验收", "operator": "保洁班组张伟", "remark": "整改完成待验收"},
    ).json()
    assert reviewing["status"] == "待验收"

    # 验收驳回回到整改中
    rejected = client.post(
        f"/api/v1/issues/{issue['id']}/transitions",
        json={"to_status": "整改中", "operator": "王巡查", "remark": "角落仍有残留"},
    ).json()
    assert rejected["status"] == "整改中"
    assert rejected["records"][-1]["action"] == "验收驳回"

    for target in ("待验收", "已完成", "已关闭"):
        payload = {"to_status": target, "operator": "值班长", "remark": f"流转到{target}"}
        response = client.post(f"/api/v1/issues/{issue['id']}/transitions", json=payload)
        assert response.status_code == 200, response.text
    final = response.json()
    assert final["status"] == "已关闭"
    assert final["closed_at"] is not None
    assert [record["to_status"] for record in final["records"]][-1] == "已关闭"

    closed_record = client.post(
        f"/api/v1/issues/{issue['id']}/records",
        json={"action": "整改进度", "operator": "值班长", "remark": "补充说明"},
    )
    assert closed_record.status_code == 400

    overdue = client.get("/api/v1/issues", params={"overdue": "true"}).json()
    assert overdue["meta"]["total"] == 0

    # 巡查记录可反查关联问题数量
    detail = client.get(f"/api/v1/inspections/{inspection['id']}").json()
    assert detail["issue_count"] == 1


def test_issue_requires_matching_restroom(client, restroom):
    other = client.post(
        "/api/v1/restrooms",
        json={"name": "另一座公厕", "district": "测试区", "address": "测试路 2 号"},
    ).json()
    inspection = client.post(
        "/api/v1/inspections",
        json={"restroom_id": other["id"], "inspector": "周巡查", "items": full_items(9)},
    ).json()
    mismatch = client.post(
        "/api/v1/issues",
        json={
            "restroom_id": restroom["id"],
            "inspection_id": inspection["id"],
            "title": "关联错误",
        },
    )
    assert mismatch.status_code == 400
    assert "不一致" in mismatch.json()["detail"]


def test_dashboard_stats(client, restroom):
    payload = client.get("/api/v1/stats/dashboard", params={"trend_days": 7}).json()
    overview = payload["overview"]
    assert overview["restroom_total"] >= 1
    assert overview["inspection_total"] >= 1
    assert len(payload["inspection_trend"]) == 7
    assert {item["name"] for item in payload["issue_by_status"]} == {
        "待整改",
        "整改中",
        "待验收",
        "已完成",
        "已关闭",
    }
    assert payload["top_restrooms"]
    assert "rectification_rate" in overview


def _create_restroom(client, name, district, grade):
    response = client.post(
        "/api/v1/restrooms",
        json={"name": name, "district": district, "address": f"{district}路", "grade": grade},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_list_grade_filter_uses_restroom_grade(client):
    """巡查与问题列表都支持按公厕等级（一类/二类/三类）过滤。"""
    first = _create_restroom(client, "口径一类公厕", "口径东区", "一类")
    second = _create_restroom(client, "口径二类公厕", "口径西区", "二类")

    for rid in (first["id"], second["id"]):
        client.post(
            "/api/v1/inspections",
            json={"restroom_id": rid, "inspector": "口径巡查", "items": full_items(8)},
        )
    client.post(
        "/api/v1/issues",
        json={"restroom_id": first["id"], "title": "一类公厕问题", "category": "其他"},
    )
    client.post(
        "/api/v1/issues",
        json={"restroom_id": second["id"], "title": "二类公厕问题", "category": "其他"},
    )

    inspections = client.get("/api/v1/inspections", params={"grade": "一类"}).json()
    inspection_ids = {item["restroom_id"] for item in inspections["items"]}
    assert first["id"] in inspection_ids
    assert second["id"] not in inspection_ids

    issues = client.get("/api/v1/issues", params={"grade": "二类"}).json()
    issue_ids = {item["restroom_id"] for item in issues["items"]}
    assert second["id"] in issue_ids
    assert first["id"] not in issue_ids


def test_scope_consistency_across_list_group_dashboard(client):
    """同一筛选下，列表、分组汇总、看板三处的巡查/问题数量必须一致。"""
    first = _create_restroom(client, "对表一类公厕", "对表区", "一类")
    client.post(
        "/api/v1/inspections",
        json={"restroom_id": first["id"], "inspector": "对表巡查", "items": full_items(9)},
    )
    client.post(
        "/api/v1/issues",
        json={"restroom_id": first["id"], "title": "对表问题", "category": "设施损坏"},
    )

    # 巡查：列表总数 == 分组汇总 total == 看板 inspection_total
    list_total = client.get("/api/v1/inspections", params={"grade": "一类"}).json()["meta"]["total"]
    summary = client.get("/api/v1/stats/inspections/summary", params={"grade": "一类"}).json()
    dashboard = client.get("/api/v1/stats/dashboard", params={"grade": "一类"}).json()
    assert summary["total"] == list_total
    assert sum(item["value"] for item in summary["by_grade"]) == list_total
    grade_bucket = {item["name"]: item["value"] for item in summary["by_grade"]}
    assert grade_bucket["一类"] == list_total
    assert dashboard["overview"]["inspection_total"] == list_total
    assert dashboard["scope"] == {"district": None, "grade": "一类"}

    # 区域维度分组里该等级只有一类公厕
    grade_dim = {item["name"]: item for item in dashboard["by_grade"]}
    assert "一类" in grade_dim
    assert grade_dim["一类"]["restroom_count"] >= 1

    # 问题：按区域收敛后列表总数 == 分组汇总 total == 看板 issue_total
    issue_list_total = client.get("/api/v1/issues", params={"district": "对表区"}).json()["meta"][
        "total"
    ]
    issue_summary = client.get(
        "/api/v1/stats/issues/summary", params={"district": "对表区"}
    ).json()
    issue_dashboard = client.get("/api/v1/stats/dashboard", params={"district": "对表区"}).json()
    assert issue_summary["total"] == issue_list_total
    assert issue_dashboard["overview"]["issue_total"] == issue_list_total
    district_dim = {item["name"]: item for item in issue_dashboard["by_district"]}
    assert "对表区" in district_dim
    assert district_dim["对表区"]["issue_total"] == issue_list_total

    # 区域 + 等级同时收敛
    both = client.get(
        "/api/v1/stats/dashboard", params={"district": "对表区", "grade": "一类"}
    ).json()
    assert both["scope"] == {"district": "对表区", "grade": "一类"}
    assert both["overview"]["inspection_total"] == 1
    assert both["overview"]["issue_total"] == 1


def test_summary_without_scope_still_groups(client, restroom):
    """无任何筛选时分组汇总也必须完整（whereclause 为空不能吞掉分组）。"""
    client.post(
        "/api/v1/inspections",
        json={"restroom_id": restroom["id"], "inspector": "全量巡查", "items": full_items(7)},
    )
    client.post(
        "/api/v1/issues",
        json={"restroom_id": restroom["id"], "title": "全量问题"},
    )
    inspection_summary = client.get("/api/v1/stats/inspections/summary").json()
    assert inspection_summary["by_district"]
    assert inspection_summary["by_grade"]
    assert sum(item["value"] for item in inspection_summary["by_grade"]) == inspection_summary["total"]

    issue_summary = client.get("/api/v1/stats/issues/summary").json()
    assert issue_summary["by_district"]
    assert sum(item["value"] for item in issue_summary["by_district"]) == issue_summary["total"]


def test_methodology_explains_caliber(client):
    payload = client.get("/api/v1/stats/methodology").json()
    assert payload["grade_options"] == ["一类", "二类", "三类"]
    assert set(payload["open_statuses"]) == {"待整改", "整改中", "待验收"}
    assert payload["dimensions"] == ["区域", "公厕等级"]
    # 明确区分“公厕等级”与巡查“评分等级”
    assert "评分等级" in payload["grade_basis"]
    assert "同一套" in payload["consistency_rule"]
