/-
GF(2) identity: (a ∧ b) ∨ (a ∧ ¬b) ↔ a

Two formal proofs of the same Boolean tautology by two different methods.

Method 1 — gf2_algebraic: translate Boolean operations to ZMod 2 arithmetic
  (∧ → *, ¬b → 1-b, ∨ → + for disjoint disjuncts) and close with `ring`.
  This is a polynomial-identity argument over the field GF(2) — a genuinely
  different reduction from propositional model enumeration.

Method 2 — decision: Lean's `decide` tactic enumerates all 4 Boolean
  assignments and checks each; it is complete propositional model checking,
  structurally equivalent to an exhaustive truth table.

These two proofs are the Lean 4 side of the ProofForge E9_MULTI_METHOD
example. The SAT-refutation side (method = sat_refutation, family = cake_lpr)
verifies the same tautology by encoding its negation as CNF and running it
through CaDiCaL → drat-trim → lrat-trim → cake_lpr.

Verified by: leanprover/lean4 (lake build / lean.yml)
-/

import Mathlib.Data.ZMod.Basic   -- ZMod 2, the GF(2) carrier
import Mathlib.Tactic            -- `ring` over commutative rings

-- ── GF(2) polynomial identity ────────────────────────────────────────────────

/-- The Boolean tautology as a ZMod 2 ring identity.

Encoding: ∧ → multiplication, ¬b → (1 - b) over ZMod 2, ∨ →addition
(valid here because the disjuncts are disjoint: one has b=1, the other b=0).
`ring` closes the goal by polynomial normalisation over ZMod 2. -/
theorem gf2_and_or_identity (a b : ZMod 2) :
    a * b + a * (1 - b) = a := by ring

-- ── Decision / enumeration proof ────────────────────────────────────────────

/-- The same tautology verified by exhaustive Boolean case enumeration. -/
theorem bool_and_or_identity (a b : Bool) :
    ((a && b) || (a && !b)) = a := by
  cases a <;> cases b <;> rfl
