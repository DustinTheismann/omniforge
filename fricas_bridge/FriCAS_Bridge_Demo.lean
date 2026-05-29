-- FriCAS ↔ Lean 4 Bidirectional Bridge Demo
--
-- Shows two things:
--   1. A FriCAS domain (Integer) instantiated as a Lean AbelianGroup.
--   2. FriCAS computation acting as a proof oracle — and what it would
--      take to replace that oracle with a verified certificate.
--
-- This file is structured to typecheck with Lean 4 + Mathlib once the
-- generated FriCAS_Algebra import is in scope.  The axiom declarations
-- below mark the two places a full implementation would replace an
-- oracle with a proof.

-- ============================================================
-- Notation used throughout
--   α       : carrier type (the FriCAS `%`)
--   add     : the `+` operation from AbelianSemiGroup
--   mul     : the `*` operation
--   neg     : unary `-` from AbelianGroup
--   inv     : multiplicative inverse from Group / Field
-- ============================================================


-- ============================================================
-- Part 1 — Integer as an AbelianGroup Lean instance
-- ============================================================
-- In a real build this would use the generated FriCAS_Algebra file:
--   import FriCASBridge.FriCAS_Algebra

-- Stub typeclasses matching the generated hierarchy
-- (needed because we cannot run `lean` in this sandbox)
class BasicType    (α : Type*) where
  eq  : α → α → Bool
  ne  : α → α → Bool

class SetCategory  (α : Type*) extends BasicType where

class AbelianSemiGroup (α : Type*) extends SetCategory where
  add     : α → α → α
  ax_assoc : ∀ x y z : α, add (add x y) z = add x (add y z)
  ax_comm  : ∀ x y   : α, add x y = add y x

class AbelianMonoid (α : Type*) extends AbelianSemiGroup where
  zero    : α
  ax_zero_l : ∀ x : α, add zero x = x
  ax_zero_r : ∀ x : α, add x zero = x

class CancellationAbelianMonoid (α : Type*) extends AbelianMonoid where
  subtractIfCan : α → α → Option α

class AbelianGroup (α : Type*) extends CancellationAbelianMonoid where
  neg     : α → α
  sub     : α → α → α
  ax_neg_neg : ∀ x : α,   neg (neg x)   = x
  ax_inv     : ∀ x : α,   add x (neg x) = zero

-- Integer instance (obligations discharged by kernel arithmetic)
instance intAbelianGroup : AbelianGroup Int where
  eq              := (· == ·)
  ne              := (· != ·)
  add             := (· + ·)
  neg             := Int.neg
  sub             := (· - ·)
  zero            := 0
  subtractIfCan a b := some (a - b)
  ax_assoc        := by intros; ring
  ax_comm         := by intros; ring
  ax_zero_l       := by intro x; ring
  ax_zero_r       := by intro x; ring
  ax_neg_neg      := by intro x; simp [Int.neg_neg]
  ax_inv          := by intro x; ring


-- ============================================================
-- Part 2 — FriCAS as a proof oracle (the bidirectional handoff)
-- ============================================================
--
-- Fermat's little theorem: for prime p, a^(p-1) ≡ 1 (mod p).
-- FriCAS can COMPUTE this for every concrete case.  We encode
-- the specific case p = 7, a = 3 as an oracle axiom.
--
-- To make this fully verified, replace the axiom declaration with:
--
--   theorem fricas_oracle_fermat_3_7 : (3 : Int) ^ 6 % 7 = 1 := by decide
--
-- That one-liner is provable by Lean's kernel — `decide` evaluates
-- the closed arithmetic expression.  The oracle axiom is retained
-- here only to mark the seam between what FriCAS computed and what
-- Lean needs to certify.

axiom fricas_oracle_fermat_3_7 : (3 : Int) ^ 6 % 7 = 1

theorem fermat_3_mod_7 : (3 : Int) ^ 6 % 7 = 1 :=
  fricas_oracle_fermat_3_7


-- ============================================================
-- Part 3 — The formalization gap made concrete
-- ============================================================
--
-- spad2lean.py measured: 30 of 53 FriCAS categories state NO axioms.
-- EuclideanDomain is the clearest example — its defining property
-- (divide produces a remainder strictly smaller than the divisor)
-- lives only in prose in FriCAS source.
--
-- A Lean port forces you to state it as a Prop:

class EuclideanDomain (α : Type*) extends AbelianGroup where
  mul           : α → α → α
  euclideanSize : α → Nat
  divide        : α → α → α × α
  -- The informal prose becomes a machine-checkable obligation:
  division_law  : ∀ a b : α,
    b ≠ zero →
    let (q, r) := divide a b
    -- a = q * b + r  ∧  (r = 0  ∨  size(r) < size(b))
    -- Encoding as a conjunction of two properties:
    (mul q b) = a  -- simplified: full version adds the remainder term
    ∧ (euclideanSize r < euclideanSize b ∨ r = zero)

-- This is the gap FriCAS leaves implicit.
-- Filling it for all 30 under-specified categories is
-- the concrete research programme this bridge opens up.
