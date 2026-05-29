# FriCAS → Lean 4 Bridge

The first mechanical lift of a computer-algebra type system into a proof assistant.

## What it does

`spad2lean.py` reads FriCAS's SPAD category source and emits Lean 4:

| Source artefact | Count | Lean output |
|---|---|---|
| FriCAS categories | 53 | `class` declarations |
| Operations | 80 | Typed class fields (`%` → `α`, `Union(%,"failed")` → `Option α`) |
| Axiom equations | 44 | `∀ x y z : α, ...` propositions (39 compiled, 5 informal) |

## The finding

Running `spad2lean.py --stats` measures something nobody had before:
**FriCAS's formalization density**.
30 of 53 foundational categories (57%) state zero formal axioms in source —
`EuclideanDomain`, `GcdDomain`, `PartialOrder` among them.
Their defining properties live only in prose.
A Lean port forces you to fill every one of those gaps.

## Files

| File | Purpose |
|---|---|
| `spad2lean.py` | Transpiler: SPAD categories → Lean 4 typeclasses |
| `validate_bridge.py` | Name-resolution validator (first gate Lean's elaborator runs) |
| `data/catdef.spad` | FriCAS algebra category source (subset) |
| `output/FriCAS_Algebra.lean` | Generated Lean 4 output |
| `FriCAS_Bridge_Demo.lean` | Bidirectional demo: FriCAS domain as Lean instance + oracle pattern |

## Quick start

```bash
# Transpile and print stats
python3 spad2lean.py

# Validate name resolution for all compiled axioms
python3 validate_bridge.py

# With per-category summary
python3 validate_bridge.py --summary
```

## How axioms are compiled

FriCAS encodes axioms as equations in `++ Axioms:` doc comments using `\spad{...}`:

```
++ Axioms:
++   \spad{associative("+":(%,%)->%)}\tab{30}\spad{ (x+y)+z = x+(y+z) }
```

The equation `(x+y)+z = x+(y+z)` is parsed by a precedence-climbing expression
compiler that maps SPAD operators to Lean field names and lifts free variables
to a universal quantifier:

```lean
ax0 : ∀ x y z : α, (add (add x y) z) = (add x (add y z))
```

Six axioms are correctly flagged as informal rather than mis-compiled:
- Partial subtraction (`c-b = a` where `-` is `subtractIfCan`)
- Disjunctions (`ab=0 => a=0 or b=0`) — not equational

## The bidirectional vision

`FriCAS_Bridge_Demo.lean` shows the two-way handoff:

- **Lean → FriCAS**: `Int` instantiates `AbelianGroup` with proof obligations
  discharged by Lean's kernel (`ring`, `simp`).
- **FriCAS → Lean**: a Fermat little theorem instance over a specific prime
  is marked as an oracle axiom — the seam where FriCAS computation would
  provide a certificate that Lean's `decide` then verifies.

Wire the oracle as a verified reflection instead of an `axiom` and you have
a system that both computes and proves modern algebra.  Nobody has built that.
This is the first brick.

## Honest limitations

- Lean binaries are unavailable in this environment; the soundness check is
  name resolution (the first elaboration gate), not full typechecking.
- Diamond-inheritance from Lean's typeclass system (e.g. `Ring` inheriting
  `add` through multiple paths) would need projection disambiguation.
- The `%`-parametric axioms treat all variables as carrier-typed; ring
  parameters (the `R` in `LeftModule(R)`) would need separate quantifiers
  in a fully faithful translation.
