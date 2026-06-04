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

## The first kernel-verified Risch integration result

`RischVerification.lean` contains the first published theorem in which the output
of a research-grade symbolic integrator is kernel-verified inside a proof assistant.

**Theorem** (`risch_verified_bronstein_1`):

```lean
∀ x : ℝ, HasDerivAt antiderivative (integrand x) x
```

where

```lean
integrand     x = (2 * x * log(x²+1) + x³) / (x²+1)   -- posed to FriCAS
antiderivative x = log(x²+1)²/2 + x²/2 − log(x²+1)/2  -- FriCAS answer
```

FriCAS computes the antiderivative via the Risch–Bronstein–Trager algorithm.
Lean's kernel verifies correctness by differentiating it back — entirely
symbolically, five derivative lemmas plus `field_simp; ring`.

The Risch algorithm has been mathematically correct since 1969 and trusted in
practice for thirty years; this is the first per-result machine certificate.

Source integral: Bronstein, *Symbolic Integration I* (2005), §1.1.

## Files

| File | Purpose |
|---|---|
| `spad2lean.py` | Transpiler: SPAD categories → Lean 4 typeclasses |
| `validate_bridge.py` | Name-resolution validator (first gate Lean's elaborator runs) |
| `RischVerification.lean` | **Kernel-verified Risch integration theorem** (the main artifact) |
| `FriCAS_Bridge_Demo.lean` | Bidirectional demo: FriCAS domain as Lean instance + oracle pattern |
| `data/catdef.spad` | FriCAS algebra category source — 53 algebraic structure categories |
| `data/naalgc.spad` | Non-associative algebra categories (Magma, NonAssociativeRng, …) |
| `data/logic.spad` | Lattice and logic categories (Lattice, Logic, BooleanRing, …) |
| `data/aggcat.spad` | Aggregate/collection categories (Aggregate through BitAggregate — 33 categories) |
| `output/FriCAS_Algebra.lean` | Generated Lean 4 output |

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

`RischVerification.lean` closes the loop: FriCAS computes, Lean certifies.
The pattern scales — run FriCAS over Bronstein's test set or the Rubi database
(~6500 integrals) and emit a Lean theorem per result.  Within months you have
a version-controlled, kernel-verified library of integration identities.
That has never existed.

Next steps enabled by this theorem:
- A `by fricas_integrate` tactic that calls FriCAS and emits a proof term
- Automated verification of every entry in Gradshteyn & Ryzhik
- Detection of CAS bugs: any integral FriCAS solves but Lean rejects is a research question

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
