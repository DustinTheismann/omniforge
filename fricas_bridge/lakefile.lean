import Lake
open Lake DSL

package "fricas_bridge" where
  name := "fricas_bridge"

require "leanprover-community" / "mathlib" @ git "v4.30.0"

/-- The verified Risch integration library.
    Contains RischVerification.lean with four HasDerivAt theorems
    and the fricas_integrate pipeline. -/
lean_lib FriCASBridge where
  roots := #[`RischVerification]

/-- Lean 4 ↔ FriCAS expression translator (ProofForge.FriCAS namespace). -/
lean_lib FriCASTranslator where
  roots := #[`FriCASTranslator]

/-- FriCAS expression string → Lean 4 Expr parser. -/
lean_lib FriCASParser where
  roots := #[`FriCASParser]

/-- Step D — auto-discharged proofs for the four Class A Risch claims. -/
lean_lib RischAutoDischarge where
  roots := #[`RischAutoDischarge]

/-- Tier 1.4 — the general n-pole partial-fraction scaling-law theorem. -/
lean_lib PartialFractionHasDerivAt where
  roots := #[`PartialFractionHasDerivAt]

/-- Tier 1.5 — CAS disagreement kernel adjudication.
    Proves that the FriCAS/Maxima factored-log form and the SymPy product-log
    form for bronstein_005 and bronstein_009 are equal under the domain
    conditions required by HasDerivAt (via Real.log_mul). -/
lean_lib CasAdjudication where
  roots := #[`CasAdjudication]

/-- E9_MULTI_METHOD — the GF(2) side of the cross-method certificate.
    gf2_and_or_identity closes a * b + a * (1 - b) = a over ZMod 2 by `ring`;
    bool_and_or_identity verifies the same tautology by Boolean enumeration.
    Wiring this as a root sends the proof to the Lean kernel on every CI run
    (lean.yml), so the E9 Lean anchor is reproduced rather than asserted. -/
lean_lib Gf2Identity where
  roots := #[`Gf2Identity]
