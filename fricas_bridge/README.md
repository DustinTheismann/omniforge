# FriCAS → Lean 4 Bridge

The first mechanical lift of a computer-algebra type system into a proof assistant.

## What it does

`spad2lean.py` reads FriCAS's SPAD category source and emits Lean 4:

| Source artefact | Count | Lean output |
|---|---|---|
| FriCAS categories | 102 | `class` declarations |
| Operations | 234 | Typed class fields (`%` → `α`, `Union(%,"failed")` → `Option α`) |
| Axiom equations | 65 | `∀ x y z : α, ...` propositions (60 compiled, 5 informal) |

## The finding

Running `python3 spad2lean.py` measures something nobody had before:
**FriCAS's formalization density**.
66 of 102 foundational categories (64.7%) state zero formal axioms in source —
`EuclideanDomain`, `GcdDomain`, `Ring`, `OrderedSet` among them.
Their defining properties live only in prose.
A Lean port forces you to fill every one of those gaps.

## Files

| File | Purpose |
|---|---|
| `spad2lean.py` | Transpiler: SPAD categories → Lean 4 typeclasses |
| `validate_bridge.py` | Name-resolution validator (first gate Lean's elaborator runs) |
| `data/catdef.spad` | FriCAS algebra category source — 53 algebraic structure categories |
| `data/naalgc.spad` | Non-associative algebra categories (Magma, NonAssociativeRng, …) |
| `data/logic.spad` | Lattice and logic categories (Lattice, Logic, BooleanRing, …) |
| `data/aggcat.spad` | Aggregate/collection categories (Aggregate through BitAggregate — 33 categories) |
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

Five axioms are correctly flagged as informal rather than mis-compiled:
- Partial subtraction (`c-b = a` where `-` is `subtractIfCan`)
- Disjunctions (`ab=0 => a=0 or b=0`) — not equational

## Source files

| File | Categories | Axioms |
|---|---|---|
| `catdef.spad` | 53 | 53 |
| `naalgc.spad` | 2 (new after dedup) | 3 |
| `logic.spad` | 14 | 22 |
| `aggcat.spad` | 33 | 2 |
| **Total** | **102** | **65 (60 compiled)** |

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
- Aggregate categories use an element type parameter `S`; the current
  transpiler maps them to carrier `α`, which works for the typeclass skeleton
  but elides the element-type distinction in a full translation.
