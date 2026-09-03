import unittest

from backend.sessions import MemorySessionStore


class MemorySessionStoreTest(unittest.TestCase):
    def test_access_renews_expiration_and_inactivity_expires_session(self):
        now = 1000
        client = object()
        store = MemorySessionStore(
            clock=lambda: now,
            token_factory=lambda: "session-id",
        )

        session_id = store.create(client)
        now += 1000
        self.assertIs(client, store.get(session_id))
        now += 1000
        self.assertIs(client, store.get(session_id))
        now += 1801
        self.assertIsNone(store.get(session_id))


if __name__ == "__main__":
    unittest.main()
