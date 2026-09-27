"""Dev A agents: Recommend + Advise, plus deterministic Watch/Predict stubs.

The stubs let the full signal->cascade->state flow run end to end today; Dev B
replaces them behind the same bus topics with the real LLM/RAG logic. Nothing
outside this package changes when that swap happens.
"""
