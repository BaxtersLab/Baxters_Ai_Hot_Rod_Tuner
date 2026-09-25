# Hot Rod Tuner — ROADMAP

Declared stubs and deferrals (Article VII.2).

## 2026-08-18 — packaging (Phase A4)

- [ ] STUB: `baxters-hot-rod-tuner` interpreter dependency — must depend on
  `baxters-runtime` (`/opt/baxters/runtime`, hash-pinned, offline wheels) —
  deferred because **A3 has not been built yet**. The package currently declares
  `python3 (>= 3.11)` plus distro `python3-*` packages. This is a **declared
  deviation from the A1 contract §2**, not an accident, and must be revisited the
  moment `baxters-runtime` exists.
- [ ] STUB: group membership for fan control — `usermod -aG baxtersfan $USER`
  cannot be performed safely by a package (it needs a re-login and is a real
  privilege change). `postinst` prints the exact command instead. If this should
  be automated, that is an operator decision, not a packaging one.
