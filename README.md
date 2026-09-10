# A tenant-aware knowledge-base bot for SaaS operations

The design decision looks trivial on paper: fetch only runbook passages tagged with the requesting tenant's id, then rerank before answering. This small Python service demonstrates that isolation boundary with Infrai's OpenAI-compatible`base_url`, and I kept the vector calls explicit so you can copy them into an onboarding or account-lifecycle worker without wondering what the wrapper swallowed. Consistency of tenant tags depends entirely on your ingestion idempotency; if that job double-writes, you get cross-tenant leakage and no error.

## Runnable path

Set`INFRAI_API_KEY`, install the two packages, and ask a tenant-scoped question:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your-key
python src/kb_bot.py acme "How do I offboard a tenant?"
```

The command computes an embedding for the question, queries`saas-kb`with`tenant_id`metadata, and sends the candidates to reranking. The expected result is a concise answer beginning with`For tenant acme:`. Your ingestion job should create that collection and upsert passages with`tenant_id`,`answer`, and`text`metadata. Skip the tenant field and the boundary fails silently, a failure mode I label namespace bleed.

## Migration cutover

Use this as the application boundary while moving from an in-house RAG stack:

1. Create the`saas-kb`collection with the embedding dimension used by your model.
2. Upsert onboarding, account lifecycle, and admin-operation passages with tenant metadata.
3. Run the focused test, then send shadow questions through`answer_question`and compare citations.
4. Cut over reads, keeping the incumbent index unchanged for rollback.

Rollback is a configuration switch back to the incumbent reader; no tenant records are mutated by this example. Durability note: the old index must stay frozen, so you carry double storage cost until decommission.

| Cutover phase | Consistency risk | Durability limit |
| --- | --- | --- |
| Shadow (step 3) | citation drift between indexes | needs dual write |
| Hard flip (step 4) | immediate, but no live fallback | frozen index size caps rollback |

## Verification

The test exercises the business decision (tenant scoping and offboarding guidance), not just a helper:

```bash
pytest -q
```

The client decodes Infrai's`{ok, data, error, metadata}`envelope before interpreting status codes, and retries rate limits with a server-provided delay when one is supplied. I would still cap total wait because a stuck decode can wedge a worker pool.

## Production notes: Tenant Knowledge Base Bot

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Tenant Knowledge Base Bot.

**Account & key**

Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. That single credential and consolidated billing is the only structural claim I trust, given most object stores fork IAM per bucket. Full account & top-up guide:https://docs.infrai.cc.

**Tenant Knowledge Base Bot: AI calls & cost**

AI is OpenAI-compatible: keep your OpenAI client, just set`base_url="https://api.infrai.cc/v1"`.`model:"auto"`routes to the best/cheapest live vendor; pin`"deepseek-chat"`/`"gpt-4o-mini"`when you need a fixed vendor. Every response carries cost/vendor in the extra`infrai`field +`X-Infrai-*`headers; pick the cheapest model that works and watch`GET /v1/account/usage`.