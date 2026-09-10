from src.kb_bot import TenantQuestion, answer_question


class StubClient:
    def find_documents(self, question, tenant_id):
        assert tenant_id == "acme"
        assert "offboard" in question
        return [{"metadata": {"answer": "Disable seats, export data, then close billing."}}]


def test_offboarding_answer_is_tenant_scoped():
    result = answer_question(StubClient(), TenantQuestion("acme", "How do I offboard a tenant?"))
    assert result == "For tenant acme: Disable seats, export data, then close billing."
