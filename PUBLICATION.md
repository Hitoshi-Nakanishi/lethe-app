# Publication checks

Argus runs locally from a separate guard checkout with the owner's private
policy. Keep that policy and detailed findings outside this public repository.
With the guard environment activated, run from its root:

```sh
python -m apps.argus --source install --repo <source-checkout>
python -m apps.argus --source check --repo <source-checkout>
python -m apps.argus --source history --all --repo <source-checkout>
```

Install the hooks again in every clone. They check staged changes, commit
messages, and all locally referenced history before a push, including annotated
tags and commits already on a remote. The private policy must remain readable.
CI tests do not replace these local checks.

Both scans must pass before publication. Unreadable screenshots and archive
members remain findings until resolved. Deleted content remains in history;
checking the current files alone is insufficient. A passing scan means only
that the configured rules found no matches.

Resolve findings with the owner. Never bypass a hook or add a policy exception
without the owner's decision. Any shared history rewrite or publication needs
explicit owner authorization.
