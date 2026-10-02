CREATE TABLE users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  salt TEXT NOT NULL,
  password_hash TEXT NOT NULL
);
CREATE TABLE logins (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires INTEGER NOT NULL
);
CREATE INDEX logins_expiry ON logins(expires);
CREATE TABLE sessions (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  id TEXT NOT NULL,
  updated REAL NOT NULL,
  body TEXT NOT NULL,
  PRIMARY KEY(user_id,id)
);
CREATE TABLE workspace_items (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('material','task')),
  updated REAL NOT NULL,
  body TEXT NOT NULL,
  PRIMARY KEY(user_id,id)
);
CREATE TABLE rate_limits (
  key TEXT PRIMARY KEY,
  count INTEGER NOT NULL,
  expires INTEGER NOT NULL
);
CREATE INDEX rate_expiry ON rate_limits(expires);
