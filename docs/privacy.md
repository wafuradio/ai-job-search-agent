# Local privacy and publication boundary

Real profiles, relationship data, work evidence, private development context, local
app settings, databases and sidecars, database dumps/backups, generated reports,
credentials and local handoff notes must stay outside commits. Ignore rules apply to
all candidates, without an exception for the default owner. Neutral templates and
synthetic regression fixtures are deliberately shareable.

An ignore rule does not untrack an existing file or remove its earlier commits. The
legacy top-level personal JSON files are absent from the working tree, but their
removals still need to be included when an actual source commit is authorized.
Do not force-add real profile files, local app settings or ignored artifacts.

Tests use temporary synthetic profile/data roots set before application imports.
The fixture's experience, compensation and preferences are fictional. Production
uses the existing local configuration unless an explicit root override is supplied.
No cleanup operation should delete a working candidate profile, review record or
credential. Keep private backups separate from the public source tree.

## Historical remediation

The repository originally committed candidate configuration, relationships and
profile-derived examples. Removing files in a new commit alone does not remove that
information from older commits or previously fetched branches.

A separately prepared sanitized mirror can preserve source commit topology while
omitting the old configuration directory and profile-derived documentation/test
snapshots from history. Source prompts are neutralized, and author identities and
commit messages use generic placeholders. Current cleaned documentation and synthetic
tests are retained in the working tree and clean export for a later authorized commit.
This is an intentional loss of old documentation/test history in the sanitized copy.
The original history is retained in a separate private backup for recovery.

Before publishing a sanitized replacement:

1. Verify every reachable commit/ref in the sanitized mirror, not only its HEAD.
   Check that removed private blobs are absent from the fresh mirror object store.
2. Make an explicitly authorized commit containing the cleaned current source in
   a suitable sanitized checkout. Verify that profiles, settings, data, credentials
   and private notes are absent from the committed snapshot. Run offline tests there.
3. Confirm repository visibility and decide whether to replace existing branches
   or create a fresh repository. Rewriting published branches requires an explicit
   approval and coordination with collaborators. Do not use a blanket mirror push.
4. Account for old branches, tags, pull-request refs, forks, caches and existing
   clones. A force-push alone cannot guarantee erasure from those locations. Use the
   hosting provider's sensitive-data removal process where required. Collaborators
   should use fresh clones and avoid reintroducing old history.

The active development repository and GitHub history are intentionally not rewritten
by local preparation alone. Nothing has been pushed as part of this cleanup. There
were no likely credential-pattern matches in the initial history audit; pattern scans
are not a guarantee. If a real secret is ever found in published history, revoke it
rather than relying on history rewriting alone.
