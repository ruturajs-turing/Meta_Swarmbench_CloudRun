# Harbor Patch

`swarmbench_harbor_changes.diff` is the client-aligned SwarmBench patch used by the managed Harbor/OpenCode runtime.

- Harbor base commit: `e70d5f060ffeb4525f320669d50b290925b55425`
- Patch SHA-256: `5c60e8ec05b29b9014db25ecce2cf0fad5384e08df968e734f6d4094c24e72d6`
- Runtime agents: `swarm-opencode-single`, `swarm-opencode-multi`, and the corresponding SwarmBench Kimi agents

Apply it to a clean checkout of the base commit:

```bash
git -C ../harbor apply --check "$PWD/patches/swarmbench_harbor_changes.diff"
git -C ../harbor apply "$PWD/patches/swarmbench_harbor_changes.diff"
```

Do not reapply it to a checkout where the patch is already present. Verify with:

```bash
git -C ../harbor apply --reverse --check "$PWD/patches/swarmbench_harbor_changes.diff"
```
