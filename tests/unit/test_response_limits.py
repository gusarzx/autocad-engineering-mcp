from autocad_engineering_mcp.core.models import Result


def test_response_limit_preserves_mutation_status_and_handles(cad):
    result = cad.bound(Result(object_ids=["AB"], count=1, data={"detail": "x" * 150000}))
    assert result.status == "ok" and result.object_ids == ["AB"] and result.count == 1
    assert result.data == {"response_truncated": True}
    assert result.warnings
