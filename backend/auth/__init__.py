"""Authentication: users, password hashing, JWT login/register.

Self-contained so it can be developed and reasoned about on its own. The User
table registers on the shared ``Base`` (so ``init_db`` creates it), and the
role it carries ("public" | "official") is what the middleware role-gate checks.
"""
