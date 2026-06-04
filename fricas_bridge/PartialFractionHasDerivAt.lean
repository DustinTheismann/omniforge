-- Tier 1.4 — Scaling-law theorem: the general n-pole partial-fraction HasDerivAt.
--
-- This is the kernel-checked counterpart to fricas_bridge/scaling_theorem.py.
-- The generator emits this exact proof; this file is the source of truth that
-- the Lean toolchain elaborates in CI (lean_lib PartialFractionHasDerivAt).
--
-- Statement: for any n simple real poles a_i with residues c_i,
--   d/dx Σ_i c_i · log(x - a_i)  =  Σ_i c_i / (x - a_i)
-- which is the formal content of "the partial-fraction scaling law is a
-- theorem, not an observation."
import Mathlib.Analysis.SpecialFunctions.Log.Deriv
import Mathlib.Analysis.Calculus.Deriv.Add
import Mathlib.Analysis.Calculus.Deriv.Mul
import Mathlib.Tactic

noncomputable section
open Real Finset

/-- General partial-fraction `HasDerivAt`.
    For `n` real poles with simple-pole residues, the antiderivative is a sum of
    weighted real logarithms, and its derivative is the partial-fraction sum. -/
theorem partial_fraction_hasDerivAt
    {n : ℕ} (poles coeffs : Fin n → ℝ) (x : ℝ)
    (h_ne : ∀ i, x - poles i ≠ 0) :
    HasDerivAt (fun y : ℝ => ∑ i, coeffs i * Real.log (y - poles i))
               (∑ i, coeffs i / (x - poles i)) x := by
  have step : ∀ i : Fin n,
      HasDerivAt (fun y : ℝ => coeffs i * Real.log (y - poles i))
        (coeffs i / (x - poles i)) x := by
    intro i
    have hsub : HasDerivAt (fun y : ℝ => y - poles i) (1 : ℝ) x := by
      simpa using (hasDerivAt_id x).sub_const (poles i)
    have hlog : HasDerivAt (fun y : ℝ => Real.log (y - poles i))
        (1 / (x - poles i)) x := by
      simpa using hsub.log (h_ne i)
    simpa [mul_one_div] using hlog.const_mul (coeffs i)
  -- HasDerivAt.sum concludes about the *function* `∑ i, A i`; convert it to the
  -- pointwise `fun y => ∑ i, A i y` via Finset.sum_apply rather than rely on defeq.
  have hsum := HasDerivAt.sum (fun i (_ : i ∈ (Finset.univ : Finset (Fin n))) => step i)
  have hfun :
      (fun y : ℝ => ∑ i, coeffs i * Real.log (y - poles i))
        = (∑ i : Fin n, fun y : ℝ => coeffs i * Real.log (y - poles i)) := by
    funext y; simp [Finset.sum_apply]
  rw [hfun]
  exact hsum

/-- Single-pole specialisation (the `n = 1` instance, matching the shape of
    Risch–Bronstein claim 007 `∫ c/(x-a) dx = c·log(x-a)`).  Derived purely from
    the general theorem to demonstrate it is usable, not just provable. -/
theorem partial_fraction_one_pole
    (a c x : ℝ) (h : x - a ≠ 0) :
    HasDerivAt (fun y : ℝ => c * Real.log (y - a)) (c / (x - a)) x := by
  have h1 := partial_fraction_hasDerivAt (n := 1)
    (fun _ => a) (fun _ => c) x (by intro i; simpa using h)
  simpa [Fin.sum_univ_one] using h1

end
