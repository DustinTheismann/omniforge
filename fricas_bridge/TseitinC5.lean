/-
Tseitin contradiction on the 5-cycle C₅ — the GF(2) linear-algebra anchor of a
non-toy E9_MULTI_METHOD certificate.

The same unsatisfiable fact is established by two genuinely different formal
methods:

Method 1 — gf2_linear_algebra (this file): the five vertex parity constraints
  of an odd-charge Tseitin formula are summed over GF(2). Every edge variable
  lies on exactly two vertices, so it occurs twice in the sum and cancels in
  characteristic 2, collapsing the left side to 0 while the right side is the
  total charge, 1. Hence 0 = 1: the system has no model. This is Gaussian
  elimination over 𝔽₂ — a structural/algebraic argument, NOT a search over
  assignments.

Method 2 — sat_refutation (benches/multimethod/tseitin_c5.cnf): the same
  constraints are encoded as a DIMACS CNF; CaDiCaL produces an UNSAT proof and
  cake_lpr (a CakeML binary whose LRAT checker is proven correct in HOL4)
  accepts it. This is propositional refutation — resolution, not algebra.

Tseitin formulas are the canonical example separating these two methods: on an
expander graph the resolution proof is exponential while the 𝔽₂ argument stays
linear. We instantiate on a cycle (bounded treewidth) precisely so the SAT
proof is also polynomial — keeping both anchors cheap while the *methods* remain
the genuinely-orthogonal pair. (Contrast the earlier gf2_and_or toy, a single
two-variable tautology.)

Verified by: leanprover/lean4 (lake build / lean.yml)
-/

import Mathlib.Data.ZMod.Basic   -- ZMod 2, the GF(2) carrier
import Mathlib.Tactic            -- linear_combination, ring

-- ── GF(2) linear-algebra refutation ─────────────────────────────────────────

/-- The odd-charge Tseitin parity system on C₅ has no GF(2) model.

Constraints (edges `e₁ … e₅`, one parity equation per vertex):
`e₅+e₁ = 1`, `e₁+e₂ = 0`, `e₂+e₃ = 0`, `e₃+e₄ = 0`, `e₄+e₅ = 0`.

Proof: `linear_combination` sums the five hypotheses; the residual
`2·(e₁+…+e₅) − 1` is identical on both sides, so it closes by `ring` with no
characteristic assumption. The summed identity is `2·(e₁+…+e₅) = 1`; in
characteristic 2 the left side is `0`, giving `0 = 1`. -/
theorem tseitin_c5_unsat (e1 e2 e3 e4 e5 : ZMod 2)
    (h1 : e5 + e1 = 1) (h2 : e1 + e2 = 0) (h3 : e2 + e3 = 0)
    (h4 : e3 + e4 = 0) (h5 : e4 + e5 = 0) : False := by
  have htwo : (2 : ZMod 2) = 0 := by decide
  -- Universal ring identity: the constraint sum equals 2·Σ eᵢ = 1.
  have hsum : (2 : ZMod 2) * (e1 + e2 + e3 + e4 + e5) = 1 := by
    linear_combination h1 + h2 + h3 + h4 + h5
  -- Characteristic 2 collapses the left side to 0.
  have hzero : (2 : ZMod 2) * (e1 + e2 + e3 + e4 + e5) = 0 := by
    rw [htwo, zero_mul]
  rw [hzero] at hsum
  exact absurd hsum (by decide)

/-- The same statement as the non-existence of a model — the form the SAT lane
refutes. Derived from `tseitin_c5_unsat`; no assignment enumeration. -/
theorem tseitin_c5_no_model :
    ¬ ∃ e1 e2 e3 e4 e5 : ZMod 2,
        e5 + e1 = 1 ∧ e1 + e2 = 0 ∧ e2 + e3 = 0 ∧ e3 + e4 = 0 ∧ e4 + e5 = 0 := by
  rintro ⟨e1, e2, e3, e4, e5, h1, h2, h3, h4, h5⟩
  exact tseitin_c5_unsat e1 e2 e3 e4 e5 h1 h2 h3 h4 h5
